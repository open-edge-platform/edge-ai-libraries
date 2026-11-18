# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Opt-in, bounded media inputs for the retrieval console.

The retrieval ranking and text are immutable. Only the final response copies
receive data URIs; duplicate hits reference the first included evidence.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

import config

_workers = ThreadPoolExecutor(max_workers=config.MEDIA_PREPARE_WORKERS, thread_name_prefix='media-input')
_slots = threading.BoundedSemaphore(config.MEDIA_PREPARE_WORKERS)
_worker_path = Path(__file__).with_name('media_worker.py')
_skip_reasons = {'source_limit', 'pixel_limit', 'payload_limit', 'prepare_timeout',
                 'bounded_read_unavailable', 'unsupported_role'}


def _prepare(library, metadata, options, deadline, cancelled):
    started = time.monotonic()
    try:
        data = library.read_media_bounded(metadata['media_key'], metadata['source_id'], config.MEDIA_MAX_SOURCE_BYTES)
        source_bytes = len(data)
        load_ms = (time.monotonic() - started) * 1000
        if cancelled.is_set() or time.monotonic() >= deadline:
            return {'error': 'prepare_timeout'}
        with tempfile.TemporaryDirectory(prefix='engine-vlm-') as directory:
            path = Path(directory) / 'media'
            path.write_bytes(data)
            del data
            process = subprocess.Popen(
                [sys.executable, str(_worker_path), str(path), json.dumps(options)],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            )
            try:
                while True:
                    if cancelled.is_set() or time.monotonic() >= deadline:
                        return {'error': 'prepare_timeout'}
                    try:
                        output, _ = process.communicate(timeout=min(.1, max(.001, deadline - time.monotonic())))
                        break
                    except subprocess.TimeoutExpired:
                        continue
                if process.returncode:
                    return {'error': 'decode_failed'}
                result = json.loads(output)
                result.update(source_bytes=source_bytes, load_ms=round(load_ms, 2))
                return result
            finally:
                if process.poll() is None:
                    process.kill()
                process.communicate()
    except OverflowError:
        return {'error': 'source_limit'}
    except NotImplementedError:
        return {'error': 'bounded_read_unavailable'}
    except (KeyError, OSError, ValueError):
        return {'error': 'media_unavailable'}
    except Exception:
        # Decoder/storage errors may contain local paths or data. Never echo them.
        return {'error': 'prepare_failed'}


async def _load(library, metadata, options, deadline):
    while not _slots.acquire(blocking=False):
        if time.monotonic() >= deadline:
            return {'error': 'prepare_timeout'}
        await asyncio.sleep(.02)
    cancelled = threading.Event()
    try:
        future = _workers.submit(_prepare, library, metadata, options, deadline, cancelled)
    except BaseException:
        _slots.release()
        raise
    future.add_done_callback(lambda _: _slots.release())
    wrapped = asyncio.wrap_future(future)
    try:
        return await asyncio.wait_for(asyncio.shield(wrapped), max(.001, deadline - time.monotonic()))
    except TimeoutError:
        cancelled.set()
        return {'error': 'prepare_timeout'}
    except asyncio.CancelledError:
        cancelled.set()
        raise


async def enrich_media(chunks, libraries):
    started = time.monotonic()
    deadline = started + config.MEDIA_PREPARE_TIMEOUT_S
    included = {}
    hits = frames = encoded_bytes = 0
    for chunk in chunks:
        metadata = chunk.metadata
        # Do not trust media data originating in an index.
        for key in ('image_url', 'video_frames', 'video_url', 'media_input'):
            metadata.pop(key, None)
        kind, role = metadata.get('kind'), metadata.get('role')
        if kind not in ('image', 'video') and role not in ('image', 'doc_image', 'short_video', 'long_video', 'l1_segment'):
            continue
        status = {'status': 'skipped', 'reason': 'unsupported_role', 'frame_count': 0}
        metadata['media_input'] = status
        if (kind == 'image' and role in ('image', 'doc_image')) or (kind == 'video' and role == 'short_video'):
            if not all(isinstance(metadata.get(k), str) and metadata[k] for k in ('library', 'source_id', 'media_key')):
                status['reason'] = 'missing_reference'
            else:
                key = (metadata['library'], metadata['media_key'])
                if key in included:
                    status.update(status='included', reason='duplicate', evidence_chunk_id=included[key], frame_count=0)
                elif hits >= config.MEDIA_MAX_HITS or config.MEDIA_MAX_TOTAL_FRAMES - frames < (2 if kind == 'video' else 1):
                    status['reason'] = 'media_budget'
                elif encoded_bytes >= config.MEDIA_MAX_PAYLOAD_BYTES:
                    status['reason'] = 'payload_limit'
                elif time.monotonic() >= deadline:
                    status['reason'] = 'prepare_timeout'
                elif metadata['library'] not in libraries:
                    status['reason'] = 'missing_reference'
                else:
                    options = dict(kind=kind, max_pixels=config.MEDIA_MAX_PIXELS,
                                   longest_side=config.MEDIA_IMAGE_LONGEST_SIDE,
                                   jpeg_quality=config.MEDIA_JPEG_QUALITY,
                                   max_payload=config.MEDIA_MAX_PAYLOAD_BYTES - encoded_bytes)
                    options.update(video_sample_fps=config.MEDIA_VIDEO_SAMPLE_FPS,
                                   max_frames=min(config.MEDIA_MAX_VIDEO_FRAMES, config.MEDIA_MAX_TOTAL_FRAMES - frames),
                                   video_width=config.MEDIA_VIDEO_WIDTH, video_height=config.MEDIA_VIDEO_HEIGHT)
                    result = await _load(libraries[metadata['library']], metadata, options, deadline)
                    reason = result.pop('error', None)
                    if reason:
                        status.update(status='skipped' if reason in _skip_reasons else 'failed', reason=reason)
                    else:
                        media_field = 'video_frames' if kind == 'video' else 'image_url'
                        metadata[media_field] = result[media_field]
                        status.update(status='included', reason='ok', frame_count=result['frame_count'])
                        hits += 1
                        frames += result['frame_count']
                        encoded_bytes += result['encoded_bytes']
                        included[key] = chunk.id
    return {'media_prepare_ms': round((time.monotonic() - started) * 1000, 2),
            'media_hits': hits, 'frame_count': frames, 'encoded_bytes': encoded_bytes}
