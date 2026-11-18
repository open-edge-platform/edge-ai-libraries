# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
Route SceneScape plugin log messages through the GStreamer debug system.

Registers a `GstDebugCategory` per plugin so that verbosity is controlled by
the standard `GST_DEBUG` env var alongside built-in categories, e.g.:

    GST_DEBUG=1,gencamsrc:2,sscape_ts_capture:2,sscape_post_inference:2

Levels map to `Gst.DebugLevel`: ERROR=1, WARNING=2, FIXME=3, INFO=4, DEBUG=5.

PyGObject does not expose a Python constructor for `GstDebugCategory` (in C
categories are created through the `GST_DEBUG_CATEGORY_INIT` macro, which is
not introspectable). We therefore call the underlying libgstreamer C symbols
directly via `ctypes`. Once the category pointer is registered, it behaves
exactly like any built-in category and is controlled by `GST_DEBUG`.
"""

import ctypes
import fnmatch
import os
import traceback
from ctypes.util import find_library

import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst  # pylint: disable=no-name-in-module,wrong-import-position


def _load_libgstreamer() -> ctypes.CDLL:
  for candidate in (
    find_library("gstreamer-1.0"),
    "libgstreamer-1.0.so.0",
    "libgstreamer-1.0.so",
  ):
    if not candidate:
      continue
    try:
      return ctypes.CDLL(candidate)
    except OSError:
      continue
  raise OSError("Unable to load libgstreamer-1.0 for GstDebugCategory setup")


_libgst = _load_libgstreamer()

# GstDebugCategory * _gst_debug_category_new(const gchar *name,
#                                            guint color,
#                                            const gchar *description);
_libgst._gst_debug_category_new.argtypes = [
  ctypes.c_char_p, ctypes.c_uint, ctypes.c_char_p,
]
_libgst._gst_debug_category_new.restype = ctypes.c_void_p

# void gst_debug_log_literal(GstDebugCategory *category, GstDebugLevel level,
#                            const gchar *file, const gchar *function,
#                            gint line, GObject *object,
#                            const gchar *message_string);   # GStreamer >= 1.20
_libgst.gst_debug_log_literal.argtypes = [
  ctypes.c_void_p, ctypes.c_int,
  ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int,
  ctypes.c_void_p, ctypes.c_char_p,
]
_libgst.gst_debug_log_literal.restype = None

# void gst_debug_category_set_threshold (GstDebugCategory *category,
#                                        GstDebugLevel level);
_libgst.gst_debug_category_set_threshold.argtypes = [ctypes.c_void_p, ctypes.c_int]
_libgst.gst_debug_category_set_threshold.restype = None
# int gst_debug_category_get_threshold (GstDebugCategory *category);
_libgst.gst_debug_category_get_threshold.argtypes = [ctypes.c_void_p]
_libgst.gst_debug_category_get_threshold.restype = ctypes.c_int


def _threshold_from_gst_debug_env(name: str):
  """Return the level `GST_DEBUG` assigns to `name`; last match wins."""
  raw = os.environ.get("GST_DEBUG", "")
  chosen = None
  for entry in raw.split(","):
    entry = entry.strip()
    if not entry:
      continue
    if ":" in entry:
      pattern, _, lvl = entry.rpartition(":")
      pattern = pattern.strip() or "*"
    else:
      pattern, lvl = "*", entry
    try:
      level = int(lvl)
    except ValueError:
      continue
    if fnmatch.fnmatchcase(name, pattern):
      chosen = level
  return chosen


_FILE_TAG = b"sscape"
_FUNC_TAG = b""


class GstCategoryLogger:
  """`logging.Logger`-lookalike backed by a `GstDebugCategory`.

  Exposes `error/warning/info/debug/exception` so existing call sites written
  against `logging.getLogger(...)` need no other changes.
  """

  def __init__(self, name: str, description: str = "", color: int = 0) -> None:
    self._name = name
    self._cat = _libgst._gst_debug_category_new(
      name.encode("utf-8"),
      int(color),
      description.encode("utf-8"),
    )
    # Bypassing `GST_DEBUG_CATEGORY_INIT` skips the threshold apply the macro
    # normally does, so replay GST_DEBUG's match for this name explicitly.
    if self._cat:
      level = _threshold_from_gst_debug_env(name)
      if level is not None:
        _libgst.gst_debug_category_set_threshold(self._cat, int(level))

  def _emit(self, level: Gst.DebugLevel, msg: str) -> None:
    # `_cat` is NULL when GStreamer was built with `--disable-gst-debug`; in
    # that case both the category and the log function are no-ops. Guard just
    # in case, and let the C side handle threshold filtering otherwise.
    if not self._cat:
      return
    _libgst.gst_debug_log_literal(
      self._cat, int(level),
      _FILE_TAG, _FUNC_TAG, 0, None,
      msg.encode("utf-8", errors="replace"),
    )

  def error(self, msg) -> None:
    self._emit(Gst.DebugLevel.ERROR, str(msg))

  def warning(self, msg) -> None:
    self._emit(Gst.DebugLevel.WARNING, str(msg))

  def info(self, msg) -> None:
    self._emit(Gst.DebugLevel.INFO, str(msg))

  def debug(self, msg) -> None:
    self._emit(Gst.DebugLevel.DEBUG, str(msg))

  def exception(self, msg) -> None:
    """Emit at ERROR level with the current exception traceback appended.

    Intended for use from inside an `except` block, mirroring
    `logging.Logger.exception`.
    """
    self._emit(Gst.DebugLevel.ERROR, f"{msg}\n{traceback.format_exc()}")
