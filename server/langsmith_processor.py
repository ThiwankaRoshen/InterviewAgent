"""OTel → LangSmith bridge for Pipecat.

Pipecat emits OTel spans named `conversation`, `turn`, `stt`, `llm`, and `tts`,
but with attributes (`transcript`, `input`/`output`, `text`, `turn.number`, …)
that LangSmith's OTLP ingester doesn't recognize. This `SpanProcessor` rewrites
each span type into the `gen_ai.*` / `langsmith.*` namespaces LangSmith keys
off, renders the whole conversation onto the root span, and attaches the
recorded audio there. It wraps its downstream exporter so attributes are always
rewritten before the span is queued for export.

The trace shape in LangSmith:

    conversation                      (root; whole transcript + conversation WAV)
    └── turn × N                      (per exchange; carries was_interrupted)
        ├── stt                       (audio → transcript)
        ├── llm                       (chain — the LangGraph brain; inference is
        │   │                          in the nested model nodes below)
        │   ├── model                 (ChatOpenAI inference; may emit tool calls)
        │   ├── tools: lookup_weather (tool execution)
        │   └── model                 (final answer — spoken)
        └── tts                       (response text → audio)
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Callable, Optional

from loguru import logger
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from dotenv import load_dotenv
load_dotenv()

class LangSmithSpanProcessor(SpanProcessor):
    """Enriches Pipecat's OTel spans with LangSmith-compatible attributes."""

    def __init__(
        self,
        downstream_processor: Optional[SpanProcessor] = None,
        *,
        llm_span_kind: str = "llm",
        thread_id_provider: Optional[Callable[[], Optional[str]]] = None,
    ) -> None:
        """Create the processor.

        Args:
            downstream_processor: where rewritten spans are forwarded; defaults
                to `BatchSpanProcessor(OTLPSpanExporter())`.
            llm_span_kind: LangSmith run kind for Pipecat's `llm` span. Keep
                the default `"llm"` for stock services (e.g. OpenAILLMService).
                Pass `"chain"` when the LLM stage only orchestrates nested runs
                that are exported to LangSmith themselves.
            thread_id_provider: opt-in conversation id for LangSmith thread
                grouping; called per span, None disables.
        """
        super().__init__()
        if downstream_processor is None:
            downstream_processor = BatchSpanProcessor(OTLPSpanExporter())
        self.downstream = downstream_processor
        self._llm_span_kind = llm_span_kind
        self.thread_id_provider = thread_id_provider
        # The latest llm request's full context per trace — each request
        # carries the whole history, so the last snapshot IS the conversation.
        self._conversation_by_trace: dict[str, list] = {}
        self.conversation_recordings: dict[str, str] = {}
        self.conversation_recorders: dict[str, object] = {}

    # -- recorder registration ------------------------------------------------

    def register_recording(self, conversation_id, recording_path, audio_recorder=None):
        """Register the whole-conversation recording for the root span."""
        self.conversation_recordings[conversation_id] = recording_path
        if audio_recorder:
            self.conversation_recorders[conversation_id] = audio_recorder

    # -- span lifecycle -------------------------------------------------------

    def on_start(self, span: ReadableSpan, parent_context=None) -> None:
        self.downstream.on_start(span, parent_context)

    def on_end(self, span: ReadableSpan) -> None:
        """Rewrite a Pipecat span into LangSmith's expected attribute shape.

        KEY FIX: Pipecat ends spans before this processor runs, so
        `span._attributes` is a frozen BoundedAttributes object. Any mutation
        on it triggers OpenTelemetry's "Setting attribute on ended span"
        warnings, which then surface as "Error during completion" errors in the
        pipeline. We replace it with a plain mutable dict before any writes so
        those warnings — and the downstream exceptions — never fire.
        """
        # Replace frozen BoundedAttributes with a plain mutable dict.
        # This must happen before any attribute writes below.
        if not isinstance(span._attributes, dict):
            span._attributes = dict(span._attributes or {})

        trace_id = format(span.context.trace_id, "032x")

        # Thread grouping (opt-in)
        if (
            self.thread_id_provider is not None
            and "langsmith.metadata.thread_id" not in span._attributes
        ):
            thread_id = self.thread_id_provider()
            if thread_id:
                span._attributes["langsmith.metadata.thread_id"] = str(thread_id)

        if span.name == "stt":
            self._handle_stt(span)
            self._exclude_from_message_view(span)
        elif span.name == "llm":
            self._handle_llm(span, trace_id)
        elif span.name == "tts":
            self._handle_tts(span)
            self._exclude_from_message_view(span)
        elif span.name == "turn":
            self._handle_turn(span)
        elif span.name == "conversation":
            self._handle_conversation(span, trace_id)

        self.downstream.on_end(span)

    def _exclude_from_message_view(self, span: ReadableSpan) -> None:
        """Drop a framework stt/tts span from the LangSmith Messages view."""
        span._attributes["langsmith.metadata.ls_message_view_exclude"] = True

    # -- per-span-type handlers -----------------------------------------------

    def _handle_stt(self, span: ReadableSpan) -> None:
        transcript = span.attributes.get("transcript", "")
        span._attributes["langsmith.span.kind"] = "llm"
        self._set_prompt_attributes(
            span, [{"role": "user", "content": f'Audio for: "{transcript}"'}]
        )
        if transcript:
            self._set_completion_attributes(
                span, [{"role": "assistant", "content": str(transcript)}]
            )

    def _handle_llm(self, span: ReadableSpan, trace_id: str) -> None:
        input_data = span.attributes.get("input", "")
        output_data = span.attributes.get("output", "")

        span._attributes["langsmith.span.kind"] = self._llm_span_kind

        try:
            raw_messages = json.loads(input_data)
        except (json.JSONDecodeError, TypeError):
            raw_messages = []
        messages = [
            self._to_langchain_message(m)
            for m in (raw_messages if isinstance(raw_messages, list) else [])
            if isinstance(m, dict)
        ]

        if messages:
            span._attributes["gen_ai.prompt"] = json.dumps({"messages": messages})
        if output_data:
            span._attributes["gen_ai.completion"] = json.dumps(
                {"messages": [{"role": "assistant", "content": output_data}]}
            )

        transcript = [m for m in messages if m.get("role") != "system"]
        if output_data:
            transcript.append({"role": "assistant", "content": output_data})
        if transcript:
            self._conversation_by_trace[trace_id] = transcript

    def _handle_tts(self, span: ReadableSpan) -> None:
        text = span.attributes.get("text", "")
        span._attributes["langsmith.span.kind"] = "llm"
        voice_id = span.attributes.get("voice_id")
        if voice_id:
            span._attributes["langsmith.metadata.voice_id"] = str(voice_id)
        self._set_prompt_attributes(span, [{"role": "user", "content": str(text)}])
        self._set_completion_attributes(
            span, [{"role": "assistant", "content": f'Generated audio for: "{text}"'}]
        )

    def _handle_turn(self, span: ReadableSpan) -> None:
        span._attributes["langsmith.span.kind"] = "chain"
        turn_number = span.attributes.get("turn.number")
        if turn_number is not None:
            span._attributes["langsmith.metadata.turn_number"] = turn_number
        was_interrupted = span.attributes.get("turn.was_interrupted")
        if was_interrupted is not None:
            span._attributes["langsmith.metadata.turn_was_interrupted"] = was_interrupted

    def _handle_conversation(self, span: ReadableSpan, trace_id: str) -> None:
        conversation_id = span.attributes.get("conversation.id", "") or span.attributes.get(
            "conversation_id", ""
        )
        span._attributes["langsmith.span.kind"] = "chain"
        span._attributes["langsmith.root_span"] = True
        span._attributes["langsmith.metadata.ls_modality"] = "audio"

        messages = self._conversation_by_trace.get(trace_id, [])
        if messages:
            span._attributes["gen_ai.prompt"] = json.dumps({"messages": messages[:1]})
            if len(messages) > 1:
                span._attributes["gen_ai.completion"] = json.dumps(
                    {"messages": messages[1:]}
                )

        self._attach_conversation_audio(span, conversation_id)
        self._cleanup_conversation(trace_id, conversation_id)

    # -- audio attachment -----------------------------------------------------

    def _attach_conversation_audio(self, span: ReadableSpan, conversation_id) -> None:
        recorder = self.conversation_recorders.get(conversation_id)
        if recorder is not None:
            try:
                recorder.save_recording()
            except Exception as e:
                logger.warning(f"Failed to save recording for {conversation_id}: {e}")

        path_str = self.conversation_recordings.get(conversation_id)
        if path_str is None and len(self.conversation_recordings) == 1:
            path_str = next(iter(self.conversation_recordings.values()))
        if not path_str:
            return

        encoded = self._load_audio_file(path_str)
        if encoded:
            span._attributes["langsmith.attachments"] = json.dumps(
                [
                    {
                        "name": Path(path_str).name,
                        "content": encoded,
                        "mime_type": "audio/wav",
                    }
                ]
            )
            logger.debug(f"Attached recording {Path(path_str).name} to conversation span")

    def _cleanup_conversation(self, trace_id: str, conversation_id) -> None:
        self._conversation_by_trace.pop(trace_id, None)
        self.conversation_recordings.pop(conversation_id, None)
        self.conversation_recorders.pop(conversation_id, None)

    # -- attribute helpers ----------------------------------------------------

    @staticmethod
    def _to_langchain_message(msg: dict) -> dict:
        """Convert one OpenAI-format context message to LangChain flat format."""
        content = msg.get("content")
        if not isinstance(content, str):
            content = "" if content is None else json.dumps(content)
        out: dict = {"role": str(msg.get("role", "")), "content": content}
        tool_calls = []
        for tc in msg.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function") or {}
            args = fn.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    pass
            tool_calls.append(
                {
                    "type": "tool_call",
                    "id": tc.get("id"),
                    "name": fn.get("name"),
                    "args": args if isinstance(args, dict) else {},
                }
            )
        if tool_calls:
            out["tool_calls"] = tool_calls
        if msg.get("tool_call_id"):
            out["tool_call_id"] = str(msg["tool_call_id"])
        if msg.get("role") == "tool" and msg.get("name"):
            out["name"] = str(msg["name"])
        return out

    def _set_prompt_attributes(self, span: ReadableSpan, messages: list) -> None:
        for i, msg in enumerate(messages):
            span._attributes[f"gen_ai.prompt.{i}.role"] = msg.get("role", "")
            span._attributes[f"gen_ai.prompt.{i}.content"] = msg.get("content", "")

    def _set_completion_attributes(self, span: ReadableSpan, messages: list) -> None:
        for i, msg in enumerate(messages):
            span._attributes[f"gen_ai.completion.{i}.role"] = msg.get("role", "")
            span._attributes[f"gen_ai.completion.{i}.content"] = msg.get("content", "")

    def _load_audio_file(self, file_path) -> str | None:
        try:
            path = Path(file_path)
            if path.exists():
                data = path.read_bytes()
                if data:
                    return base64.b64encode(data).decode("utf-8")
        except Exception as e:
            logger.warning(f"Failed to load audio file {file_path}: {e}")
        return None

    def shutdown(self) -> None:
        self.downstream.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self.downstream.force_flush(timeout_millis)


