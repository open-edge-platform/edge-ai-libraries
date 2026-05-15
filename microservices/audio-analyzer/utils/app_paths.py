import os


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORAGE_ROOT = os.path.join(BASE_DIR, "storage")


def get_audio_upload_dir(session_id: str | None = None) -> str:
    if session_id:
        return get_session_dir(session_id)
    return os.path.join(STORAGE_ROOT, "audio")


def get_session_dir(session_id: str) -> str:
    return os.path.join(STORAGE_ROOT, session_id)


def resolve_project_path(path: str) -> str:
    if os.path.isabs(path):
        return path
    return os.path.join(BASE_DIR, path)


def get_chunks_dir(path: str = "chunks") -> str:
    return resolve_project_path(path)