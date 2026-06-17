from pathlib import Path
from typing import Any
from datetime import datetime

from pydantic import BaseModel, Field


class LeadCreate(BaseModel):
    brand_name: str = Field(..., min_length=1)
    instagram_url: str = Field(..., min_length=1)
    email: str = Field(..., min_length=3)
    reference_url: str = ""
    product_name: str = ""
    target_customer: str = ""
    main_benefit: str = ""
    language: str = "ko"
    notes: str = ""


class LeadRecord(LeadCreate):
    lead_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    job_id: str | None = None
    warnings: list[str] = []
    files: dict[str, Any] = {}


class ProductBrief(BaseModel):
    product_name: str = Field(..., min_length=1)
    target_customer: str = ""
    main_benefit: str = ""
    tone: str = "premium, clean, persuasive"
    platform: str = "short-form social ad"
    start_second: float = 0.0
    voice_text: str = ""


class AnalysisResult(BaseModel):
    source: str
    summary: str
    appeal_points: list[str]
    visual_direction: str
    image_prompt: str
    video_prompt: str
    capcut_plan: list[str]


class HiggsfieldResult(BaseModel):
    provider: str
    status: str
    image_results: list[dict[str, Any]] = []
    selected_image: dict[str, Any] | None = None
    video_result: dict[str, Any] | None = None
    package_only: bool = True


class JobResult(BaseModel):
    job_id: str
    status: str
    upload_path: Path
    start_frame_path: Path | None
    analysis: AnalysisResult
    higgsfield_package_path: Path
    higgsfield_result: HiggsfieldResult | None = None
    voice_path: Path | None
    warnings: list[str] = []
    files: dict[str, Any] = {}
