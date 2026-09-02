import uuid
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    backend_url: str = "http://localhost:8080"
    stream_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    camera_index: int = 0

    detection_socket_path: str = Field(
        default="/tmp/talon-detections.sock",
        description="Unix socket the perception process writes detection frames to",
    )
    enable_detections: bool = Field(
        default=True,
        description="Forward detection frames alongside video",
    )

    reconnect_initial_delay_s: float = 1.0
    reconnect_max_delay_s: float = 15.0

    @field_validator("backend_url")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()
