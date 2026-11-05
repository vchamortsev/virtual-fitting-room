"""Настройки читаются из окружения и файла .env в корне проекта."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Path("data")
    api_keys: str = "local-dev-key"
    host: str = "127.0.0.1"
    port: int = 8080
    cors_origins: str = "*"
    default_model: str = "auto"
    max_upload_mb: int = 12
    retention_hours: int = 48
    rate_limit_per_minute: int = 30
    public_base_url: str = ""

    fashn_weights_dir: Path = Path("weights/fashn-vton-1.5")
    fashn_device: str = ""

    enable_catvton_flux: bool = False
    catvton_base_repo: str = "black-forest-labs/FLUX.1-dev"
    catvton_fill_repo: str = "xiaozaa/flux1-fill-dev-diffusers"
    catvton_lora_repo: str = "xiaozaa/catvton-flux-lora-alpha"
    catvton_lora_weight: str = "pytorch_lora_weights.safetensors"
    catvton_offload: bool = True
    catvton_width: int = 576
    catvton_height: int = 768
    segformer_repo: str = "mattmdjaga/segformer_b2_clothes"

    @property
    def parsed_api_keys(self) -> set[str]:
        return {item.strip() for item in self.api_keys.split(",") if item.strip()}

    @property
    def parsed_cors_origins(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
