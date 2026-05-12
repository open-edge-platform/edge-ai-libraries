import os
import subprocess
from uuid import uuid4
import atexit
import shutil
import time
import logging
from utils.config_loader import config
from utils.app_paths import get_chunks_dir
from dto.audiosource import AudioSource

logger = logging.getLogger(__name__)

CHUNK_DURATION = config.audio_preprocessing.chunk_duration_sec
SILENCE_THRESH = config.audio_preprocessing.silence_threshold
SILENCE_DURATION = config.audio_preprocessing.silence_duration
SEARCH_WINDOW = config.audio_preprocessing.search_window_sec
CLEAN_UP_ON_EXIT = config.app.cleanup_on_exit

CHUNKS_DIR = get_chunks_dir(config.audio_preprocessing.chunk_output_path)
os.makedirs(CHUNKS_DIR, exist_ok=True)

DENOISE = getattr(config.audio_preprocessing, "denoise", False)
DENOISE_MODEL = getattr(config.audio_preprocessing, "denoise_model", "")

FFMPEG_PROCESSES = {}

@atexit.register
def cleanup_chunks_folder():
    if os.path.exists(CHUNKS_DIR) and CLEAN_UP_ON_EXIT:
        shutil.rmtree(CHUNKS_DIR)
        logger.info(f"Cleaned up {CHUNKS_DIR} directory on exit.")

