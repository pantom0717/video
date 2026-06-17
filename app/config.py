from pathlib import Path
from typing import Any
import json

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_mode: str = "free"
    data_dir: Path = Path("data")
    cors_origins: str = "https://landing-eight-black-83.vercel.app,http://localhost:3000,http://127.0.0.1:3000"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    higgsfield_provider: str = "manual"
    higgsfield_run_by_default: bool = False
    hf_key: str = ""
    hf_api_key: str = ""
    hf_api_secret: str = ""
    higgsfield_image_model: str = "bytedance/seedream/v4/text-to-image"
    higgsfield_video_model: str = "bytedance/seedance/v1/image-to-video"
    higgsfield_image_count: int = 4
    higgsfield_image_args_json: str = '{"resolution":"2K","aspect_ratio":"16:9","camera_fixed":false}'
    higgsfield_video_args_json: str = '{"duration":5,"resolution":"720p","camera_fixed":false}'

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    def higgsfield_image_args(self) -> dict[str, Any]:
        return json.loads(self.higgsfield_image_args_json or "{}")

    def higgsfield_video_args(self) -> dict[str, Any]:
        return json.loads(self.higgsfield_video_args_json or "{}")

    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
