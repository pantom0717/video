import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.config import settings
from app.models import LeadCreate, LeadRecord


def create_lead(payload: LeadCreate) -> LeadRecord:
    now = datetime.now(UTC)
    lead = LeadRecord(
        **payload.model_dump(),
        lead_id=uuid4().hex[:12],
        status="lead_received",
        created_at=now,
        updated_at=now,
    )
    save_lead(lead)
    return lead


def list_leads() -> list[LeadRecord]:
    root = _lead_root()
    leads: list[LeadRecord] = []
    for path in sorted(root.glob("*/lead.json"), reverse=True):
        leads.append(LeadRecord.model_validate_json(path.read_text(encoding="utf-8")))
    return leads


def get_lead(lead_id: str) -> LeadRecord:
    path = _lead_path(lead_id)
    if not path.exists():
        raise FileNotFoundError(lead_id)
    return LeadRecord.model_validate_json(path.read_text(encoding="utf-8"))


def save_lead(lead: LeadRecord) -> None:
    lead.updated_at = datetime.now(UTC)
    path = _lead_path(lead.lead_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(lead.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")


def update_lead_status(
    lead_id: str,
    status: str,
    *,
    job_id: str | None = None,
    warning: str | None = None,
    files: dict[str, str] | None = None,
) -> LeadRecord:
    lead = get_lead(lead_id)
    lead.status = status
    if job_id is not None:
        lead.job_id = job_id
    if warning:
        lead.warnings.append(warning)
    if files:
        lead.files.update(files)
    save_lead(lead)
    return lead


def lead_dir(lead_id: str) -> Path:
    return _lead_root() / lead_id


def _lead_root() -> Path:
    return settings.data_dir / "leads"


def _lead_path(lead_id: str) -> Path:
    return _lead_root() / lead_id / "lead.json"
