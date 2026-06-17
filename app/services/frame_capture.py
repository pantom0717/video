from pathlib import Path


def capture_frame(video_path: Path, output_path: Path, second: float = 0.0) -> Path:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("opencv-python is required for frame capture") from exc

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

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
