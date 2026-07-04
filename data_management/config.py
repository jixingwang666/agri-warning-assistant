from dataclasses import dataclass
import os
from pathlib import Path


ENV_FILE = Path(__file__).resolve().parent / ".env"
SECRETS_FILE = Path(__file__).resolve().parent / "secrets.env"


def load_env_file(path: Path = ENV_FILE, override: bool = False) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if override:
            os.environ[key] = value
        else:
            os.environ.setdefault(key, value)


load_env_file(ENV_FILE)
load_env_file(SECRETS_FILE, override=True)  # secrets override .env defaults


@dataclass(frozen=True)
class DatabaseConfig:
    host: str = os.getenv("AGRI_DB_HOST", "127.0.0.1")
    port: int = int(os.getenv("AGRI_DB_PORT", "3306"))
    user: str = os.getenv("AGRI_DB_USER", "root")
    password: str = os.getenv("AGRI_DB_PASSWORD", "")
    database: str = os.getenv("AGRI_DB_NAME", "agri_warning")
    charset: str = "utf8mb4"


DB_CONFIG = DatabaseConfig()
LOGIN_USER = os.getenv("AGRI_LOGIN_USER", "admin")
LOGIN_PASSWORD = os.getenv("AGRI_LOGIN_PASSWORD", "123456")


@dataclass(frozen=True)
class LLMConfig:
    enabled: bool = os.getenv("AGRI_LLM_ENABLED", "false").lower() == "true"
    api_key: str = os.getenv("AGRI_LLM_API_KEY", "")
    base_url: str = os.getenv("AGRI_LLM_BASE_URL", "https://api.deepseek.com")
    model: str = os.getenv("AGRI_LLM_MODEL", "deepseek-chat")
    timeout: int = int(os.getenv("AGRI_LLM_TIMEOUT", "30"))
    max_tokens: int = int(os.getenv("AGRI_LLM_MAX_TOKENS", "600"))
    temperature: float = float(os.getenv("AGRI_LLM_TEMPERATURE", "0.3"))


LLM_CONFIG = LLMConfig()
