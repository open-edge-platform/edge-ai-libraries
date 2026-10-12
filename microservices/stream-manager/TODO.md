# TODO

Items are listed roughly in order of priority.

## Features

### Major
- [x] Design and implement DATA dir setup and handling logic for both host and containerised environments
- [x] Package and distribution - Discuss and implement a strategy for containerizing.
- [ ] Implement the `PUT /buffer` endpoint to resize stream buffers
- [ ] Add S3-compatible storage for videos
- [ ] Support multiple `stream_ids` in start-recording request bodies

### Incremental
- [x] Implement support for user supplied config file. JSON or YAML preferred.
- [ ] Add pagination to the `GET /streams` endpoint
- [ ] Add a tools directory. This remains added to .dockerignore, but contain shell scripts that allow anyone to add stream-manager with proper config/data file dir to an existing docker compose file which is passed as an argument.

## Optimization or Improvements

### Major
- [ ] Add a custom error-handling framework using `StreamManError`
- [ ] Write `AGENTS.md` and `copilot-instructions.md`
- [ ] Idempotency of the `POST /records/start` endpoint

### Incremental
- [ ] Use of `log/slog` for logging
- [ ] Check if `ffmpeg` can completely replace `blueviron/mediamtx` and whether it will be an optimal choice.
- [ ] Check `cfg.RecordingStorage` quotas and enforce disk limits through host-based notifications or other mechanisms (rolling storage?)
- [ ] Use `errors.Join()` to combine `recordingFilter` validation errors and similar errors across endpoints
- [ ] Evaluate whether `DecodeJSON` would be useful as middleware
- [ ] Optimize request coupling - Should POST /streams be always called before POST /records/start by consumer?

## Research/Exploration
- [ ] Weigh in tradeoffs of using random UUIDs as primary key in the database - should UUIDv7 be used or a shorter UUID or incremental int prefixed to UUIDs.
- [x] Analyse tradeoffs of using distroless/scratch base image for the container - whether its even feasible or practical for our use case.
- [ ] Evaluate S3-compatible storage tradeoffs for video recordings, especially open recordings and real-time ingestion
- [ ] Evaluate whether fMP4 or another format can reduce MPEG-TS storage overhead while retaining its robustness
- [ ] Evaluate WebM instead of MP4 as the default Replay API clip format to use fully open-source codecs

## Bugs/Issues

- [ ] A `sensor_id` and `source_uri` both together make a unique stream, not just the sensor_id. Fix the stream attached error coming up for duplicate streams with the same `sensor_id` but different `source_uri`.
- [ ] Update the unique identifier (`stream_id`) for a stream to be a short uuid prefixed with `sensor_id`. (See related item in Research/Exploration)

# Deferred

Some of these items might have been already reconsidered for the TODO list above.

- [ ] Defer pagination for `GET /streams`; pagination is currently planned only for `/records` endpoints
- [ ] Do not implement sidecar indexes for keyframes or decoding assistance
- [ ] Defer S3-based storage
- [ ] Defer authentication and rate limiting; they are out of scope for now
