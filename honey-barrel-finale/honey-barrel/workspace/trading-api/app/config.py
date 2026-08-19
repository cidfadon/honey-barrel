from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Trading212 ---
    t212_mode: str = "mock"                       # mock | demo | live
    t212_api_key: str = ""
    t212_api_secret: str = ""

    # --- Ollama ---
    ollama_base_ip: str = ""
    ollama_url: str = "http://ollama:11434"
    ollama_model: str = "batiai/gemma4-e4b:q4"

    # --- DB ---
    database_url: str = "sqlite:///./local.db"    # overridden in docker

    # --- Safety caps ---
    max_orders_per_day: int = 5
    max_notional_eur: float = 200.0
    auto_execute: bool = False

    def resolved_ollama_url(self) -> str:
        if self.ollama_url and self.ollama_url != "http://ollama:11434":
            return self.ollama_url.rstrip("/")
        if self.ollama_base_ip:
            return f"http://{self.ollama_base_ip}:11434"
        return self.ollama_url.rstrip("/")


settings = Settings()


def t212_base_url() -> str:
    if settings.t212_mode == "live":
        return "https://live.trading212.com/api/v0"
    # demo & mock both target demo URL; mock client never actually calls it
    return "https://demo.trading212.com/api/v0"
