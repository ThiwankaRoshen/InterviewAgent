from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ASSEMBLYAI_API_KEY: str
    DEEPGRAM_API_KEY: str
    DEEPGRAM_VOICE: str
    GITHUB_TOKEN: str
    OPENAI_MODEL: str
    LANGSMITH_API_KEY: str
    LANGSMITH_PROJECT: str
    OTEL_EXPORTER_OTLP_ENDPOINT: str

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
    )


settings = Settings()