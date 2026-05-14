from pydantic import BaseModel
from dto.audiosource import AudioSource
from typing import Optional
 
class TranscriptionRequest(BaseModel):
    audio_filename: str
    source_type: Optional[AudioSource] = AudioSource.AUDIO_FILE