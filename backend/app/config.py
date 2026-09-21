from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Telegram Bots (split by function)
    bot_token_auth: str = ""      # tgsell_auth_bot — Login Widget
    bot_token_alerts: str = ""     # tgsell_alert_bot — deal notifications (aiogram)
    bot_token_stats: str = ""      # tgsell_stats_bot — Bot API stats (getChat, etc.)
    telegram_api_id: int = 0
    telegram_api_hash: str = ""
    telegram_phone: str = ""
    telethon_session_string: str = ""

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""

    # Database
    database_url: str = "postgresql+asyncpg://tgsell:tgsell@localhost:5432/tgsell"
    redis_url: str = "redis://localhost:6379/0"

    @property
    def async_database_url(self) -> str:
        url = self.database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    # JWT
    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # TRON
    tron_network: str = "nile"  # nile (testnet) or mainnet
    tron_api_key: str = ""
    tron_master_wallet_address: str = ""
    tron_master_wallet_private_key: str = ""
    usdt_contract_address: str = "TXYZopYRdj2D9XRtbG411XZZ3kM5VkAeBf"  # Nile testnet USDT
    encryption_key: str = "change-me-32-byte-encryption-key!"

    # Service
    service_fee_percent: float = 3.0
    payment_timeout_hours: int = 2
    transfer_timeout_hours: int = 48
    frontend_url: str = "http://localhost:5173"
    admin_group_id: int = 0  # Telegram group chat_id for admin notifications
    alerts_bot_username: str = "tgsell_alert_bot"
    # Telegram user_id of the platform admin (for /reauth and other privileged bot commands)
    admin_telegram_id: int = 0

    # AI Analysis (Groq — free Llama 3.3 70B)
    groq_api_key: str = ""

    # Autonomous agents (see automation/agents/*.md) — shared secret an agent's
    # cloud routine presents when calling POST /agent/report to relay its
    # summary into the admin Telegram group. Unset = endpoint stays disabled.
    agent_report_secret: str = ""
    # Fine-grained GitHub PAT (Issues: write) used by alert_service_down() to
    # open a triage issue for the developer agent. Unset = Telegram-only alerts,
    # unchanged from before.
    github_token: str = ""
    github_repo: str = "RenatKost/tgsell"
    # Anthropic API key the backend uses to power the interactive developer-
    # agent chat (bot/main.py) — separate from any Claude Code session, this
    # is the backend calling the Claude API directly so the chat works 24/7
    # on Railway regardless of whether anyone's laptop is on.
    anthropic_api_key: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
