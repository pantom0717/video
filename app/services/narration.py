"""§7.5 나레이션 자동화 — 컷별 한국어 스크립트 + 자막 SRT + (선택) TTS 음성.

타임드 나레이션 스크립트 하나가 ① TTS ② 자막 SRT ③ 오디오 배치를 동시에 먹인다.
휴먼터칭 = 스크립트 승인 1회. 승인 전 TTS 금지(잘못 뽑으면 음성 크레딧 낭비).
"""
from __future__ import annotations

import json
from pathlib import Path

from app.config import settings
from app.models import NarrationLine, ProductionPlan

# 한국어 대략 발화 속도 ~ 초당 5자 (컷 길이 내 글자수 상한 추정)
CHARS_PER_SECOND = 5.0


def make_narration(plan: ProductionPlan, job_dir: Path) -> list[NarrationLine]:
    lines: list[NarrationLine] = []
    for cut in plan.cuts:
        duration = max(0.0, cut.end_second - cut.start_second)
        char_limit = int(duration * CHARS_PER_SECOND) if duration > 0 else 0
        text = (cut.narration or "").strip()
        lines.append(
            NarrationLine(
                cut_index=cut.index,
                start_second=cut.start_second,
                end_second=cut.end_second,
                text=text,
                char_limit=char_limit,
                over_limit=bool(char_limit and len(text) > char_limit),
            )
        )
    _write_json(job_dir / "narration.json", [ln.model_dump() for ln in lines])
    (job_dir / "captions.srt").write_text(build_srt(lines), encoding="utf-8")
    return lines


def build_srt(lines: list[NarrationLine]) -> str:
    blocks: list[str] = []
    for i, ln in enumerate(lines, start=1):
        if not ln.text:
            continue
        blocks.append(
            f"{i}\n{_ts(ln.start_second)} --> {_ts(ln.end_second)}\n{ln.text}\n"
        )
    return "\n".join(blocks)


def synthesize_tts(lines: list[NarrationLine], out_dir: Path) -> tuple[list[Path], list[str]]:
    """승인된 narration 으로 컷별 음성 생성. (생성된 경로들, 경고들) 반환.

    ElevenLabs 키가 있으면 REST 로 mp3 생성, 없으면 건너뛰고 경고만(비치명적).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    if not settings.elevenlabs_api_key:
        return [], ["elevenlabs_api_key_missing — 승인 후 키 설정하면 음성 자동 생성"]
    if not settings.elevenlabs_voice_id:
        return [], ["elevenlabs_voice_id_missing — 한국어 voice_id 설정 필요"]

    paths: list[Path] = []
    for ln in lines:
        if not ln.text:
            continue
        target = out_dir / f"seg{ln.cut_index:02d}.mp3"
        try:
            _elevenlabs_tts(ln.text, target)
            paths.append(target)
        except Exception as exc:  # noqa: BLE001 - 한 컷 실패가 전체를 막지 않음
            warnings.append(f"tts_failed cut{ln.cut_index:02d}: {exc}")
    return paths, warnings


def _elevenlabs_tts(text: str, out_path: Path) -> None:
    import urllib.request

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{settings.elevenlabs_voice_id}"
    payload = json.dumps({"text": text, "model_id": settings.elevenlabs_model_id}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "xi-api-key": settings.elevenlabs_api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - 고정 호스트
        out_path.write_bytes(resp.read())


def _ts(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    h, millis = divmod(millis, 3_600_000)
    m, millis = divmod(millis, 60_000)
    s, millis = divmod(millis, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{millis:03d}"


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
