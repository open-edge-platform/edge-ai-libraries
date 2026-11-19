# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Isolated pixel decoding; stdout contains only the bounded JSON result.

Invoked by media_inputs with a temporary copy of a registered media asset.
No Engine/model imports: killing this process also stops native decoders.
"""
import base64
import io
import json
import sys
import time

from PIL import Image, ImageOps


def encode_image(image, options):
    if image.width * image.height > options['max_pixels']:
        raise ValueError('pixel_limit')
    image = ImageOps.exif_transpose(image)
    if image.mode in ('RGBA', 'LA') or 'transparency' in image.info:
        rgba = image.convert('RGBA')
        background = Image.new('RGBA', rgba.size, 'white')
        image = Image.alpha_composite(background, rgba).convert('RGB')
    else:
        image = image.convert('RGB')
    image.thumbnail((options['longest_side'], options['longest_side']), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    image.save(output, 'JPEG', quality=options['jpeg_quality'])
    uri = 'data:image/jpeg;base64,' + base64.b64encode(output.getvalue()).decode('ascii')
    if len(uri) > options['max_payload']:
        raise ValueError('payload_limit')
    return uri


def prepare_video(path, options):
    import av
    import math

    # First pass retains only actual frame indices/timestamps, never pixel arrays.
    # Native decode stays inside this killable process with a total parent deadline.
    candidates = []
    next_target = 0.0
    step = 1 / options['video_sample_fps']
    origin = None
    last = None
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        stream.thread_count = 1
        if stream.codec_context.width * stream.codec_context.height > options['max_pixels']:
            raise ValueError('pixel_limit')
        for index, frame in enumerate(container.decode(stream)):
            if index >= 100000:
                raise ValueError('decode_frame_limit')
            if frame.width * frame.height > options['max_pixels']:
                raise ValueError('pixel_limit')
            if frame.pts is None or frame.time_base is None:
                raise ValueError('missing_timestamp')
            timestamp = float(frame.pts * frame.time_base)
            if origin is None:
                origin = float(stream.start_time * stream.time_base) if stream.start_time is not None else timestamp
            seconds = timestamp - origin
            if not math.isfinite(seconds) or seconds < 0 or (last and seconds * 1000 < last[1]):
                raise ValueError('missing_timestamp')
            last = (index, seconds * 1000)
            if not candidates or seconds + 1e-8 >= next_target:
                candidates.append(last)
                next_target = (math.floor((seconds + 1e-8) / step) + 1) * step
    if last is None:
        raise ValueError('decode_failed')
    if candidates[-1][0] != last[0]:
        candidates.append(last)
    count = min(len(candidates), options['max_frames'])
    selected = candidates if count == len(candidates) else [
        candidates[round(i * (len(candidates) - 1) / (count - 1))] for i in range(count)
    ]
    wanted = dict(selected)
    frames = []
    encoded = 0
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        stream.thread_count = 1
        for index, frame in enumerate(container.decode(stream)):
            if frame.width * frame.height > options['max_pixels']:
                raise ValueError('pixel_limit')
            if index not in wanted:
                continue
            image = frame.to_image()
            if frame.rotation:
                image = image.rotate(frame.rotation, expand=True)
            image.thumbnail((options['video_width'], options['video_height']), Image.Resampling.LANCZOS)
            canvas = Image.new('RGB', (options['video_width'], options['video_height']), 'white')
            canvas.paste(image, ((canvas.width - image.width) // 2, (canvas.height - image.height) // 2))
            uri = encode_image(canvas, {**options, 'longest_side': max(canvas.size)})
            encoded += len(uri)
            if encoded > options['max_payload']:
                raise ValueError('payload_limit')
            frames.append({'timestamp_ms': round(wanted[index], 3), 'image_url': uri})
            if len(frames) == len(selected):
                break
    if len(frames) != len(selected):
        raise ValueError('decode_failed')
    return {'video_frames': frames, 'frame_count': len(frames), 'encoded_bytes': encoded,
            'requested_fps': options['video_sample_fps'], 'candidate_frames': len(candidates),
            'timestamps_ms': [f['timestamp_ms'] for f in frames], 'downsampled': len(selected) < len(candidates)}


def prepare(path, options):
    started = time.monotonic()
    if options['kind'] == 'video':
        result = prepare_video(path, options)
        result['decode_encode_ms'] = round((time.monotonic() - started) * 1000, 2)
        return result
    if options['kind'] != 'image':
        raise ValueError('unsupported_role')
    with Image.open(path) as image:
        uri = encode_image(image, options)
    return {'image_url': uri, 'frame_count': 1,
            'encoded_bytes': len(uri), 'decode_encode_ms': round((time.monotonic() - started) * 1000, 2)}


if __name__ == '__main__':
    try:
        result = prepare(sys.argv[1], json.loads(sys.argv[2]))
    except ValueError as error:
        reason = str(error)
        result = {'error': reason if reason in {'pixel_limit', 'payload_limit', 'unsupported_role', 'decode_frame_limit', 'missing_timestamp'} else 'decode_failed'}
    except ImportError:
        result = {'error': 'decoder_unavailable'}
    except Exception:
        result = {'error': 'decode_failed'}
    print(json.dumps(result))
