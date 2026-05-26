import uuid
from datetime import datetime


MAX_SESSION_ID_LENGTH = 128
_ALLOWED_SESSION_ID_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")

def generate_session_id():
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    short_uid = str(uuid.uuid4())[:4]  # short random suffix
    return f"{timestamp}-{short_uid}"


def normalize_session_id(session_id: str | None) -> str | None:
    if session_id is None:
        return None

    normalized = session_id.strip()
    if not normalized:
        return None

    if len(normalized) > MAX_SESSION_ID_LENGTH:
        raise ValueError("session_id is too long")

    if any(char not in _ALLOWED_SESSION_ID_CHARS for char in normalized):
        raise ValueError("session_id contains unsupported characters")

    return normalized


def resolve_requested_session_id(session_id: str | None) -> tuple[str, bool]:
    normalized = normalize_session_id(session_id)
    if normalized is None:
        return generate_session_id(), False
    return normalized, True