def get_audio_duration(audio_path):
    if not os.path.isfile(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of",
        "default=noprint_wrappers=1:nokey=1", audio_path
    ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")

    if result.returncode != 0:
        raise ValueError(result.stdout.strip() or f"ffprobe failed for {audio_path}")

    return float(result.stdout.strip())

def detect_silences(audio_path):
    result = subprocess.run([
        "ffmpeg", "-i", audio_path, "-af",
        f"silencedetect=noise={SILENCE_THRESH}dB:d={SILENCE_DURATION}",
        "-f", "null", "-"
    ], stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")

    output = result.stderr
    silences = []

    current_silence = {}
    for line in output.split('\n'):
        if "silence_start" in line:
            current_silence['start'] = float(line.split("silence_start:")[1])
        elif "silence_end" in line:
            current_silence['end'] = float(line.split("silence_end:")[1].split('|')[0])
            silences.append(current_silence)
            current_silence = {}
    return silences

def get_closest_silence(silences, target_time, window=SEARCH_WINDOW):
    closest = None
    closest_diff = float('inf')

    for silence in silences:
        # Check if target time is within the silence interval
        if silence['start'] <= target_time <= silence['end']:
            return target_time

        # Check distance to start and end points
        for key in ['start', 'end']:
            diff = abs(silence[key] - target_time)
            if diff <= window and diff < closest_diff:
                closest = silence[key]
                closest_diff = diff

    return closest  # None if nothing close enough

def _build_af_filter() -> list[str]:
    """Return ffmpeg -af args for RNNoise denoising, or empty list if disabled."""
    if not DENOISE:
        return []
    if DENOISE_MODEL:
        af = f"arnndn=m={DENOISE_MODEL}"
    else:
        af = "arnndn"
    return ["-af", af]


def process_audio_segment(audio_path, start_time, end_time, chunk_index):
    os.makedirs(CHUNKS_DIR, exist_ok=True)
    chunk_name = f"chunk_{chunk_index}_{uuid4().hex[:6]}.wav"
    chunk_path = os.path.join(CHUNKS_DIR, chunk_name)
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-i", audio_path,
            "-ss", str(start_time), "-to", str(end_time),
            "-ar", "16000", "-ac", "1",
            *_build_af_filter(),
            "-c:a", "pcm_s16le", "-vn",
            chunk_path
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace"
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed while creating chunk {chunk_index}: {result.stderr.strip() or result.returncode}"
        )
    if not os.path.isfile(chunk_path):
        raise FileNotFoundError(f"Chunk file was not created: {chunk_path}")
    logger.debug(f"Chunk {chunk_index} saved: {chunk_path}")
    return {
        "chunk_path": chunk_path,
        "start_time": start_time,
        "end_time": end_time,
        "chunk_index": chunk_index
    }

def chunk_audio_by_silence(audio_path):
    if SEARCH_WINDOW > CHUNK_DURATION:
        raise ValueError(
            f"Silence search window ({SEARCH_WINDOW}s) can't be more than chunk duration ({CHUNK_DURATION}s)."
        )
    duration = get_audio_duration(audio_path)
    silences = detect_silences(audio_path)
    current_time, chunk_index = 0.0, 0
    while current_time < duration:
        ideal_end = current_time + CHUNK_DURATION
        end_time = get_closest_silence(silences, ideal_end) or min(ideal_end, duration)
        if end_time <= current_time:
            end_time = min(ideal_end, duration)
        yield process_audio_segment(audio_path, current_time, end_time, chunk_index)
        current_time = end_time
        chunk_index += 1

def chunk_audiostream_by_silence(session_id: str):
    global FFMPEG_PROCESSES
    os.makedirs(CHUNKS_DIR, exist_ok=True)
    mic_device = os.environ.get("AUDIO_ANALYZER_MICROPHONE", "").strip()
    if not mic_device:
        raise ValueError(
            "Microphone device not set. Set AUDIO_ANALYZER_MICROPHONE to an ALSA device such as hw:0,0"
        )

    record_file = os.path.join(CHUNKS_DIR, f"live_input_{session_id}.wav")
    process = subprocess.Popen(
        [
            "ffmpeg", "-y",
            "-f", "alsa", "-i", mic_device,
            "-ar", "16000", "-ac", "1",
            "-c:a", "pcm_s16le", "-rf64", "auto",
            record_file
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    FFMPEG_PROCESSES[session_id] = process
    logger.info(f"🎙️ Recording from {mic_device} (session={session_id}) ... use /stop-mic to stop.")
    current_time, chunk_index = 0.0, 0
    MAX_DURATION = 45 * 60
    try:
        while True:
            if current_time >= MAX_DURATION:
                logger.info(f"Session {session_id}: reached 45 min limit, stopping.")
                break
            if not os.path.exists(record_file) or os.path.getsize(record_file) < 44:
                time.sleep(0.02)
                continue
            duration = get_audio_duration(record_file)
            if (process.poll() is not None) and (duration - current_time < CHUNK_DURATION):
                logger.info(f"Session {session_id}: FFmpeg stopped, processing final chunk...")
                yield process_audio_segment(record_file, current_time, duration, chunk_index)
                break
            if duration - current_time < CHUNK_DURATION:
                time.sleep(0.02)
                continue
            segment_file = os.path.join(CHUNKS_DIR, f"temp_segment_{uuid4().hex[:6]}.wav")
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", record_file,
                    "-ss", str(current_time), "-to", str(duration),
                    "-ar", "16000", "-ac", "1",
                    "-c:a", "pcm_s16le", "-vn",
                    segment_file
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            silences = detect_silences(segment_file)
            silences = [
                    {"start": s["start"] + current_time, "end": s["end"] + current_time}
                    for s in detect_silences(segment_file)
            ]
            ideal_end = current_time + CHUNK_DURATION
            end_time = get_closest_silence(silences, ideal_end) or min(ideal_end, duration)
            if end_time <= current_time:
                end_time = min(ideal_end, duration)
            yield process_audio_segment(record_file, current_time, end_time, chunk_index)
            current_time = end_time
            chunk_index += 1
            os.remove(segment_file)
    finally:
        proc = FFMPEG_PROCESSES.pop(session_id, None)
        if proc:
            try:
                proc.terminate()
            except Exception as e:
                logger.warning(f"Error stopping FFmpeg for session {session_id}: {e}")
        if os.path.exists(record_file):
            try:
                os.remove(record_file)
            except Exception as e:
                logger.warning(f"Could not remove {record_file}: {e}")
        logger.info(f"🎧 Live recording stopped for session {session_id}.")

def chunk_by_silence(input, session_id: str):
    if input.source_type == AudioSource.MICROPHONE:
        yield from chunk_audiostream_by_silence(session_id)
    else:
        yield from chunk_audio_by_silence(input.audio_filename)
