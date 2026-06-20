"""레퍼런스 분석 → ProductionPlan (beauty-fast-gen-cli analyze_reference 대응).

zoom-in-skin-handover 가이드 §5(9항목) 기준으로 컷별 구성 + 컷별 이미지/i2v
프롬프트(일반 텍스트)를 만든다. Gemini 키가 없거나 실패하면 결정적 fallback 으로 떨어진다.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.config import settings
from app.models import (
    ConsistencyType,
    CutPlan,
    ProductBrief,
    ProductionPlan,
    TopicSuggestion,
)

# 가이드 §7-2 이미지 프롬프트 기본형 / §8-2 i2v 프롬프트 기본형 — Gemini 가 이 골격을 따르게 한다.
_PLAN_SCHEMA_HINT = """
Return STRICT JSON (no markdown) with this shape:
{
  "video_type": "3D animation | character personification | life-hack | product-morph | info | shock-hook ...",
  "first_3_seconds": "what is on screen in the first 3s and why a viewer stops",
  "success_structure": "why this reference works (known problem, broad audience, easy, strong visual change, save/share/comment trigger)",
  "consistency": "A | B | mixed",
  "consistency_reason": "one line: is there a single recurring main character, or a different character per cut?",
  "narration_structure": "first line -> problem -> process -> twist/change -> info -> CTA",
  "localization_points": ["how to adapt subject/tone/habit/product/humor/subtitle tone for Korean viewers"],
  "topic_suggestions": [{"topic": "...", "hook": "first-3s hook line (Korean)"} , ... 10 items],
  "pipeline_notes": "image -> i2v -> edit notes",
  "summary": "1-2 sentence plan summary (Korean ok)",
  "appeal_points": ["..."],
  "visual_direction": "overall tone/mood/lighting",
  "cuts": [
    {
      "index": 1,
      "start_second": 0.0,
      "end_second": 3.0,
      "screen": "...", "camera": "...", "motion": "...", "background": "...", "lighting": "...",
      "narration": "Korean one line for this cut",
      "subtitle": "Korean subtitle",
      "emotion": "what the viewer feels",
      "image_prompt": "PLAIN TEXT image prompt (NOT json). Follow: A highly detailed 3D animated scene of <subject>, <situation>, <expression/motion>, <background>, <lighting>, <colors>, <camera>, <texture>, <visual hook>, vertical 9:16 composition, viral short-form 3D animation style, clear main subject, strong visual contrast, no text, no watermark. Add consistency phrase appropriate to the consistency type.",
      "i2v_prompt": "PLAIN TEXT image-to-video prompt (NOT json). Follow the labeled-section form: Animate this image into a short vertical 9:16 3D animation. Camera movement: ... Main object movement: ... Character expression: ... Scene action: ... Visual effect: ... Motion style: dynamic, satisfying, viral short-form. Keep the same character design, object shape, background, lighting, and overall visual tone. No text, no subtitles, no watermark. No background music, no vocal (keep sound effects only).",
      "is_anchor": false
    }
  ]
}
Rules: Do NOT copy the reference exactly — extract only appeal/mood/framing/motion/transition.
No lip sync. No end frame unless absolutely necessary. Korean for narration/subtitle/hook.
If a single main character recurs across cuts set consistency=A and mark the first appearance cut is_anchor=true.
"""


async def analyze_reference(video_path: Path, brief: ProductBrief) -> ProductionPlan:
    if settings.gemini_api_key:
        try:
            return await _analyze_with_gemini(video_path, brief)
        except Exception as exc:  # noqa: BLE001
            plan = _fallback_plan(brief, source="local_fallback_after_gemini_error")
            plan.pipeline_notes = f"{plan.pipeline_notes} (gemini error: {exc})".strip()
            return plan
    return _fallback_plan(brief, source="local_fallback_no_api_key")


async def _analyze_with_gemini(video_path: Path, brief: ProductBrief) -> ProductionPlan:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    uploaded = client.files.upload(file=str(video_path))

    prompt = f"""
You are planning a Korean AI short-form ad from a reference video for a beauty / health-supplement brand.
Analyze the reference the way zoom_in_skin operates: find why it works, then localize — do not copy it.

Product brief:
- name: {brief.product_name}
- target customer: {brief.target_customer}
- main benefit: {brief.main_benefit}
- tone: {brief.tone}
- platform: {brief.platform}

