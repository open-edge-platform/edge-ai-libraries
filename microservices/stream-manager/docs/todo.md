# TODO

Items are supposed to be considered in order of priority. _(But not to be strictly enforced)_

## Features

### Major
- [ ] PUT /buffer endpoint implementation for resizing stream buffers
- [ ] Add S3 compatible storage for videos
- [ ] Multiple stream_ids in request bodies for start recording

### Incremental
- [ ] Pagination for GET /streams endpoint

## Optimization or Improvements

### Major
- [ ] log/slog for logging
- [ ] Custom error handling framework - Using Custom StreamManError

### Incremental
- [ ] Use errors.Join() in recordingFilter validation and other similar "multiplexed validations" requirement across the endpoints
- [ ] Check if DecodeJSON can be used as a middleware and whether this refactoring has some merits.

# Deffered

Some of these items may be in the pipeline for TODO consideration above.

- [ ] No pagination for GET /streams endpoint for now (Pagination only for /records endpoints).
- [ ] Not implementing sidecar indexes for keyframes/decoding help.
- [ ] Not implementing s3 based storage for now.
- [ ] Not implementing authentication or rate limiting for now (not in scope as well).
