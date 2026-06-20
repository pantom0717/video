"""§3.6 AI 프리셀렉트 — 컷별 후보 4장 중 베스트 1장을 추천(사람 거부권 게이트).

이미지가 로컬에 있으면 Gemini(VLM)로 채점, 없거나 실패하면 결정적 fallback(variant 0,
needs_human=True)으로 떨어진다. 자동 확정이 아니라 추천일 뿐 — 최종은 사람이 확정.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from app.config import settings
from app.models import CutPick, CutPlan, ImageCandidate, ProductionPlan


def prescreen(
    plan: ProductionPlan,
    candidates: list[ImageCandidate],
    job_dir: Path,
) -> list[CutPick]:
    by_cut: dict[int, list[ImageCandidate]] = defaultdict(list)
    for c in candidates:
        by_cut[c.cut_index].append(c)

    cut_by_index = {cut.index: cut for cut in plan.cuts}
    picks: list[CutPick] = []
    for cut_index, cands in sorted(by_cut.items()):
        cut = cut_by_index.get(cut_index)
        picks.append(_pick_one(cut, cands))

    _write(job_dir / "picks.json", [p.model_dump() for p in picks])
    return picks


def _pick_one(cut: CutPlan | None, cands: list[ImageCandidate]) -> CutPick:
    variants = sorted(c.variant for c in cands)
    if not variants:
        return CutPick(cut_index=cut.index if cut else 0, pick_variant=0, needs_human=True,
                       reason="no candidates")

    local = [c for c in cands if c.local_path and Path(c.local_path).exists()]
    if settings.gemini_api_key and cut and local:
        try:
            return _pick_with_gemini(cut, local)
        except Exception:  # noqa: BLE001
            pass

    # fallback: 첫 변형 추천, 사람이 직접 확인
    return CutPick(
        cut_index=cut.index if cut else cands[0].cut_index,
        pick_variant=variants[0],
        ranking=variants,
        reason="fallback: first variant (no VLM scoring) — 사람이 직접 확인",
        confidence=0.0,
        needs_human=True,
    )


def _pick_with_gemini(cut: CutPlan, local: list[ImageCandidate]) -> CutPick:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    parts: list[object] = [
        "Score these candidate starting frames for one short-form ad cut. "
        f"Cut intent: {cut.screen} | {cut.image_prompt[:300]}\n"
        "Pick the single best by: appeal clarity, composition, on-brief, no AI artifacts. "
        'Return STRICT JSON: {"pick_variant": <int>, "ranking": [<int>...], '
        '"reason": "...", "confidence": 0.0-1.0, "needs_human": <bool>}. '
        "Set needs_human=true if it is a close call or all have flaws."
    ]
    variant_order: list[int] = []
    for c in local:
        variant_order.append(c.variant)
        parts.append(f"variant {c.variant}:")
        parts.append(types.Part.from_bytes(data=Path(c.local_path).read_bytes(), mime_type="image/png"))

    resp = client.models.generate_content(
        model=settings.gemini_model,
        contents=parts,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    data = json.loads(resp.text or "{}")
    pick_variant = int(data.get("pick_variant", variant_order[0]))
    if pick_variant not in variant_order:
        pick_variant = variant_order[0]
    return CutPick(
        cut_index=cut.index,
        pick_variant=pick_variant,
        ranking=[int(x) for x in data.get("ranking", variant_order) if isinstance(x, (int, float))] or variant_order,
        reason=str(data.get("reason", "")),
        confidence=float(data.get("confidence", 0.0)),
        needs_human=bool(data.get("needs_human", False)),
    )


def _write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
