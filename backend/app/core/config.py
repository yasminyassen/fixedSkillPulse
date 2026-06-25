#config
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ENVIRONMENT: str = "development"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    COOKIE_SAMESITE: str = "lax"
    COOKIE_SECURE: bool = False

    # Email (SendGrid)
    SENDGRID_API_KEY: str = ""
    FROM_EMAIL: str = ""

    # GitHub OAuth
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    GITHUB_REDIRECT_URI: str = "http://localhost:8000/auth/github/callback"
    FRONTEND_URL: str = "http://localhost:5173"
    
    # Encryption for GitHub tokens
    ENCRYPTION_KEY: str = "V4b5gxkYREWRMc3NDzwbPzypjCtasGVSKzdNiSn8xSQ="
    
    # SonarQube Local
    sonar_host_url: str = "http://localhost:9000"
    sonar_token: str = ""
    sonar_scanner_path: str = ""
    sonar_scanner_timeout: int = 600
    sonar_ce_timeout: int = 180

    # Tool Paths
    GITLEAKS_PATH: str = "gitleaks"
    SEMGREP_PATH: str = "semgrep"

    # AI Configurations
    ai_mode: str = "openrouter"
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen2.5-coder:7b"
    openrouter_api_key: str = ""
    openrouter_model: str = "qwen/qwen3-14b"
    openrouter_api_url: str = "https://openrouter.ai/api/v1"
    llm_max_retries: int = 3
    llm_context_limit: int = 32000
    analysis_version: str = "v1"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()