/**
 * Resolve the same-origin WHEP endpoint for a live stream. MediaMTX is only reachable
 * through the nginx/Vite proxy, so the result is always `<origin>/<stream-name>/whep`.
 *
 * The scheme is rewritten to `http:` before parsing because `rtsp:` is a non-special
 * scheme: browsers disagree on whether `new URL()` puts the authority in `host` or leaves
 * it in `pathname`. Older Firefox does the latter, which yielded a protocol-relative path
 * and pointed the browser at the internal `mediamtx:8554` address instead of the proxy.
 *
 * Returns `null` when no stream name can be derived, so callers never fall back to a
 * cross-origin URL.
 */
export const buildWhepUrl = (
  origin: string,
  streamUrl?: string,
  pipelineId?: string,
): string | null => {
  if (!streamUrl) {
    return pipelineId
      ? new URL(`/stream_${pipelineId}/whep`, origin).toString()
      : null;
  }

  let parsed: URL;
  try {
    parsed = new URL(streamUrl.replace(/^rtsps?:/i, "http:"), origin);
  } catch {
    return null;
  }

  const segments = parsed.pathname.split("/").filter(Boolean);
  const last = segments[segments.length - 1];
  const streamName = last === "whep" ? segments[segments.length - 2] : last;

  return streamName ? new URL(`/${streamName}/whep`, origin).toString() : null;
};
