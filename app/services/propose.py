"""§5.0 i2v A/B 제안표 — 컷별로 A안(plan 충실) / B안(드라마틱 작문)을 결정적으로 만든다.

영상 판정이 아니라 '생성 전 텍스트 제안'. 최종 A/B 확정은 사람이 한다.
셀프체크 5개: 전후해소 / 첫3초후킹 / 실행정보 / AI티 / endFrame (team-feedback 기준).
"""
from __future__ import annotations

import json
from pathlib import Path

from app.config import settings
from app.models import CutPlan, I2VProposal, ProductionPlan


def propose(plan: ProductionPlan, job_dir: Path) -> list[I2VProposal]:
    proposals: list[I2VProposal] = []
    for cut in plan.cuts:
        proposals.append(_propose_one(cut))
    _write(job_dir / "proposals.json", [p.model_dump() for p in proposals])
    return proposals


def _propose_one(cut: CutPlan) -> I2VProposal:
    option_a = (cut.i2v_prompt or "").strip()
    option_b = ""
    recommend = "A"
    rationale = "A안 = plan 충실. before/after 가 약하면 B안 검토."

    if settings.gemini_api_key:
        try:
            option_b, recommend, rationale = _gemini_variant(cut, option_a)
        except Exception:  # noqa: BLE001
            option_b = _dramatic_rewrite(option_a)
    else:
        option_b = _dramatic_rewrite(option_a)

    return I2VProposal(
        cut_index=cut.index,
        option_a=option_a,
        option_b=option_b,
        recommend=recommend,
        rationale=rationale,
        self_check=_self_check(option_a, cut),
        chosen="",  # 사람이 확정
    )


def _gemini_variant(cut: CutPlan, option_a: str) -> tuple[str, str, str]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    prompt = (
        "Rewrite this image-to-video prompt as a more dramatic B option: "
        "strong before -> exaggerated change -> perfect after (hold). "
        "Keep the SAME labeled-section format (Camera movement / Main object movement / "
        "Character expression / Scene action / Visual effect / Motion style + keep-consistency + "
        "no text + no background music, no vocal). Korean intent ok, prompt body in English.\n"
        f"Cut: {cut.screen} | emotion: {cut.emotion}\n"
        f"A option:\n{option_a}\n\n"
        'Return STRICT JSON: {"option_b": "...", "recommend": "A|B", "rationale": "one line"}'
    )
    resp = client.models.generate_content(
        model=settings.gemini_model,
        contents=[prompt],
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    data = json.loads(resp.text or "{}")
    recommend = "B" if str(data.get("recommend", "A")).upper().strip() == "B" else "A"
    return str(data.get("option_b", "")), recommend, str(data.get("rationale", ""))


def _dramatic_rewrite(option_a: str) -> str:
    if not option_a:
        return ""
    return (
        option_a
        + "\nEmphasis: start from a clearly worse 'before' state, show an exaggerated, "
        "satisfying change, then hold a clean perfect 'after' for the last beat."
    )


def _self_check(option_a: str, cut: CutPlan) -> dict[str, str]:
    text = f"{option_a} {cut.i2v_prompt}".lower()
    return {
        "before_after_resolved": "ok" if any(k in text for k in ("before", "after", "change", "reveal")) else "check",
        "first_3s_hook": "ok" if cut.index == 1 else "n/a",
        "action_info": "check",  # 무엇을/어디에/몇 번 — 사람이 확인
        "ai_look": "check",
        "end_frame": "no",  # 기본 미사용; 변화 약하면 after 이미지를 end frame 으로 검토
    }


def _write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
