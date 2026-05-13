import uuid
from datetime import datetime

def generate_session_id():
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    short_uid = str(uuid.uuid4())[:8]
    return f"{timestamp}-{short_uid}"
