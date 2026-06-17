from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import settings
from app.models import JobResult, LeadCreate, LeadRecord, ProductBrief
from app.services.frame_capture import capture_frame
from app.services.gemini import analyze_reference
from app.services.higgsfield import run_higgsfield
from app.services.landing_package import create_landing_intake_package
from app.services.leads import create_lead, get_lead, lead_dir, list_leads, update_lead_status
from app.services.package import create_higgsfield_package
from app.services.storage import ensure_dirs, save_upload
from app.services.voice import create_voiceover

app = FastAPI(title="AI Product Video Backend", version="0.1.0")
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


@app.post("/leads", response_model=LeadRecord)
def submit_landing_lead(payload: LeadCreate) -> LeadRecord:
    lead = create_lead(payload)
    package_path = create_landing_intake_package(lead, lead_dir(lead.lead_id))
    status = "reference_video_needed" if not lead.reference_url else "reference_url_received"
    return update_lead_status(
        lead.lead_id,
        status,
        files={
            "lead_dir": str(lead_dir(lead.lead_id)),
            "intake_package": str(package_path),
            "production_brief": str(lead_dir(lead.lead_id) / "production_brief.txt"),
        },
    )


@app.get("/leads", response_model=list[LeadRecord])
def get_landing_leads() -> list[LeadRecord]:
    return list_leads()


@app.get("/leads/{lead_id}", response_model=LeadRecord)
def get_landing_lead(lead_id: str) -> LeadRecord:
    try:
        return get_lead(lead_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Lead not found") from exc


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
    product_name = lead.product_name or lead.brand_name
    target_customer = lead.target_customer or "beauty / health supplement short-form buyers"
    main_benefit = lead.main_benefit or "brand-fit product appeal from the reference"
    voice_text = f"{product_name}, 지금 가장 빠르게 눈에 띄는 브랜드 숏폼으로 보여드립니다."

    result = await _run_uploaded_reference_job(
        reference_video=reference_video,
        product_name=product_name,
        target_customer=target_customer,
        main_benefit=main_benefit,
        tone="premium, clean, persuasive, social-first",
        platform="9:16 short-form social ad",
        start_second=start_second,
        voice_text=voice_text,
        run_higgsfield_generation=run_higgsfield_generation,
        lead_id=lead_id,
    )
    update_lead_status(
        lead_id,
        result.status,
        job_id=result.job_id,
        files={
            "job_dir": result.files.get("job_dir", ""),
            "higgsfield_prompt_txt": result.files.get("higgsfield_prompt_txt", ""),
            "capcut_plan_txt": result.files.get("capcut_plan_txt", ""),
        },
    )
    return result


@app.get("/leads/{lead_id}/files/{filename}")
def get_lead_file(lead_id: str, filename: str) -> FileResponse:
    root = lead_dir(lead_id).resolve()
    path = (root / filename).resolve()
    if not str(path).startswith(str(root)):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path)


@app.post("/jobs", response_model=JobResult)
async def create_job(
    reference_video: UploadFile = File(...),
    product_name: str = Form(...),
    target_customer: str = Form(""),
    main_benefit: str = Form(""),
    tone: str = Form("premium, clean, persuasive"),
    platform: str = Form("short-form social ad"),
    start_second: float = Form(0.0),
    voice_text: str = Form(""),
    run_higgsfield_generation: bool = Form(False),
) -> JobResult:
    return await _run_uploaded_reference_job(
        reference_video=reference_video,
        product_name=product_name,
        target_customer=target_customer,
        main_benefit=main_benefit,
        tone=tone,
        platform=platform,
        start_second=start_second,
        voice_text=voice_text,
        run_higgsfield_generation=run_higgsfield_generation,
    )


async def _run_uploaded_reference_job(
    reference_video: UploadFile,
    product_name: str,
    target_customer: str,
    main_benefit: str,
    tone: str,
    platform: str,
    start_second: float,
    voice_text: str,
    run_higgsfield_generation: bool,
    lead_id: str | None = None,
) -> JobResult:
    job_id = uuid4().hex[:12]
    job_dir = settings.data_dir / "outputs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    brief = ProductBrief(
        product_name=product_name,
        target_customer=target_customer,
        main_benefit=main_benefit,
        tone=tone,
        platform=platform,
        start_second=start_second,
        voice_text=voice_text,
    )

    warnings: list[str] = []
    upload_path = await save_upload(reference_video, settings.data_dir / "uploads", job_id)
    if lead_id:
        (job_dir / "lead_id.txt").write_text(lead_id, encoding="utf-8")

    start_frame_path: Path | None = None
    try:
        start_frame_path = capture_frame(upload_path, job_dir / "starting_frame.jpg", start_second)
    except Exception as exc:
        warnings.append(f"Starting frame capture failed: {exc}")

    analysis = await analyze_reference(upload_path, brief)
    package_path = create_higgsfield_package(job_dir, brief, analysis, start_frame_path)
    should_run_higgsfield = run_higgsfield_generation or settings.higgsfield_run_by_default
    higgsfield_result = await run_higgsfield(analysis, start_frame_path, should_run_higgsfield)

    voice_path: Path | None = None
    if voice_text.strip():
        try:
            voice_path = create_voiceover(job_dir / "voiceover.wav", voice_text)
        except Exception as exc:
            warnings.append(f"Voice generation failed: {exc}")

    return JobResult(
        job_id=job_id,
        status="higgsfield_generation_completed" if not higgsfield_result.package_only else "ready_for_higgsfield_ui",
        upload_path=upload_path,
        start_frame_path=start_frame_path,
        analysis=analysis,
        higgsfield_package_path=package_path,
        higgsfield_result=higgsfield_result,
        voice_path=voice_path,
        warnings=warnings,
        files={
            "job_dir": str(job_dir),
            "analysis_json": str(job_dir / "analysis.json"),
            "higgsfield_prompt_txt": str(job_dir / "higgsfield_prompt.txt"),
            "capcut_plan_txt": str(job_dir / "capcut_plan.txt"),
        },
    )


@app.get("/jobs/{job_id}/files/{filename}")
def get_job_file(job_id: str, filename: str) -> FileResponse:
    job_dir = settings.data_dir / "outputs" / job_id
    path = (job_dir / filename).resolve()
    if not str(path).startswith(str(job_dir.resolve())):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path)
