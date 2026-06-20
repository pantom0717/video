"""힉스필드 생성 — provider 추상화.

provider 별 동작:
  manual : 컷별 이미지/i2v 요청 패키지(JSON)만 쓰고 사람이 직접 생성. (MVP 기본)
  mcp    : beauty-fast-gen MCP 경로로 위임하는 핸드오프 패키지를 만든다.
           ↳ 실제 MCP 호출은 에이전트(스킬)가 이 패키지를 읽어 실행한다 = 연동 지점(드롭인).
  sdk    : higgsfield-client SDK 로 백엔드가 직접 생성(크레딧 사용).

가이드/CLI 스킬 규칙 반영:
  - 이미지는 컷당 4장 (A형은 앵커 컷 먼저 → 그 job_id 를 나머지 컷 reference 로).
  - i2v 시작 프레임 = 픽한 이미지의 job_id 재사용.
  - sound: on 고정. 음악/보컬 억제는 i2v 프롬프트 문구로.
  - 엔드프레임·립싱크 미사용.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import settings
from app.models import (
    ConsistencyType,
    CutPlan,
    HiggsfieldResult,
    ImageCandidate,
    ProductionPlan,
)


# ---------------------------------------------------------------------------
# 요청 패키지 빌더 (manual / mcp 가 공유) — 컷별로 무엇을 어떻게 생성할지 결정적으로 기술
# ---------------------------------------------------------------------------
def build_image_requests(plan: ProductionPlan, frames: dict[int, str]) -> list[dict[str, Any]]:
    """컷별 이미지 생성 요청. A형이면 앵커 컷을 먼저(order=0)."""
    image_args = settings.higgsfield_image_args()
    requests: list[dict[str, Any]] = []
    anchor_index = _anchor_index(plan)

    for cut in plan.cuts:
        is_anchor = plan.consistency == ConsistencyType.A and cut.index == anchor_index
        requests.append(
            {
                "cut_index": cut.index,
                "order": 0 if is_anchor else 1,  # 앵커 먼저, 나머지는 병렬
                "is_anchor": is_anchor,
                "count": settings.higgsfield_image_count,
                "model": settings.higgsfield_image_model,
                "args": image_args,
                "prompt": _flatten(cut.image_prompt),
                # reference: B형/혼합 = 컷별 추출 프레임 / A형 비앵커 = 앵커 이미지(픽 후 job_id 주입)
                "reference_frame": frames.get(cut.index, ""),
                "reference_anchor_job_id": "",  # A형: 앵커 픽 후 채워짐
                "consistency": plan.consistency.value,
            }
        )
    requests.sort(key=lambda r: (r["order"], r["cut_index"]))
    return requests


def build_video_requests(
    plan: ProductionPlan,
    start_image_job_ids: dict[int, str],
    i2v_prompts: dict[int, str],
) -> list[dict[str, Any]]:
    """컷별 i2v 생성 요청. 시작 프레임 = 픽한 이미지 job_id."""
    video_args = settings.higgsfield_video_args()
    requests: list[dict[str, Any]] = []
    for cut in plan.cuts:
        requests.append(
            {
                "cut_index": cut.index,
                "model": settings.higgsfield_video_model,
                "args": video_args,  # mode pro, 9:16, 6s, sound on
                "prompt": _flatten(i2v_prompts.get(cut.index, cut.i2v_prompt)),
                "start_image_job_id": start_image_job_ids.get(cut.index, ""),
                "use_end_frame": False,
                "lip_sync": False,
            }
        )
    return requests


# ---------------------------------------------------------------------------
# 이미지 생성
# ---------------------------------------------------------------------------
async def generate_images(
    plan: ProductionPlan,
    frames: dict[int, str],
    job_dir: Path,
    run_generation: bool,
) -> HiggsfieldResult:
    provider = settings.higgsfield_provider.lower().strip()
    requests = build_image_requests(plan, frames)
    _write_package(job_dir / "candidates" / "image_requests.json", {"provider": provider, "requests": requests})

    if not run_generation or provider in ("manual", "mcp"):
        status = "mcp_handoff" if provider == "mcp" else "package_only"
        return HiggsfieldResult(provider=provider, status=status, package_only=True)

    if provider == "sdk":
        return await _sdk_generate_images(requests, job_dir)

    return HiggsfieldResult(provider=provider, status=f"unknown_provider:{provider}", package_only=True)


async def generate_videos(
    plan: ProductionPlan,
    start_image_job_ids: dict[int, str],
    i2v_prompts: dict[int, str],
    job_dir: Path,
    run_generation: bool,
) -> HiggsfieldResult:
    provider = settings.higgsfield_provider.lower().strip()
    requests = build_video_requests(plan, start_image_job_ids, i2v_prompts)
    _write_package(job_dir / "videos" / "video_requests.json", {"provider": provider, "requests": requests})

    if not run_generation or provider in ("manual", "mcp"):
        status = "mcp_handoff" if provider == "mcp" else "package_only"
        return HiggsfieldResult(provider=provider, status=status, package_only=True)

    if provider == "sdk":
        return await _sdk_generate_videos(requests, job_dir)

    return HiggsfieldResult(provider=provider, status=f"unknown_provider:{provider}", package_only=True)


# ---------------------------------------------------------------------------
# SDK 경로 (백엔드가 직접 생성)
# ---------------------------------------------------------------------------
async def _sdk_generate_images(requests: list[dict[str, Any]], job_dir: Path) -> HiggsfieldResult:
    import asyncio

    if not _sdk_credentials_ready():
        return HiggsfieldResult(provider="sdk", status="missing_higgsfield_credentials", package_only=True)

    import higgsfield_client  # type: ignore

    async def one(req: dict[str, Any], variant: int) -> ImageCandidate:
        args = dict(req["args"])
        args["prompt"] = req["prompt"]
        if req.get("reference_frame"):
            args["reference_image"] = req["reference_frame"]
        result = await higgsfield_client.subscribe_async(req["model"], arguments=args)
        url, job_id = _extract_image_ref(result)
        return ImageCandidate(cut_index=req["cut_index"], variant=variant, job_id=job_id, url=url)

    candidates: list[ImageCandidate] = []
    for req in requests:
        batch = await asyncio.gather(*[one(req, v) for v in range(req["count"])])
        candidates.extend(batch)

    _write_package(
        job_dir / "candidates" / "candidates_jobs.json",
        [c.model_dump() for c in candidates],
    )
    return HiggsfieldResult(provider="sdk", status="completed", package_only=False, candidates=candidates)


async def _sdk_generate_videos(requests: list[dict[str, Any]], job_dir: Path) -> HiggsfieldResult:
    if not _sdk_credentials_ready():
        return HiggsfieldResult(provider="sdk", status="missing_higgsfield_credentials", package_only=True)

    import higgsfield_client  # type: ignore

    videos: list[dict[str, Any]] = []
    for req in requests:
        args = dict(req["args"])
        args["prompt"] = req["prompt"]
        if req.get("start_image_job_id"):
            args["start_image_job_id"] = req["start_image_job_id"]
        result = await higgsfield_client.subscribe_async(req["model"], arguments=args)
        videos.append({"cut_index": req["cut_index"], "result": result})

    _write_package(job_dir / "videos" / "video_jobs.json", videos)
    return HiggsfieldResult(provider="sdk", status="completed", package_only=False, videos=videos)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _anchor_index(plan: ProductionPlan) -> int | None:
    for cut in plan.cuts:
        if cut.is_anchor:
            return cut.index
    return plan.cuts[0].index if plan.cuts else None


def _flatten(prompt: str) -> str:
    """CLI 함정 ②: 멀티라인 --prompt 는 줄바꿈에서 잘림 → 공백 한 줄로 (내용 보존)."""
    return " ".join(line.strip() for line in (prompt or "").splitlines() if line.strip())


def _sdk_credentials_ready() -> bool:
    import os

    if settings.hf_key:
        os.environ["HF_KEY"] = settings.hf_key
    if settings.hf_api_key:
        os.environ["HF_API_KEY"] = settings.hf_api_key
    if settings.hf_api_secret:
        os.environ["HF_API_SECRET"] = settings.hf_api_secret
    return bool(os.environ.get("HF_KEY") or (os.environ.get("HF_API_KEY") and os.environ.get("HF_API_SECRET")))


def _extract_image_ref(result: dict[str, Any]) -> tuple[str, str]:
    job_id = str(result.get("job_id") or result.get("id") or "")
    images = result.get("images")
    if isinstance(images, list) and images and isinstance(images[0], dict):
        return str(images[0].get("url", "")), job_id
    return str(result.get("url") or result.get("image_url") or ""), job_id


def _write_package(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
