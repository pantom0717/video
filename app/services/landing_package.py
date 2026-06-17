import json
from pathlib import Path

from app.models import LeadRecord


def create_landing_intake_package(lead: LeadRecord, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    package = {
        "lead_id": lead.lead_id,
        "status": lead.status,
        "brand": {
            "name": lead.brand_name,
            "instagram_url": lead.instagram_url,
            "email": lead.email,
        },
        "reference": {
            "url": lead.reference_url,
            "note": "If a reference URL is present, fetch or upload the source video before production analysis.",
        },
        "production_defaults": {
            "format": "9:16 vertical short-form ad",
            "resolution": "1080p",
            "duration": "3-4 seconds per AI clip",
            "image_variations": 4,
            "use_end_frame": False,
            "lip_sync": False,
        },
        "next_steps": [
            "Attach or fetch the reference video.",
            "Run Gemini analysis on the reference video.",
            "Extract and rank starting frames.",
            "Generate 4 Higgsfield starting images.",
            "Rank the 4 images and generate img-to-video from the winner.",
            "Create voiceover, subtitles, and final MP4 render.",
        ],
    }
    package_path = output_dir / "intake_package.json"
    package_path.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")

    brief_path = output_dir / "production_brief.txt"
    brief_path.write_text(
        "\n".join(
            [
                f"Brand: {lead.brand_name}",
                f"Instagram: {lead.instagram_url}",
                f"Reference: {lead.reference_url or 'not provided'}",
                f"Email: {lead.email}",
                f"Product: {lead.product_name or lead.brand_name}",
                f"Target customer: {lead.target_customer or 'beauty / health supplement short-form buyers'}",
                f"Main benefit: {lead.main_benefit or 'derive from brand and reference analysis'}",
                "",
                "Production rule: Do not copy the reference exactly. Extract only the hook, appeal, mood, framing, and transition energy.",
                "No JSON prompt for generation. No lip sync. No end frame unless repeated video generations fail.",
            ]
        ),
        encoding="utf-8",
    )
    return package_path
