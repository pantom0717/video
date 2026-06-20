"""제작 작업(job) 영속화 — plan.json 을 단일 출처로 읽고 쓴다.

각 job 디렉터리(`data/outputs/<job_id>/`) 구성:
  plan.json                 ← ProductionPlan (게이트마다 갱신)
  starting_frame.jpg        ← 대표 시작 프레임
  frames/cutNN.png          ← 컷별 추출 프레임 (§2)
  candidates/...            ← 이미지 후보 (§3)
  picks.json                ← 프리셀렉트 결과 (§3.6)
  proposals.json            ← i2v A/B 제안 (§5.0)
  narration.json captions.srt vo/   ← 나레이션 (§7.5)
  videos/segNN.mp4          ← i2v 결과 (§5)
"""
from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.models import ProductionPlan


def outputs_root() -> Path:
    return settings.data_dir / "outputs"


def job_dir(job_id: str) -> Path:
    return outputs_root() / job_id


def plan_path(job_id: str) -> Path:
    return job_dir(job_id) / "plan.json"


def save_plan(job_id: str, plan: ProductionPlan) -> Path:
    path = plan_path(job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_plan(job_id: str) -> ProductionPlan:
    path = plan_path(job_id)
    if not path.exists():
        raise FileNotFoundError(job_id)
    return ProductionPlan.model_validate_json(path.read_text(encoding="utf-8"))


def list_jobs() -> list[str]:
    root = outputs_root()
    if not root.exists():
        return []
    return sorted((p.parent.name for p in root.glob("*/plan.json")), reverse=True)