def setup_langsmith_tracing(
    *,
    llm_span_kind: str = "llm",
    thread_id_provider: Optional[Callable[[], Optional[str]]] = None,
) -> LangSmithSpanProcessor:
    """Configure OTel export to LangSmith and register the span processor.

    Returns the processor instance so the agent can register audio recorders.
    """
    from pipecat.utils.tracing.setup import setup_tracing

    api_key = os.environ.get("LANGSMITH_API_KEY", "")
    project = os.environ.get("LANGSMITH_PROJECT", "default")
    base_endpoint = os.environ.get(
        "OTEL_EXPORTER_OTLP_ENDPOINT", "https://api.smith.langchain.com/otel"
    )
    # OTLPSpanExporter appends /v1/traces only when reading from env vars, not
    # when the endpoint is passed as a constructor argument, so we add it here.
    traces_endpoint = f"{base_endpoint.rstrip('/')}/v1/traces"

    exporter = OTLPSpanExporter(
        endpoint=traces_endpoint,
        headers={
            "x-api-key": api_key,
            "Langchain-Project": project,
        },
    )
    downstream = BatchSpanProcessor(exporter)

    setup_tracing(service_name="voice-demo-pipecat", exporter=None, console_export=False)

    span_processor = LangSmithSpanProcessor(
        downstream_processor=downstream,
        llm_span_kind=llm_span_kind,
        thread_id_provider=thread_id_provider,
    )
    provider = trace.get_tracer_provider()
    if isinstance(provider, TracerProvider):
        provider.add_span_processor(span_processor)
    else:
        logger.warning("LangSmith tracing: TracerProvider not available, spans will not be exported.")
    return span_processor