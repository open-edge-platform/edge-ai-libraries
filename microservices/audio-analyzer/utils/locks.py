import threading 

audio_pipeline_lock = threading.Lock()
video_analytics_lock = threading.Lock()