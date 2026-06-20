import json
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import settings
from app.models import (
    ConsistencyType,
    ImageCandidate,
    JobResult,
    LeadCreate,
    LeadRecord,
    ProductBrief,
)
from app.services import higgsfield, jobs, narration, pick, propose
from app.services.email import send_lead_notification
from app.services.frame_capture import capture_frame, extract_cut_frames
from app.services.gemini import analyze_reference
from app.services.landing_package import create_landing_intake_package
from app.services.leads import (
    create_lead,
    get_lead,
    lead_dir,
    list_leads,
    save_lead,
    update_lead_status,
)
from app.services.package import create_higgsfield_package
from app.services.storage import ensure_dirs, save_upload

app = FastAPI(title="Kiwi AI Short-Form Backend", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    ensure_dirs(settings.data_dir)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": settings.app_mode}


# ---------------------------------------------------------------------------
# Landing leads  (MVP: 폼 접수 + 운영자 메일 알림)
# ---------------------------------------------------------------------------
@app.post("/leads", response_model=LeadRecord)
def submit_landing_lead(payload: LeadCreate) -> LeadRecord:
    lead = create_lead(payload)
    package_path = create_landing_intake_package(lead, lead_dir(lead.lead_id))
    status = "reference_video_needed" if not lead.reference_url else "reference_url_received"
    lead = update_lead_status(
        lead.lead_id,
        status,
        files={
            "lead_dir": str(lead_dir(lead.lead_id)),
            "intake_package": str(package_path),
            "production_brief": str(lead_dir(lead.lead_id) / "production_brief.txt"),
        },
    )

    # 운영자에게 메일 알림 (실패해도 리드는 저장됨)
    ok, reason = send_lead_notification(lead)
    lead.notified = ok
    if not ok:
        lead.warnings.append(f"email_not_sent:{reason}")
    save_lead(lead)
    return lead


@app.get("/leads", response_model=list[LeadRecord])
def get_landing_leads() -> list[LeadRecord]:
    return list_leads()


@app.get("/leads/{lead_id}", response_model=LeadRecord)
def get_landing_lead(lead_id: str) -> LeadRecord:
    try:
        return get_lead(lead_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Lead not found") from exc


@app.get("/leads/{lead_id}/files/{filename}")
def get_lead_file(lead_id: str, filename: str) -> FileResponse:
    return _safe_file(lead_dir(lead_id), filename)


# ---------------------------------------------------------------------------
# Production: 레퍼런스 업로드 → 컷별 플랜 생성 (CLI 스킬급)
# ---------------------------------------------------------------------------
@app.post("/leads/{lead_id}/reference-video", response_model=JobResult)
async def upload_lead_reference_video(
    lead_id: str,
    reference_video: UploadFile = File(...),
    start_second: float = Form(0.0),
    run_higgsfield_generation: bool = Form(False),
) -> JobResult:
    try:
        lead = get_lead(lead_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Lead not found") from exc

    update_lead_status(lead_id, "reference_video_uploaded")
    brief = _brief_from_lead(lead)
    result = await _run_reference_pipeline(
        reference_video, brief, start_second, run_higgsfield_generation, lead_id=lead_id
    )
    update_lead_status(
        lead_id,
        result.status,
        job_id=result.job_id,
        files={"job_dir": result.files.get("job_dir", "")},
    )
    return result


@app.post("/jobs", response_model=JobResult)
async def create_job(
    reference_video: UploadFile = File(...),
    product_name: str = Form(...),
    target_customer: str = Form(""),
    main_benefit: str = Form(""),
    tone: str = Form("premium, clean, persuasive"),
    platform: str = Form("9:16 short-form social ad"),
    start_second: float = Form(0.0),
    run_higgsfield_generation: bool = Form(False),
) -> JobResult:
    brief = ProductBrief(
        product_name=product_name,
        target_customer=target_customer,
        main_benefit=main_benefit,
        tone=tone,
        platform=platform,
        start_second=start_second,
    )
    return await _run_reference_pipeline(
        reference_video, brief, start_second, run_higgsfield_generation
    )


async def _run_reference_pipeline(
    reference_video: UploadFile,
    brief: ProductBrief,
    start_second: float,
    run_generation: bool,
    lead_id: str | None = None,
) -> JobResult:
    job_id = uuid4().hex[:12]
    job_dir = jobs.job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []

    upload_path = await save_upload(reference_video, settings.data_dir / "uploads", job_id)
    if lead_id:
        (job_dir / "lead_id.txt").write_text(lead_id, encoding="utf-8")

    start_frame_path: Path | None = None
    try:
        start_frame_path = capture_frame(upload_path, job_dir / "starting_frame.jpg", start_second)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"starting_frame_capture_failed: {exc}")

    plan = await analyze_reference(upload_path, brief)

    # §2 컷별 프레임 자동 추출 (이미지 생성 reference)
    frames: dict[int, Path] = {}
    try:
        frames = extract_cut_frames(upload_path, plan.cuts, job_dir / "frames")
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"cut_frame_extract_failed: {exc}")

    jobs.save_plan(job_id, plan)
    package_path = create_higgsfield_package(job_dir, brief, plan, start_frame_path)

    # 이미지 생성(또는 패키지만) — manual/mcp 는 요청 패키지만, sdk+run 은 실제 생성
    hf = await higgsfield.generate_images(
        plan, {k: str(v) for k, v in frames.items()}, job_dir, run_generation
    )

    status = "plan_ready" if hf.package_only else "images_generated"
    return JobResult(
        job_id=job_id,
        status=status,
        upload_path=upload_path,
        start_frame_path=start_frame_path,
        plan=plan,
        higgsfield_package_path=package_path,
        higgsfield_result=hf,
        warnings=warnings,
        files={
            "job_dir": str(job_dir),
            "plan_json": str(jobs.plan_path(job_id)),
            "higgsfield_prompt_txt": str(job_dir / "higgsfield_prompt.txt"),
        },
    )


# ---------------------------------------------------------------------------
# Human gates (API)
# ---------------------------------------------------------------------------
@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    plan = _load_plan(job_id)
    return {"job_id": job_id, "plan": plan.model_dump(), "files": _job_files(job_id)}


@app.post("/jobs/{job_id}/consistency")
def set_consistency(job_id: str, consistency: str = Form(...)) -> dict:
    """§1.5 일관성 분류 게이트 — 사람이 A/B/mixed 확정."""
    plan = _load_plan(job_id)
    mapping = {"a": ConsistencyType.A, "b": ConsistencyType.B, "mixed": ConsistencyType.MIXED}
    key = consistency.strip().lower()
    if key not in mapping:
        raise HTTPException(status_code=400, detail="consistency must be A | B | mixed")
    plan.consistency = mapping[key]
    plan.consistency_needs_human = False
    anchor_index = plan.cuts[0].index if plan.cuts else None
    for cut in plan.cuts:
        cut.is_anchor = plan.consistency == ConsistencyType.A and cut.index == anchor_index
    jobs.save_plan(job_id, plan)
    return {"job_id": job_id, "consistency": plan.consistency.value}


@app.post("/jobs/{job_id}/pick")
def run_pick(job_id: str) -> dict:
    """§3.6 AI 프리셀렉트 — 컷별 베스트 추천(사람 거부권)."""
    plan = _load_plan(job_id)
    candidates = _load_candidates(job_id)
    picks = pick.prescreen(plan, candidates, jobs.job_dir(job_id))
    return {"job_id": job_id, "picks": [p.model_dump() for p in picks]}


@app.post("/jobs/{job_id}/propose-i2v")
def run_propose(job_id: str) -> dict:
    """§5.0 i2v A/B 제안표 생성 (확정 전 텍스트 제안)."""
    plan = _load_plan(job_id)
    proposals = propose.propose(plan, jobs.job_dir(job_id))
    return {"job_id": job_id, "proposals": [p.model_dump() for p in proposals]}


@app.post("/jobs/{job_id}/generate-video", response_model=None)
async def run_video(
    job_id: str,
    choices: str = Form(""),          # "1:B,2:A,..." (미지정 시 proposals.recommend)
    run_higgsfield_generation: bool = Form(False),
) -> dict:
    """§5 i2v 영상 생성 (확정된 A/B 프롬프트로). manual/mcp 는 요청 패키지만."""
    plan = _load_plan(job_id)
    job_path = jobs.job_dir(job_id)

    proposals = _load_json(job_path / "proposals.json", [])
    choice_map = _parse_choices(choices)
    i2v_prompts: dict[int, str] = {}
    for p in proposals:
        idx = int(p.get("cut_index", 0))
        chosen = choice_map.get(idx) or p.get("chosen") or p.get("recommend", "A")
        i2v_prompts[idx] = p.get("option_b" if chosen.upper() == "B" else "option_a", "")

    # 시작 프레임 = 픽한 이미지 job_id
    picks = _load_json(job_path / "picks.json", [])
    candidates = _load_candidates(job_id)
    start_jobs = _start_image_job_ids(picks, candidates)

    hf = await higgsfield.generate_videos(
        plan, start_jobs, i2v_prompts, job_path, run_higgsfield_generation
    )
    return {"job_id": job_id, "result": hf.model_dump()}


@app.post("/jobs/{job_id}/narration")
def run_narration(job_id: str) -> dict:
    """§7.5 나레이션 스크립트 + 자막 SRT 생성 (TTS 전 — 사람 승인 게이트)."""
    plan = _load_plan(job_id)
    lines = narration.make_narration(plan, jobs.job_dir(job_id))
    return {"job_id": job_id, "narration": [ln.model_dump() for ln in lines]}


@app.post("/jobs/{job_id}/tts")
def run_tts(job_id: str) -> dict:
    """승인된 narration.json 으로 컷별 TTS 음성 생성."""
    job_path = jobs.job_dir(job_id)
    raw = _load_json(job_path / "narration.json", None)
    if raw is None:
        raise HTTPException(status_code=400, detail="narration.json not found — run /narration first")
    from app.models import NarrationLine

    lines = [NarrationLine(**r) for r in raw]
    paths, warnings = narration.synthesize_tts(lines, job_path / "vo")
    return {"job_id": job_id, "audio": [str(p) for p in paths], "warnings": warnings}


@app.get("/jobs/{job_id}/files/{filename:path}")
def get_job_file(job_id: str, filename: str) -> FileResponse:
    return _safe_file(jobs.job_dir(job_id), filename)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _brief_from_lead(lead: LeadRecord) -> ProductBrief:
    return ProductBrief(
        product_name=lead.product_name or lead.brand_name,
        target_customer=lead.target_customer or "beauty / health supplement short-form buyers",
        main_benefit=lead.main_benefit or "brand-fit product appeal from the reference",
        tone="premium, clean, persuasive, social-first",
        platform="9:16 short-form social ad",
        start_second=0.0,
    )


def _load_plan(job_id: str):
    try:
        return jobs.load_plan(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Job/plan not found") from exc


def _load_candidates(job_id: str) -> list[ImageCandidate]:
    raw = _load_json(jobs.job_dir(job_id) / "candidates" / "candidates_jobs.json", [])
    out: list[ImageCandidate] = []
    for r in raw:
        try:
            out.append(ImageCandidate(**r))
        except Exception:  # noqa: BLE001
            continue
    return out


def _start_image_job_ids(picks: list[dict], candidates: list[ImageCandidate]) -> dict[int, str]:
    by_key = {(c.cut_index, c.variant): c for c in candidates}
    result: dict[int, str] = {}
    for p in picks:
        cut_index = int(p.get("cut_index", 0))
        variant = int(p.get("pick_variant", 0))
        cand = by_key.get((cut_index, variant))
        if cand:
            result[cut_index] = cand.job_id
    return result


def _parse_choices(choices: str) -> dict[int, str]:
    result: dict[int, str] = {}
    for token in (choices or "").split(","):
        token = token.strip()
        if ":" not in token:
            continue
        idx, ab = token.split(":", 1)
        if idx.strip().isdigit():
            result[int(idx)] = ab.strip().upper()
    return result


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def _job_files(job_id: str) -> dict[str, str]:
    job_path = jobs.job_dir(job_id)
    names = [
        "plan.json", "higgsfield_package.json", "higgsfield_prompt.txt",
        "picks.json", "proposals.json", "narration.json", "captions.srt",
    ]
    return {n: str(job_path / n) for n in names if (job_path / n).exists()}


def _safe_file(root: Path, filename: str) -> FileResponse:
    root = root.resolve()
    path = (root / filename).resolve()
    if not str(path).startswith(str(root)):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path)
