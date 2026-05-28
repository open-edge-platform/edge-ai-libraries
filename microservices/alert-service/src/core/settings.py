"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=True,
    )

    # Service
    APP_NAME: str = "Alert Service"
    API_V1_PREFIX: str = "/api/v1"
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = False
    CONFIG_PATH: str = "config/config.yaml"

    # MQTT
    MQTT_MODE: str = "embedded"  # "embedded" or "external"
    MQTT_HOST: str = ""
    MQTT_PORT: int = 1883
    MQTT_USERNAME: str = ""
    MQTT_PASSWORD: str = ""

    @property
    def mqtt_broker(self) -> str:
        """Resolve the effective MQTT broker hostname."""
        if self.MQTT_MODE == "embedded":
            return "mqtt"  # docker compose service name
        return self.MQTT_HOST

    # Webhook
    WEBHOOK_URL: str = ""

    # Delivery handlers override (comma-separated: log,mqtt,webhook)
    DELIVERY_HANDLERS: str = ""


settings = Settings()
