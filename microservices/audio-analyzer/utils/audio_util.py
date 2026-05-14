import os
import logging
from fastapi import UploadFile, HTTPException
from utils.config_loader import config
from utils.app_paths import get_audio_upload_dir

logger = logging.getLogger(__name__)


def _build_unique_file_path(project_path: str, safe_filename: str) -> str:
    stem, ext = os.path.splitext(safe_filename)
    candidate = os.path.join(project_path, safe_filename)
    suffix = 1
    while os.path.exists(candidate):
        candidate = os.path.join(project_path, f"{stem}_{suffix}{ext}")
        suffix += 1
    return candidate

def save_audio_file(file: UploadFile, session_id: str | None = None):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    allowed_extensions = [ext.lower() for ext in config.audio_util.allowed_extensions]
    max_file_size_mb = config.audio_util.max_size_mb
    max_file_size_bytes = max_file_size_mb * 1024 * 1024

    project_path = get_audio_upload_dir(session_id=session_id)
    os.makedirs(project_path, exist_ok=True)

    safe_filename = os.path.basename(file.filename)
    ext = os.path.splitext(safe_filename)[1].lower()
    if ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail="Invalid file type")

    contents = bytearray()
    total_read = 0
    chunk_size = config.audio_util.chunk_size 

    while True:
        chunk = file.file.read(chunk_size)
        if not chunk:
            break
        total_read += len(chunk)
        if total_read > max_file_size_bytes:
            raise HTTPException(status_code=400, detail="File too large")
        contents.extend(chunk)

    file.file.seek(0)

    file_path = _build_unique_file_path(project_path, safe_filename)
    with open(file_path, "wb") as f:
        f.write(contents)

    logger.info(f"File saved: {file_path}")

    return os.path.basename(file_path), file_path
