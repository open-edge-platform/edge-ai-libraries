# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Subtitle serialization helpers shared by the OpenAI-compatible and VSS APIs.

``format_srt`` output must stay parseable by ``srt-parser-2``, which is what
VSS's pipeline-manager uses to read transcripts back out of MinIO
(``sample-applications/video-search-and-summarization``). That parser requires
each cue to be an integer index line, a ``HH:MM:SS,mmm --> HH:MM:SS,mmm``
timing line, then the text — so do not change this shape casually.
"""


def _clock(seconds: float, millis_separator: str) -> str:
    total_milliseconds = int(round(float(seconds) * 1000))
    if total_milliseconds < 0:
        total_milliseconds = 0
    hours, remainder = divmod(total_milliseconds, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    secs, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02}{millis_separator}{milliseconds:03}"


def format_srt(segments: list[dict]) -> str:
    """Render segments as SubRip (.srt) text."""
    blocks = []
    for index, segment in enumerate(segments, start=1):
        blocks.append(
            f"{index}\n"
            f"{_clock(segment.get('start', 0.0), ',')} --> {_clock(segment.get('end', 0.0), ',')}\n"
            f"{segment.get('text', '').strip()}"
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def format_vtt(segments: list[dict]) -> str:
    """Render segments as WebVTT (.vtt) text."""
    blocks = ["WEBVTT"]
    for segment in segments:
        blocks.append(
            f"{_clock(segment.get('start', 0.0), '.')} --> {_clock(segment.get('end', 0.0), '.')}\n"
            f"{segment.get('text', '').strip()}"
        )
    return "\n\n".join(blocks) + ("\n" if len(blocks) > 1 else "")
