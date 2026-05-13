import os


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORAGE_ROOT = os.path.join(BASE_DIR, "storage")

def get_session_dir(session_id: str) -> str:
    return os.path.join(STORAGE_ROOT, session_id)