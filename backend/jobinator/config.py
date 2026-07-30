from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="JOBINATOR_",
        extra="ignore",
    )

    database_url: str = "sqlite:///./data/jobinator.db"
    openai_api_key: SecretStr | None = None
    greenhouse_board_token: str | None = None
    greenhouse_company: str | None = None
    lever_site: str | None = None
    lever_company: str | None = None
    ashby_board: str | None = None
    ashby_company: str | None = None
    career_page_urls: list[str] = Field(default_factory=list)
    workday_posting_urls: list[str] = Field(default_factory=list)
