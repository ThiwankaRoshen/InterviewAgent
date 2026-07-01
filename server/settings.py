from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr

class Settings(BaseSettings):
    ASSEMBLYAI_API_KEY: str
    DEEPGRAM_API_KEY: str
    DEEPGRAM_VOICE: str
    GITHUB_TOKEN: str
    OPENAI_MODEL: str
    LANGSMITH_API_KEY: str
    LANGSMITH_PROJECT: str
    OTEL_EXPORTER_OTLP_ENDPOINT: str
    SECRET_KEY: SecretStr
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    MAX_UPLOAD_SIZE_BYTES: int = 5 * 1024 * 1024

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
    )


settings = Settings()