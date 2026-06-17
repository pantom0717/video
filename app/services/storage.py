from pathlib import Path

from fastapi import UploadFile


def ensure_dirs(data_dir: Path) -> None:
    (data_dir / "uploads").mkdir(parents=True, exist_ok=True)
    (data_dir / "outputs").mkdir(parents=True, exist_ok=True)


async def save_upload(upload: UploadFile, upload_dir: Path, job_id: str) -> Path:
    upload_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(upload.filename or "reference.mp4").suffix or ".mp4"
    path = upload_dir / f"{job_id}{suffix}"
    with path.open("wb") as handle:
        while chunk := await upload.read(1024 * 1024):
            handle.write(chunk)
    return path
