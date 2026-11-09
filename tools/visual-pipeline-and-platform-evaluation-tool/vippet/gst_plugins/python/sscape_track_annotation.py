# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Bounded, best-effort track labels for on-demand camera images."""

import json
import math
import time
from datetime import datetime
from threading import Condition

import cv2


MAX_TRACK_PAYLOAD_BYTES = 4 * 1024 * 1024 # 4 MiB


def frame_timestamp(value: str) -> float:
  """Parse an ISO timestamp with an explicit timezone."""
  timestamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
  if timestamp.tzinfo is None:
    raise ValueError('Timestamp requires a timezone')
  return timestamp.timestamp()


def _track_entry(obj: dict, camera_id: str) -> tuple | None:
  if not isinstance(obj, dict):
    return None
  gid = obj.get('id')
  bounds = obj.get('camera_bounds')
  if not isinstance(gid, str) or not 0 < len(gid) <= 64 or not isinstance(bounds, dict):
    return None
  box = bounds.get(camera_id)
  if not isinstance(box, dict):
    return None
  values = tuple(box.get(key) for key in ('x', 'y', 'width', 'height'))
  if not all(type(value) in (int, float) and math.isfinite(value) for value in values):
    return None
  if values[2] <= 0 or values[3] <= 0:
    return None
  return gid, values


def parse_track_message(payload: bytes, camera_id: str) -> tuple | None:
  """Return timestamp and usable camera bounds, or None for malformed input."""
  try:
    if len(payload) > MAX_TRACK_PAYLOAD_BYTES:
      return None
    message = json.loads(payload)
    if not isinstance(message, dict) or not isinstance(message.get('objects'), list):
      return None
    timestamp = frame_timestamp(message['timestamp'])
    entries = {}
    for obj in message['objects'][:1000]:
      entry = _track_entry(obj, camera_id)
      if entry is not None:
        entries.setdefault(*entry)
    return timestamp, list(entries.items())
  except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
    return None


class TrackSync:
  """One cached track snapshot and one pending image, shared with an image worker."""

  def __init__(self):
    self.condition = Condition()
    self.snapshot = None
    self.pending = None
    self.stopped = False

  def update(self, snapshot: tuple) -> None:
    """Accept newer snapshots, including empty results."""
    with self.condition:
      if self.snapshot is None or snapshot[0] >= self.snapshot[0]:
        self.snapshot = snapshot
        self.condition.notify_all()

  def submit(self, image, payload: dict, wait_ms: int) -> None:
    """Coalesce image requests without moving the pending image's deadline."""
    try:
      timestamp = frame_timestamp(payload['timestamp'])
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
      timestamp = None
    with self.condition:
      if self.pending is None and not self.stopped:
        self.pending = image, payload, timestamp, time.monotonic() + wait_ms / 1000
        self.condition.notify_all()

  def take(self, max_age_ms: int) -> tuple | None:
    """Wait for a usable result or deadline; return None when stopped."""
    with self.condition:
      while not self.stopped:
        if self.pending is None:
          self.condition.wait()
          continue
        image, payload, timestamp, deadline = self.pending
        delta = self.snapshot[0] - timestamp if self.snapshot and timestamp is not None else math.inf
        remaining = deadline - time.monotonic()
        if 0 <= delta <= max_age_ms / 1000 or remaining <= 0:
          entries = self.snapshot[1] if abs(delta) <= max_age_ms / 1000 else []
          self.pending = None
          return image, payload, entries
        self.condition.wait(remaining)
    return None

  def stop(self) -> None:
    """Discard pending work and wake the worker for shutdown."""
    with self.condition:
      self.stopped = True
      self.pending = None
      self.condition.notify_all()


def draw_track_labels(image, entries: list) -> list:
  """Draw shortened labels and return the full GIDs actually rendered."""
  height, width = image.shape[:2]
  scale = max(1, (height + 479) // 480)
  drawn = []
  for gid, (left, top, box_width, box_height) in entries:
    if left >= width or top >= height or left + box_width <= 0 or top + box_height <= 0:
      continue
    label = gid[:8]
    font_scale = min(scale, width / 180, height / 50)
    (text_width, text_height), baseline = cv2.getTextSize(
      label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 2 * scale)
    origin = (max(0, min(int(left), width - text_width - 3)),
              max(text_height + 3, min(int(top) - 5, height - baseline - 3)))
    cv2.putText(image, label, origin, cv2.FONT_HERSHEY_SIMPLEX, font_scale,
                (0, 0, 0), 5 * scale)
    cv2.putText(image, label, origin, cv2.FONT_HERSHEY_SIMPLEX, font_scale,
                (255, 255, 255), 2 * scale)
    drawn.append(gid)
  return drawn
