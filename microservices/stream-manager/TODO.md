<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# TODO

Items are listed roughly in order of priority.

## Features

### Major
- [x] Design and implement DATA dir setup and handling logic for both host and containerised environments
- [x] Package and distribution - Discuss and implement a strategy for containerizing.
- [x] Implement the `PUT /buffer` endpoint to resize stream buffers
- [ ] Add S3-compatible storage for videos
- [ ] Discuss, analyse and implement multiple `stream_ids` in start-recording request bodies
- [ ] Discuss if TTL or expiry of retrieved clips and frames is a desired or undesired feature. Act accordingly.
- [x] Documentation Update - With forked repo references
- [ ] Documentation Update - With mainline repo references

### Incremental
- [x] Implement support for user supplied config file. JSON or YAML preferred.
- [x] Add a tool for building and running the application on host and as a container (`Makefile` with `build`/`run`/`start`/`docker-build`/`docker-run`/`docker-stop` targets).
- [ ] Add pagination to the `GET /streams` endpoint
- [ ] Decide whether `make deploy` should add stream-manager (with its config and data mounts) to an existing docker compose file, which is passed as an argument.
- [ ] Analyse if ranger headers needed in media access APIs and implement accordingly

## Optimization or Improvements

### Major
- [x] Add a custom error-handling framework using `StreamManError`
- [ ] See possibilities to use `StreamManError` across all error chains, or even as Custom Sentinel Errors.
- [x] Write `AGENTS.md` and `copilot-instructions.md`
- [ ] Idempotency of the `POST /records/start` endpoint

### Incremental
- [x] Use of `log/slog` for logging
- [ ] Check if `ffmpeg` can completely replace `blueviron/mediamtx` and whether it will be an optimal choice. (or vice-versa :O)
- [ ] Check `cfg.RecordingStorage` quotas and enforce disk limits through host-based notifications or other mechanisms (rolling storage?)
- [ ] Use `errors.Join()` to combine `recordingFilter` validation errors and similar errors across endpoints
- [ ] Evaluate whether `DecodeJSON` would be useful as middleware
- [ ] Optimize request sequences - Should POST /streams be always called before POST /records/start by consumer?
- [ ] Make the derived media TTL (fixed 15 min for replay frames and clips) configurable via `config.json`
- [ ] Move scheduled cleanup into a dedicated service. Add derived-media TTL cleanup; automatic recording expiry must preserve derived media.
- [ ] Decide whether `PUT /streams/{stream-id}/buffer` should reject resizing a stream that is in `failed` state, or whether resizing an already-failed stream's buffer should keep succeeding as it does today
- [ ] Should recording IDs be prefixed with `rec-` as stream IDs are prefixed with `str-`?

## Research/Exploration
- [x] Weigh in tradeoffs of using random UUIDs as primary key in the database - should UUIDv7 be used or a shorter UUID or incremental int prefixed to UUIDs.
- [x] Analyse tradeoffs of using distroless/scratch base image for the container - whether its even feasible or practical for our use case.
- [ ] Should the retrieval (replay APIs) of clip and frame be supported while the recording is ongoing - and not `finalized` or `ready` yet.
- [ ] Evaluate S3-compatible storage tradeoffs for video recordings, especially open recordings and real-time ingestion
- [ ] Evaluate whether fMP4 or another format can reduce MPEG-TS storage overhead while retaining its robustness
- [ ] Evaluate WebM instead of MP4 as the default Replay API clip format to use fully open-source codecs

## Bugs/Issues

- [x] A `sensor_id` and `source_uri` both together make a unique stream, not just the sensor_id. Fix the stream attached error coming up for duplicate streams with the same `sensor_id` but different `source_uri`.
- [x] Even if buffering or stream attachment fails, a re-attachment request fails with Stream_exists. This should not be the behavior.
- [x] Update the unique identifier (`stream_id`) for a stream to be a short uuid prefixed with `sensor_id`. (See related item in Research/Exploration)
- [x] Update OpenAPI specs error response and error codes to be inline with actual implementation.
- [x] Fix incorrect examples for /clip and /frame endpoints in OpenAPI specs.
- [ ] MPEG-TS (and also other alternative fMP4) are unseekable. Cut clips are seekable (MP4). Analyze whether this is a prospective issue.
- [ ] Debug - (intermittent) "no space left on device" issue in docker container while buffering.
- [ ] API Best Practices: /clip and /clip/url (similarly /frame and /frame/url) - Not following the best practice for resource retrieval and URL-based access.
- [ ] Confusing `content_type` field in /clip and /frame endpoints.

# Deferred

Some of these items might have been already reconsidered for the TODO list above.

- Defer pagination for `GET /streams`; pagination is currently planned only for `/records` endpoints
- Do not implement sidecar indexes for keyframes or decoding assistance
- Defer S3-based storage
- Defer authentication and rate limiting; they are out of scope for now
