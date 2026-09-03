import uuid
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    backend_url: str = "http://localhost:8080"
    stream_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    video_source: Literal["auto", "perception", "local"] = Field(
        default="auto",
        description=(
            "Skad brac klatki: 'perception' = z modulu C++ przez pamiec "
            "wspoldzielona, 'local' = wlasna kamera, 'auto' = modul, a gdy "
            "go nie ma, kamera"
        ),
    )
    frame_stream: Literal["raw", "annotated"] = Field(
        default="raw",
        description="Ktory strumien modulu czytac: czysty czy z ramkami",
    )
    camera_index: int = Field(
        default=0, description="Uzywane tylko przy video_source='local'"
    )

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
