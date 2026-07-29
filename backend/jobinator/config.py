from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="JOBINATOR_",
        extra="ignore",
    )

    database_url: str = "sqlite:///./data/jobinator.db"
    openai_api_key: SecretStr | None = None
