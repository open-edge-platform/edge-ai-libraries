#!/usr/bin/env python3
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Split an include_media_data retrieve response into text chunks + media files.

Reads <dir>/response.json, writes one JPG per included image / video frame into
<dir>, and prints the numbered chunks plus a media manifest on stdout. Data
URIs are never printed: stdout stays small and safe for an agent context.
"""
import base64
import binascii
import json
import math
import sys
from pathlib import Path


def decode_data_uri(uri):
    header, _, data = uri.partition(',')
    if not header.startswith('data:') or not data:
        raise ValueError('not a data URI')
    return base64.b64decode(data, validate=True)


def frame_time(milliseconds):
    if not isinstance(milliseconds, (int, float)) or not math.isfinite(milliseconds) or milliseconds < 0:
        return 'unknown'
    value = int(milliseconds)
    return f'{value // 60000:02d}:{value // 1000 % 60:02d}.{value % 1000:03d}'


def main():
    directory = Path(sys.argv[1])
    response = json.loads((directory / 'response.json').read_text())
    chunks = response.get('chunks') or []
    if not chunks:
        print('No matching content was found in the knowledge base.')
        return

    image_lines = []
    video_lines = {}
    for index, chunk in enumerate(chunks, 1):
        metadata = chunk.get('metadata') or {}
        source = metadata.get('file_name') or metadata.get('asset_id') or 'unknown'
        score = round((chunk.get('score') or 0) * 1000) / 1000
        print(f'[{index}] score={score} source={source}\n{chunk.get("text") or ""}\n')

        state = metadata.get('media_input')
        if not state:
            continue
        entry = f'[{index}] source={source} status={state.get("status")}'
        if state.get('reason') not in (None, 'ok'):
            entry += f' reason={state["reason"]}'
        duplicate = state.get('evidence_chunk_id')
        if duplicate:
            entry += f' duplicate_of={duplicate}'
        files = []
        errors = []
        if state.get('status') == 'included' and not duplicate:
            if metadata.get('image_url'):
                try:
                    path = directory / f'hit{index}.jpg'
                    path.write_bytes(decode_data_uri(metadata['image_url']))
                    files.append(f'E{index} path={path}')
                except (ValueError, binascii.Error, OSError) as error:
                    errors.append(str(error))
            for frame_index, frame in enumerate(metadata.get('video_frames') or []):
                try:
                    path = directory / f'hit{index}_frame{frame_index}.jpg'
                    path.write_bytes(decode_data_uri(frame['image_url']))
                    files.append(f'E{index}F{frame_index} time={frame_time(frame.get("timestamp_ms"))} '
                                 f't={frame.get("timestamp_ms")}ms path={path}')
                except (ValueError, binascii.Error, KeyError, OSError) as error:
                    errors.append(str(error))
        if duplicate:
            delivery = 'shared'
        elif files and errors:
            delivery = 'partial'
        elif files:
            delivery = 'ready'
        elif state.get('status') == 'included':
            delivery = 'failed'
        else:
            delivery = 'unavailable'
        entry += f' delivery={delivery}'
        if errors:
            entry += f' file_error={"; ".join(errors)}'
        line = entry + ('\n    ' + '\n    '.join(files) if files else '')
        if metadata.get('role') in ('short_video', 'video') or metadata.get('video_frames'):
            video_lines.setdefault(source, []).append(line)
        else:
            image_lines.append(line)

    if image_lines or video_lines:
        print('## Media evidence')
        if image_lines:
            print('### Images and document figures')
            print('\n'.join(image_lines))
        if video_lines:
            print('### Videos — each source is a separate group')
            for source, lines in video_lines.items():
                print(f'#### source={source}')
                print('\n'.join(lines))
        print(f'\nMedia files directory: {directory}')
        print('Read must return an image block before describing a file. '
              'Choose relevant evidence; finish one video source before another. '
              'Use IDs only for internal cross-checking; in the answer cite source and time, '
              'never the E IDs. State uncertainty when needed.')

    diagnostics = response.get('media_diagnostics')
    if diagnostics:
        print(f'\nmedia_diagnostics: media_hits={diagnostics.get("media_hits")} '
              f'frame_count={diagnostics.get("frame_count")} '
              f'media_prepare_ms={diagnostics.get("media_prepare_ms")}')


if __name__ == '__main__':
    main()
