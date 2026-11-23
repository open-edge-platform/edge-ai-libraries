// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

const RTSP_URL_PREFIX = "rtsp://";
const RTSP_URL_MAX_LENGTH = 2048;

// Mirrors vippet/rtsp_utils.py: characters significant in GStreamer pipeline
// descriptions (whitespace, '!', quotes, ',', ...) are rejected.
const RTSP_URL_ALLOWED_RE = /^[A-Za-z0-9\-._~:/?#[\]@%&+;=]+$/;

export const isRtspUrl = (value: string): boolean =>
  value.trim().startsWith(RTSP_URL_PREFIX);

/**
 * Validate a user-provided RTSP URL.
 * Returns an error message, or null when the URL is valid.
 */
export const validateRtspUrl = (value: string): string | null => {
  const url = value.trim();
  if (!url) {
    return "RTSP URL is required";
  }
  if (url.length > RTSP_URL_MAX_LENGTH) {
    return `RTSP URL is too long (max ${RTSP_URL_MAX_LENGTH} characters)`;
  }
  if (!url.startsWith(RTSP_URL_PREFIX)) {
    return `RTSP URL must start with '${RTSP_URL_PREFIX}'`;
  }
  if (!RTSP_URL_ALLOWED_RE.test(url)) {
    return "RTSP URL contains unsupported characters (whitespace, quotes, '!', ',', '(', ')', '*', '$' and '\\' are not allowed)";
  }

  const authority = url.slice(RTSP_URL_PREFIX.length).split(/[/?#]/, 1)[0];
  if (authority.includes("@")) {
    return "Credentials in the RTSP URL (user:password@) are not supported";
  }
  const host = authority.startsWith("[")
    ? authority.slice(0, authority.indexOf("]") + 1)
    : authority.split(":", 1)[0];
  if (!host || host === "[]") {
    return "RTSP URL must include a host";
  }
  const port = authority.slice(host.length);
  if (port) {
    const portNumber = Number(port.slice(1));
    if (
      !port.startsWith(":") ||
      !/^\d*$/.test(port.slice(1)) ||
      portNumber > 65535
    ) {
      return "RTSP URL has an invalid port";
    }
  }
  return null;
};
