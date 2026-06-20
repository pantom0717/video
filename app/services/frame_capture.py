from pathlib import Path

from app.models import CutPlan


def capture_frame(video_path: Path, output_path: Path, second: float = 0.0) -> Path:
    capture, cv2 = _open(video_path)
    fps = capture.get(cv2.CAP_PROP_FPS) or 30
    frame_index = max(0, int(second * fps))
    capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    ok, frame = capture.read()
    capture.release()

    if not ok:
        raise RuntimeError(f"Could not read frame at {second}s")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), frame):
        raise RuntimeError(f"Could not write frame: {output_path}")
    return output_path


def extract_cut_frames(
    video_path: Path,
    cuts: list[CutPlan],
    out_dir: Path,
    offset: float = 0.3,
) -> dict[int, Path]:
    """컷별 시작 프레임을 cutNN.png 로 추출 (§2). {cut_index: path} 반환.

    offset: 컷 시작 후 N초 시점(전환 프레임 회피). 컷 중간을 넘지 않게 보호.
    추출 프레임은 §3 이미지 생성의 reference 로만 쓰이므로 픽셀 정확도는 불필요.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    result: dict[int, Path] = {}
    for cut in cuts:
        span = max(0.0, cut.end_second - cut.start_second)
        safe_offset = min(offset, span / 2) if span > 0 else offset
        second = cut.start_second + safe_offset
        path = out_dir / f"cut{cut.index:02d}.png"
        try:
            capture_frame(video_path, path, second)
            result[cut.index] = path
        except Exception:  # noqa: BLE001 - 한 컷 실패가 전체를 막지 않음(사람이 교체)
            continue
    return result


def _open(video_path: Path):
    try:
        import cv2
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("opencv-python is required for frame capture") from exc

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")
    return capture, cv2
