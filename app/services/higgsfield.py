import asyncio
import os
from pathlib import Path
from typing import Any

from app.config import settings
from app.models import AnalysisResult, HiggsfieldResult


async def run_higgsfield(
    analysis: AnalysisResult,
    start_frame_path: Path | None,
    run_generation: bool,
) -> HiggsfieldResult:
    provider = settings.higgsfield_provider.lower().strip()
    if not run_generation or provider == "manual":
        return HiggsfieldResult(
            provider=provider,
            status="package_only",
            package_only=True,
        )
    if provider == "sdk":
        return await _run_higgsfield_sdk(analysis, start_frame_path)
    if provider == "cli":
        return await _run_higgsfield_cli_plan()
    return HiggsfieldResult(
        provider=provider,
        status=f"unknown_provider:{provider}",
        package_only=True,
    )


async def _run_higgsfield_sdk(
    analysis: AnalysisResult,
    start_frame_path: Path | None,
) -> HiggsfieldResult:
    if settings.hf_key:
        os.environ["HF_KEY"] = settings.hf_key
    if settings.hf_api_key:
        os.environ["HF_API_KEY"] = settings.hf_api_key
    if settings.hf_api_secret:
        os.environ["HF_API_SECRET"] = settings.hf_api_secret

    if not (os.environ.get("HF_KEY") or (os.environ.get("HF_API_KEY") and os.environ.get("HF_API_SECRET"))):
        return HiggsfieldResult(
            provider="sdk",
            status="missing_higgsfield_credentials",
            package_only=True,
        )

    import higgsfield_client

    image_args = settings.higgsfield_image_args()
    image_args["prompt"] = analysis.image_prompt

    async def create_image(seed_offset: int) -> dict[str, Any]:
        args = dict(image_args)
        if "seed" in args and isinstance(args["seed"], int) and args["seed"] >= 0:
            args["seed"] = args["seed"] + seed_offset
        return await higgsfield_client.subscribe_async(
            settings.higgsfield_image_model,
            arguments=args,
        )

    image_results = await asyncio.gather(
        *[create_image(index) for index in range(settings.higgsfield_image_count)]
    )
    selected_image = _pick_first_image(image_results)

    video_result: dict[str, Any] | None = None
    if selected_image:
        image_url = selected_image.get("url") or selected_image.get("image_url")
        if not image_url and start_frame_path:
            image_url = await higgsfield_client.upload_file_async(str(start_frame_path))

        video_args = settings.higgsfield_video_args()
        video_args["prompt"] = analysis.video_prompt
        if image_url:
            video_args["image_url"] = image_url
        video_result = await higgsfield_client.subscribe_async(
            settings.higgsfield_video_model,
            arguments=video_args,
        )

    return HiggsfieldResult(
        provider="sdk",
        status="completed",
        image_results=image_results,
        selected_image=selected_image,
        video_result=video_result,
        package_only=False,
    )


async def _run_higgsfield_cli_plan() -> HiggsfieldResult:
    return HiggsfieldResult(
        provider="cli",
        status="cli_mode_requires_local_higgsfield_login_and_command_mapping",
        package_only=True,
    )


def _pick_first_image(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    for result in results:
        images = result.get("images")
        if isinstance(images, list) and images:
            first = images[0]
            if isinstance(first, dict):
                return first
        if "url" in result or "image_url" in result:
            return result
    return None
