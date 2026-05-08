from __future__ import annotations

import json
import os
import re
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

# Test fp16 and fp32 on GPU with 2 requests each to check warmup
runs = [
    ('fp16', 'fp16', 2),
    ('fp16-equivalent', 'fp32', 2),
]

url = 'http://127.0.0.1:8011/v1/audio/speech'
results = []


def set_gpu_dtype(dtype_value: str) -> None:
    """Update config to use GPU with specified dtype."""
    updated = re.sub(r'(^\s*device:\s*).*$', r'\1GPU', original_config, flags=re.MULTILINE)
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
    for label, dtype_value, num_requests in runs:
        set_gpu_dtype(dtype_value)
        out_dir = root / 'storage' / 'openvino-api-tests' / f'qwen-gpu-warmup-{label}'
        out_dir.mkdir(parents=True, exist_ok=True)
        log_path = out_dir / 'startup.log'

        print(f"\n{'='*60}")
        print(f"Starting test: Qwen GPU {label} with {num_requests} requests")
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
                    'device': 'GPU',
                    'status': 'startup_failed',
                    'log_file': str(log_path.relative_to(root)),
                })
                print(f"[{label}] Startup failed!")
                continue

            print(f"[{label}] Service started, sending {num_requests} requests...")
            session = requests.Session()
            session.trust_env = False
            
            for req_num in range(1, num_requests + 1):
                payload = {
                    'model': 'qwen-tts',
                    'input': f'Request {req_num}: This is an OpenVINO GPU {label} validation for Qwen text to speech.',
                    'voice': 'Ryan',
                    'language': 'English',
                    'response_format': 'wav',
                }
                
                start = time.perf_counter()
                response = session.post(url, json=payload, timeout=1200)
                elapsed = time.perf_counter() - start

                wav_path = out_dir / f'qwen-gpu-warmup-{label}-req{req_num}.wav'
                wav_path.write_bytes(response.content)
                data, sr = sf.read(wav_path)
                data = np.asarray(data, dtype=np.float32)
                
                run_result = {
                    'label': label,
                    'request': req_num,
                    'dtype': dtype_value,
                    'device': 'GPU',
                    'status_code': response.status_code,
                    'elapsed_seconds': elapsed,
                    'bytes': len(response.content),
                    'session_id': response.headers.get('x-session-id'),
                    'output_file': wav_path.name,
                    'sample_rate': sr,
                    'rms': float(np.sqrt(np.mean(np.square(data)))),
                    'peak': float(np.max(np.abs(data))),
                    'p95': float(np.percentile(np.abs(data), 95)),
                }
                results.append(run_result)
                print(f"[{label}] Request {req_num} completed in {elapsed:.2f}s (RMS: {run_result['rms']:.4f})")
                print(json.dumps(run_result, indent=2))

            stop_process(proc)
            print(f"[{label}] All requests completed")

finally:
    config_path.write_text(original_config, encoding='utf-8')

summary_path = root / 'storage' / 'openvino-api-tests' / 'qwen-gpu-warmup-batch-summary.json'
summary_path.write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')

print(f"\n{'='*60}")
print(f"All tests completed! Summary saved to:")
print(f"{summary_path}")
print(f"{'='*60}")

# Print warmup analysis
print("\n=== WARMUP ANALYSIS ===")
for label, dtype_value, _ in runs:
    label_results = [r for r in results if r['label'] == label]
    if len(label_results) >= 2:
        req1 = label_results[0]
        req2 = label_results[1]
        print(f"\n{label} ({dtype_value}):")
        print(f"  Request 1: {req1['elapsed_seconds']:.2f}s (RMS: {req1['rms']:.4f})")
        print(f"  Request 2: {req2['elapsed_seconds']:.2f}s (RMS: {req2['rms']:.4f})")
        print(f"  Speedup: {req1['elapsed_seconds']/req2['elapsed_seconds']:.2f}x")
        print(f"  Quality difference (RMS): {abs(req1['rms']-req2['rms']):.4f}")

print(json.dumps(results, indent=2))
