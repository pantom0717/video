import json
from pathlib import Path

from app.models import ProductBrief, ProductionPlan


def create_higgsfield_package(
    job_dir: Path,
    brief: ProductBrief,
    plan: ProductionPlan,
    start_frame_path: Path | None,
) -> Path:
    """컷별 이미지/i2v 프롬프트 패키지 + 사람이 읽는 prompt 텍스트를 쓴다."""
    job_dir.mkdir(parents=True, exist_ok=True)

    package = {
        "mode": "cli_grade_per_cut",
        "product": brief.model_dump(),
        "starting_frame": str(start_frame_path) if start_frame_path else None,
        "consistency": plan.consistency.value,
        "consistency_needs_human": plan.consistency_needs_human,
        "defaults": {
            "image_count_per_cut": 4,
            "image_model": "nano_banana_2",
            "video_model": "kling3_0",
            "aspect": "9:16",
            "sound": "on",
            "use_end_frame": False,
            "lip_sync": False,
        },
        "cuts": [
            {
                "index": cut.index,
                "is_anchor": cut.is_anchor,
                "image_prompt": cut.image_prompt,
                "i2v_prompt": cut.i2v_prompt,
                "narration": cut.narration,
            }
            for cut in plan.cuts
        ],
    }
    package_path = job_dir / "higgsfield_package.json"
    package_path.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")

    # 사람이 바로 복붙할 수 있는 프롬프트 텍스트 (컷별)
    lines: list[str] = [f"# Consistency: {plan.consistency.value} (needs human confirm: {plan.consistency_needs_human})", ""]
    for cut in plan.cuts:
        anchor = " [ANCHOR]" if cut.is_anchor else ""
        lines += [
            f"== Cut {cut.index:02d}{anchor} ({cut.start_second:.1f}s-{cut.end_second:.1f}s) ==",
            "[Image prompt — create 4]",
            cut.image_prompt or "(none)",
            "",
            "[Img-to-video prompt — 6s, sound on]",
            cut.i2v_prompt or "(none)",
            "",
        ]
    (job_dir / "higgsfield_prompt.txt").write_text("\n".join(lines), encoding="utf-8")
    return package_path
