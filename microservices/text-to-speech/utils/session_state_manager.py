from typing import Optional, Dict
from threading import Lock
import logging

logger = logging.getLogger(__name__)

class SessionState:
    """Thread-safe in-memory storage for active session metadata"""
    
    _sessions: Dict[str, dict] = {}
    _lock = Lock()
    
    @classmethod
    def set_audio_duration(cls, session_id: str, duration: float):
        """Store audio duration in memory"""
        with cls._lock:
            if session_id not in cls._sessions:
                cls._sessions[session_id] = {}
            cls._sessions[session_id]['audio_duration'] = duration
            cls._sessions[session_id]['has_audio'] = True
            logger.debug(f"Session {session_id}: Audio duration set to {duration}s")
    
    @classmethod
    def set_video_duration(cls, session_id: str, duration: float):
        """Store video duration in memory"""
        with cls._lock:
            if session_id not in cls._sessions:
                cls._sessions[session_id] = {}
            cls._sessions[session_id]['video_duration'] = duration
            cls._sessions[session_id]['has_video'] = True
            logger.debug(f"Session {session_id}: Video duration set to {duration}s")
    
    @classmethod
    def get_audio_duration(cls, session_id: str) -> Optional[float]:
        """Get stored audio duration"""
        with cls._lock:
            return cls._sessions.get(session_id, {}).get('audio_duration')
    
    @classmethod
    def get_video_duration(cls, session_id: str) -> Optional[float]:
        """Get stored video duration"""
        with cls._lock:
            return cls._sessions.get(session_id, {}).get('video_duration')
    
    @classmethod
    def get_session_state(cls, session_id: str) -> dict:
        """Get full session state"""
        with cls._lock:
            return cls._sessions.get(session_id, {}).copy()
    
    @classmethod
    def clear_session(cls, session_id: str):
        """Clean up session after processing"""
        with cls._lock:
            cls._sessions.pop(session_id, None)
            logger.debug(f"Session {session_id}: State cleared")
