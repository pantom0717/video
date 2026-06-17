import json
from pathlib import Path

from app.config import settings
from app.models import AnalysisResult, ProductBrief


async def analyze_reference(video_path: Path, brief: ProductBrief) -> AnalysisResult:
    if settings.gemini_api_key:
        try:
            return await _analyze_with_gemini(video_path, brief)
        except Exception:
            return _fallback_analysis(brief, source="local_fallback_after_gemini_error")
    return _fallback_analysis(brief, source="local_fallback_no_api_key")


async def _analyze_with_gemini(video_path: Path, brief: ProductBrief) -> AnalysisResult:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    uploaded = client.files.upload(file=str(video_path))

    prompt = f"""
You are planning a short AI product ad from a reference video.
Do not copy the reference exactly. Extract only appeal, mood, framing, motion, and transition language.

Product:
- name: {brief.product_name}
- target customer: {brief.target_customer}
- main benefit: {brief.main_benefit}
- tone: {brief.tone}
- platform: {brief.platform}

Return strict JSON with:
summary, appeal_points, visual_direction, image_prompt, video_prompt, capcut_plan.
Use natural-language prompts, not JSON prompts for Higgsfield.
No lip sync. No end frame unless absolutely necessary.
"""

    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=[uploaded, prompt],
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    data = json.loads(response.text or "{}")
    return AnalysisResult(
        source="gemini_api",
        summary=data.get("summary", ""),
        appeal_points=list(data.get("appeal_points", [])),
        visual_direction=data.get("visual_direction", ""),
        image_prompt=data.get("image_prompt", ""),
        video_prompt=data.get("video_prompt", ""),
        capcut_plan=list(data.get("capcut_plan", [])),
    )


def _fallback_analysis(brief: ProductBrief, source: str) -> AnalysisResult:
    target = brief.target_customer or "the target customer"
    benefit = brief.main_benefit or "the clearest product benefit"
    mood = brief.tone

    image_prompt = (
        f"Create a polished starting frame for a short product promotion video. "
        f"The hero product is {brief.product_name}. Show the product clearly in the foreground, "
        f"with a composition inspired by the reference video's opening mood and framing, but not copied. "
        f"Prioritize {benefit} for {target}. The frame should feel {mood}, clean, commercially usable, "
        f"with realistic lighting, strong product visibility, and enough negative space for subtitles."
    )
    video_prompt = (
        f"Animate this starting image into a 3 to 4 second product ad shot. "
        f"Use smooth camera movement, subtle product reveal, premium lighting shift, and a clear focus on {benefit}. "
        f"Keep the motion natural and stable. Do not add lip sync. Do not require an end frame."
    )
    return AnalysisResult(
        source=source,
        summary=(
            "Fallback plan: use the reference as a creative direction source only. "
            "Carry over the opening frame discipline, mood, pacing, and ad-like clarity."
        ),
        appeal_points=[
            benefit,
            "Fast viewer understanding in the first second",
            "Clean product visibility",
            "Short-form ad pacing",
        ],
        visual_direction=(
            f"{mood} product-focused frame, clear hero object, simple background, "
            "commercial lighting, smooth 3-4 second motion."
        ),
        image_prompt=image_prompt,
        video_prompt=video_prompt,
        capcut_plan=[
            "Place the generated 3-4 second clip first as the hook.",
            "Add voiceover and subtitles immediately, with product name visible early.",
            "Use quick cuts only if they support the main benefit.",
            "End with product name, benefit, and a simple call to action.",
        ],
    )
