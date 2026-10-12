# TODO

Items are listed roughly in order of priority.

## Features

### Major
- [ ] Implement the `PUT /buffer` endpoint to resize stream buffers
- [ ] Add S3-compatible storage for videos
- [ ] Support multiple `stream_ids` in start-recording request bodies

### Incremental
- [ ] Implement support for user supplied config file (located at user home config directory). JSON or YAML preferred.
- [ ] Add pagination to the `GET /streams` endpoint

## Optimization or Improvements

### Major
- [ ] Use `log/slog` for logging
- [ ] Add a custom error-handling framework using `StreamManError`

### Incremental
- [ ] Check `cfg.RecordingStorage` quotas and enforce disk limits through host-based notifications or other mechanisms
- [ ] Use `errors.Join()` to combine `recordingFilter` validation errors and similar errors across endpoints
- [ ] Evaluate whether `DecodeJSON` would be useful as middleware

### Research/Exploration
- [ ] Evaluate S3-compatible storage tradeoffs for video recordings, especially open recordings and real-time ingestion
- [ ] Evaluate whether fMP4 or another format can reduce MPEG-TS storage overhead while retaining its robustness
- [ ] Evaluate WebM instead of MP4 as the default Replay API clip format to use fully open-source codecs

# Deferred

Some of these items might have been already reconsidered for the TODO list above.

- [ ] Defer pagination for `GET /streams`; pagination is currently planned only for `/records` endpoints
- [ ] Do not implement sidecar indexes for keyframes or decoding assistance
- [ ] Defer S3-based storage
- [ ] Defer authentication and rate limiting; they are out of scope for now
