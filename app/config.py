import json
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_mode: str = "free"
    data_dir: Path = Path("data")
    cors_origins: str = (
        "https://landing-eight-black-83.vercel.app,"
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:5500,http://127.0.0.1:5500"
    )

    # --- Gemini (analysis / planning / pick / propose / narration) ---
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # --- Higgsfield generation ---
    # provider: manual | mcp | sdk
    #   manual : 컷별 프롬프트 패키지만 만들고 사람이 직접 생성 (MVP 기본)
    #   mcp    : beauty-fast-gen MCP 경로로 위임 (연동 지점 — 드롭인)
    #   sdk    : higgsfield-client SDK 로 백엔드가 직접 생성
    higgsfield_provider: str = "manual"
    higgsfield_run_by_default: bool = False
    hf_key: str = ""
    hf_api_key: str = ""
    hf_api_secret: str = ""
    # 운영 모델 (가이드/CLI 스킬 기준)
    higgsfield_image_model: str = "nano_banana_2"
    higgsfield_video_model: str = "kling3_0"
    higgsfield_image_count: int = 4
    higgsfield_image_args_json: str = '{"aspect":"9:16","resolution":"2k"}'
    higgsfield_video_args_json: str = '{"mode":"pro","aspect":"9:16","duration":6,"sound":"on"}'

    # --- Narration / TTS ---
    elevenlabs_api_key: str = ""
    elevenlabs_model_id: str = "eleven_v3"
    elevenlabs_voice_id: str = ""

    # --- Email (lead notification) ---
    # provider: console | smtp | resend
    email_provider: str = "console"
    notify_email: str = ""               # 우리(운영자) 수신 메일 — 폼 신청이 여기로 옴
    email_from: str = "kiwi-bot@localhost"
    # SMTP (Gmail 앱 비밀번호 등 — 무료)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    # Resend (무료 티어)
    resend_api_key: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    def higgsfield_image_args(self) -> dict[str, Any]:
        return json.loads(self.higgsfield_image_args_json or "{}")

    def higgsfield_video_args(self) -> dict[str, Any]:
        return json.loads(self.higgsfield_video_args_json or "{}")

    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
