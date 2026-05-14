from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import requests
import soundfile as sf

root = Path('/home/intel/udit-ws/kiosk/new_audio_analyzer/text-to-speech')
config_path = root / 'config.yaml'
original_config = config_path.read_text(encoding='utf-8')

runs = [
    ('int4', 'int4'),
    ('int8', 'int8'),
    ('fp16', 'fp16'),
    ('fp32', 'float32'),
]

url = 'http://127.0.0.1:8011/v1/audio/speech'
results = []


def set_cpu_dtype(dtype_value: str) -> None:
    """Update config to use CPU with specified dtype."""
    updated = re.sub(r'(^\s*device:\s*).*$', r'\1CPU', original_config, flags=re.MULTILINE)
    updated = re.sub(r'(^\s*dtype:\s*).*$', rf'\1{dtype_value}', updated, flags=re.MULTILINE)
    config_path.write_text(updated, encoding='utf-8')


def stop_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=20)


try:
    for label, dtype_value in runs:
        set_cpu_dtype(dtype_value)
        out_dir = root / 'storage' / 'openvino-api-tests' / f'qwen-cpu-{label}'
        out_dir.mkdir(parents=True, exist_ok=True)
        log_path = out_dir / 'startup.log'

        print(f"\n{'='*60}")
        print(f"Starting test: Qwen CPU {label}")
        print(f"{'='*60}")

        with log_path.open('w', encoding='utf-8') as log_file:
            proc = subprocess.Popen(
                [str(root / '.venv-qwen-speecht5-test' / 'bin' / 'python'), 'main.py'],
                cwd=root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            startup_ok = False
            startup_deadline = time.monotonic() + 3600
            while time.monotonic() < startup_deadline:
                line = proc.stdout.readline()
                if line:
                    log_file.write(line)
                    log_file.flush()
                    sys.stdout.write(f'[{label}] {line}')
                    sys.stdout.flush()
                    if 'Application startup complete.' in line:
                        startup_ok = True
                        break
                elif proc.poll() is not None:
                    break

            if not startup_ok:
                stop_process(proc)
                results.append({
                    'label': label,
                    'dtype': dtype_value,
                    'device': 'CPU',
                    'status': 'startup_failed',
                    'log_file': str(log_path.relative_to(root)),
                })
                print(f"[{label}] Startup failed!")
                continue

            print(f"[{label}] Service started, sending test request...")
            session = requests.Session()
            session.trust_env = False
            payload = {
                'model': 'qwen-tts',
                'input': f'This is an OpenVINO CPU {label} validation for Qwen text to speech.',
                'voice': 'Ryan',
                'language': 'English',
                'response_format': 'wav',
            }
            start = time.perf_counter()
            response = session.post(url, json=payload, timeout=1200)
            elapsed = time.perf_counter() - start

            wav_path = out_dir / f'qwen-cpu-{label}.wav'
            wav_path.write_bytes(response.content)
            data, sr = sf.read(wav_path)
            data = np.asarray(data, dtype=np.float32)
            run_result = {
                'label': label,
                'dtype': dtype_value,
                'device': 'CPU',
                'status_code': response.status_code,
                'elapsed_seconds': elapsed,
                'bytes': len(response.content),
                'session_id': response.headers.get('x-session-id'),
                'output_file': wav_path.name,
                'sample_rate': sr,
                'rms': float(np.sqrt(np.mean(np.square(data)))),
                'peak': float(np.max(np.abs(data))),
                'p95': float(np.percentile(np.abs(data), 95)),
                'log_file': str(log_path.relative_to(root)),
            }
            (out_dir / f'qwen-cpu-{label}.json').write_text(json.dumps(run_result, indent=2) + '\n', encoding='utf-8')
            results.append(run_result)
            print(json.dumps(run_result, indent=2))
            stop_process(proc)
            print(f"[{label}] Test completed in {elapsed:.2f}s")

finally:
    config_path.write_text(original_config, encoding='utf-8')

summary_path = root / 'storage' / 'openvino-api-tests' / 'qwen-cpu-batch-summary.json'
summary_path.write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
print(f"\n{'='*60}")
print(f"All tests completed! Summary saved to:")
print(f"{summary_path}")
print(f"{'='*60}")
print(json.dumps(results, indent=2))
