from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Landing / leads
# ---------------------------------------------------------------------------
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
    notified: bool = False
    warnings: list[str] = []
    files: dict[str, Any] = {}


class ProductBrief(BaseModel):
    product_name: str = Field(..., min_length=1)
    target_customer: str = ""
    main_benefit: str = ""
    tone: str = "premium, clean, persuasive"
    platform: str = "9:16 short-form social ad"
    start_second: float = 0.0
    voice_text: str = ""


# ---------------------------------------------------------------------------
# Production plan (mirrors beauty-fast-gen-cli plan.md — 가이드 §5 9항목)
# ---------------------------------------------------------------------------
class ConsistencyType(str, Enum):
    """한 영상 안에서 캐릭터가 어떻게 반복되는지 (§1.5 일관성 분류 게이트)."""

    A = "A"          # 같은 주인공이 계속 — 앵커 신원 락
    B = "B"          # 컷마다 다른 캐릭터 — 스타일 락만
    MIXED = "mixed"  # 한 명만 반복 + 나머지는 매번 달라짐
    UNKNOWN = "unknown"


class TopicSuggestion(BaseModel):
    topic: str
    hook: str = ""  # 첫 3초 후킹 문장


class CutPlan(BaseModel):
    """레퍼런스 컷별 구성 + 컷별 이미지/i2v 프롬프트 (일반 텍스트, JSON 프롬프트 아님)."""

    index: int
    start_second: float = 0.0
    end_second: float = 0.0
    screen: str = ""        # 화면 구성
    camera: str = ""        # 카메라 구도
    motion: str = ""        # 캐릭터/오브젝트 움직임
    background: str = ""
    lighting: str = ""
    narration: str = ""     # 컷 나레이션 (한국어)
    subtitle: str = ""
    emotion: str = ""       # 시청자가 느끼는 감정
    image_prompt: str = ""  # §7-2 이미지 프롬프트 기본형
    i2v_prompt: str = ""    # §8-2 image-to-video 프롬프트 기본형
    is_anchor: bool = False  # A형에서 앵커(주인공 첫 등장) 컷인지


class ProductionPlan(BaseModel):
    source: str
    video_type: str = ""
    first_3_seconds: str = ""
    success_structure: str = ""

    # §1.5 게이트 — Gemini 는 제안만, 최종 분류는 사람이 확정
    consistency: ConsistencyType = ConsistencyType.UNKNOWN
    consistency_reason: str = ""
    consistency_needs_human: bool = True

    cuts: list[CutPlan] = []
    narration_structure: str = ""
    localization_points: list[str] = []
    topic_suggestions: list[TopicSuggestion] = []
    pipeline_notes: str = ""

    # 빠른 요약용 (랜딩/브리프)
    summary: str = ""
    appeal_points: list[str] = []
    visual_direction: str = ""


# ---------------------------------------------------------------------------
# Generation — image candidates / picks / i2v proposals
# ---------------------------------------------------------------------------
class ImageCandidate(BaseModel):
    cut_index: int
    variant: int            # 0..3
    job_id: str = ""        # 힉스필드 job_id → i2v 시작 프레임으로 재사용
    url: str = ""
    local_path: str = ""


class CutPick(BaseModel):
    """§3.6 AI 프리셀렉트 결과 (사람 거부권 게이트)."""

    cut_index: int
    pick_variant: int = 0
    ranking: list[int] = []
    reason: str = ""
    confidence: float = 0.0
    needs_human: bool = False


class I2VProposal(BaseModel):
    """§5.0 i2v A/B 제안표 (생성 전 텍스트 제안 — 최종 확정은 사람)."""

    cut_index: int
    option_a: str = ""              # plan 의 i2v 프롬프트 그대로 (충실)
    option_b: str = ""             # Gemini 가 작문 (심한 비포→과장된 변화→완벽한 애프터)
    recommend: str = "A"           # "A" | "B"
    rationale: str = ""
    self_check: dict[str, str] = {}  # 전후해소/첫3초후킹/실행정보/AI티/endFrame
    chosen: str = ""               # 사람이 확정한 "A" | "B"


class NarrationLine(BaseModel):
    cut_index: int
    start_second: float = 0.0
    end_second: float = 0.0
    text: str = ""
    char_limit: int = 0
    over_limit: bool = False


# ---------------------------------------------------------------------------
# Generation results
# ---------------------------------------------------------------------------
class HiggsfieldResult(BaseModel):
    provider: str
    status: str
    package_only: bool = True
    candidates: list[ImageCandidate] = []
    videos: list[dict[str, Any]] = []
    raw: list[dict[str, Any]] = []


class JobResult(BaseModel):
    job_id: str
    status: str
    upload_path: Path | None = None
    start_frame_path: Path | None = None
    plan: ProductionPlan
    higgsfield_package_path: Path | None = None
    higgsfield_result: HiggsfieldResult | None = None
    voice_path: Path | None = None
    warnings: list[str] = []
    files: dict[str, Any] = {}
