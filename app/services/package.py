import json
from pathlib import Path

from app.models import AnalysisResult, ProductBrief


def create_higgsfield_package(
    job_dir: Path,
    brief: ProductBrief,
    analysis: AnalysisResult,
    start_frame_path: Path | None,
) -> Path:
    job_dir.mkdir(parents=True, exist_ok=True)

    package = {
        "mode": "free_manual_higgsfield_ui",
        "product": brief.model_dump(),
        "starting_frame": str(start_frame_path) if start_frame_path else None,
        "higgsfield": {
            "image_generation": {
                "count": 4,
                "prompt": analysis.image_prompt,
                "note": "Generate 4 starting images. Pick the strongest one before img-to-video.",
            },
            "img_to_video": {
                "duration_seconds": "3-4",
                "prompt": analysis.video_prompt,
                "use_end_frame": False,
                "note": "Only add an end frame if repeated generations fail.",
            },
        },
        "analysis": analysis.model_dump(),
    }

    package_path = job_dir / "higgsfield_package.json"
    package_path.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")

    (job_dir / "analysis.json").write_text(
        json.dumps(analysis.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (job_dir / "higgsfield_prompt.txt").write_text(
        "\n".join(
            [
                "[Image generation prompt - create 4]",
                analysis.image_prompt,
                "",
                "[Img to video prompt - 3 to 4 seconds]",
                analysis.video_prompt,
            ]
        ),
        encoding="utf-8",
    )
    (job_dir / "capcut_plan.txt").write_text("\n".join(analysis.capcut_plan), encoding="utf-8")
    return package_path