{_PLAN_SCHEMA_HINT}
"""

    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=[uploaded, prompt],
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    data = json.loads(response.text or "{}")
    return _plan_from_data(data, source="gemini_api")


def _plan_from_data(data: dict, source: str) -> ProductionPlan:
    cuts: list[CutPlan] = []
    for raw in data.get("cuts", []) or []:
        try:
            cuts.append(CutPlan(**{k: raw.get(k) for k in CutPlan.model_fields if raw.get(k) is not None}))
        except Exception:  # noqa: BLE001 - 한 컷이 깨져도 나머지는 살린다
            continue
    if not cuts:
        cuts = _default_cuts()

    topics = [
        TopicSuggestion(topic=t.get("topic", ""), hook=t.get("hook", ""))
        for t in (data.get("topic_suggestions", []) or [])
        if isinstance(t, dict)
    ]

    consistency = _coerce_consistency(data.get("consistency"))
    return ProductionPlan(
        source=source,
        video_type=data.get("video_type", ""),
        first_3_seconds=data.get("first_3_seconds", ""),
        success_structure=data.get("success_structure", ""),
        consistency=consistency,
        consistency_reason=data.get("consistency_reason", ""),
        consistency_needs_human=True,  # §1.5 항상 사람이 최종 확정
        cuts=cuts,
        narration_structure=data.get("narration_structure", ""),
        localization_points=list(data.get("localization_points", []) or []),
        topic_suggestions=topics,
        pipeline_notes=data.get("pipeline_notes", ""),
        summary=data.get("summary", ""),
        appeal_points=list(data.get("appeal_points", []) or []),
        visual_direction=data.get("visual_direction", ""),
    )


def _coerce_consistency(value: object) -> ConsistencyType:
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("a", "A"):
            return ConsistencyType.A
        if v in ("b", "B"):
            return ConsistencyType.B
        if v == "mixed":
            return ConsistencyType.MIXED
    return ConsistencyType.UNKNOWN


def _default_cuts() -> list[CutPlan]:
    return [
        CutPlan(index=1, start_second=0.0, end_second=3.0, is_anchor=True),
        CutPlan(index=2, start_second=3.0, end_second=6.0),
        CutPlan(index=3, start_second=6.0, end_second=9.0),
    ]


def _fallback_plan(brief: ProductBrief, source: str) -> ProductionPlan:
    target = brief.target_customer or "the target customer"
    benefit = brief.main_benefit or "the clearest product benefit"
    mood = brief.tone

    base_image = (
        f"A highly detailed 3D animated scene of {brief.product_name}, "
        f"clean commercial setting inspired by the reference mood (not copied), "
        f"clear product expression, simple but detailed background, soft commercial lighting, "
        f"premium color palette, centered hero composition, glossy texture, "
        f"a strong visual hook highlighting {benefit}, vertical 9:16 composition, "
        "viral short-form 3D animation style, clear main subject, strong visual contrast, "
        "consistent character design, consistent visual tone, same 3D animation style, "
        "no text, no watermark."
    )
    base_i2v = (
        "Animate this image into a short vertical 9:16 3D animation.\n"
        "Camera movement: slow push-in toward the hero product.\n"
        f"Main object movement: subtle reveal emphasizing {benefit}.\n"
        "Character expression: n/a.\n"
        "Scene action: premium lighting shift and clean product reveal.\n"
        "Visual effect: soft shimmer / clarity boost.\n"
        "Motion style: dynamic, satisfying, suitable for a viral short-form video.\n"
        "Keep the same character design, object shape, background, lighting, and overall visual tone.\n"
        "No text, no subtitles, no watermark.\n"
        "No background music, no vocal (keep sound effects only)."
    )
    cuts = [
        CutPlan(
            index=1, start_second=0.0, end_second=3.0, is_anchor=True,
            screen="hero product close-up", camera="front, slow push-in",
            motion="product reveal", background="clean studio", lighting="soft commercial",
            narration=f"{brief.product_name}, 이거 하나면 충분해요.", subtitle=f"{brief.product_name}",
            emotion="curiosity", image_prompt=base_image, i2v_prompt=base_i2v,
        ),
        CutPlan(
            index=2, start_second=3.0, end_second=6.0,
            screen="benefit demonstration", camera="medium, steady",
            motion="before/after change", background="clean studio", lighting="soft commercial",
            narration=f"{benefit}, 눈으로 바로 보여요.", subtitle=benefit,
            emotion="satisfaction", image_prompt=base_image, i2v_prompt=base_i2v,
        ),
        CutPlan(
            index=3, start_second=6.0, end_second=9.0,
            screen="product + brand", camera="pull-back to reveal product",
            motion="settle to clean after shot", background="clean studio", lighting="soft commercial",
            narration="궁금하면 지금 신청해 보세요.", subtitle=brief.product_name,
            emotion="trust", image_prompt=base_image, i2v_prompt=base_i2v,
        ),
    ]
    return ProductionPlan(
        source=source,
        video_type="product-morph / info short-form",
        first_3_seconds="hero product appears immediately with a clear benefit hook",
        success_structure="known problem, broad audience, easy to grasp, strong visual change, save/share trigger",
        consistency=ConsistencyType.UNKNOWN,
        consistency_reason="fallback: ask the operator whether one main character recurs",
        consistency_needs_human=True,
        cuts=cuts,
        narration_structure="hook -> problem -> change -> info -> CTA",
        localization_points=[
            "한국 소비자가 자주 겪는 문제로 소재 치환",
            "한국 릴스/쇼츠 말투로 자막 톤 조정",
            "국내에서 쉽게 구하는 제품/재료로 교체",
        ],
        topic_suggestions=[],
        pipeline_notes="image(4/cut) -> pick -> i2v -> narration -> CapCut",
        summary=(
            "Fallback plan: 레퍼런스를 방향성 소스로만 사용. 오프닝 프레임 규율·무드·페이스·광고 명료성을 가져온다."
        ),
        appeal_points=[
            benefit,
            "첫 1초 안에 바로 이해되는 후킹",
            "깔끔한 제품 가시성",
            f"{target} 대상 숏폼 페이싱",
        ],
        visual_direction=(
            f"{mood} 제품 중심 프레임, 명확한 히어로 오브젝트, 단순한 배경, 상업 조명, 부드러운 3-4초 모션."
        ),
    )
