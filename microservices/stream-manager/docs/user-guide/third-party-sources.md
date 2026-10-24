<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Third-party Sources

Stream Manager includes FFmpeg and other third-party libraries.
A separate source image contains the collected source archives, license notices,
and build records for FFmpeg dependencies and the base image.

## Get the sources

Use the source image for your application release.

> [!NOTE]
> Replace `RELEASE_TAG` with the application release tag.
> Use the same release tag for the source image and the application image.

```bash
source_image_tag='RELEASE_TAG'
docker pull "intel/stream-manager-sources:$source_image_tag"
cid=$(docker create --platform linux/amd64 "intel/stream-manager-sources:$source_image_tag" /not-executed)
mkdir -p stream-manager-sources
docker cp "$cid":/sources/. ./stream-manager-sources/
docker rm "$cid"
```

These commands do not start the container.
Docker copies the source files from the stopped container to the local
`stream-manager-sources` directory.

## Verify the sources

Verify the copied files on a host with `sha256sum`:

```bash
(cd stream-manager-sources && sha256sum -c SHA256SUMS)
```

Read `README.md` and `manifest.json` in the copied directory for source coverage,
versions, and build records.
Keep the license notices with the sources.
