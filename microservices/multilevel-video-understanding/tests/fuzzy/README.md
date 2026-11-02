<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# RESTler Fuzz Tests

This optional black-box test uses RESTler to fuzz the deployed API described by
`docs/user-guide/_assets/openapi.yaml`. It is intentionally separate from the
default pytest suite because RESTler requires .NET and a running service.

## Prerequisites

Install the .NET 8 SDK in your user directory:

```bash
export DOTNET_VERSION=8.0.414
export DOTNET_ROOT="$HOME/Software/dotnet"
export DOTNET_ARCHIVE="/tmp/dotnet-sdk-${DOTNET_VERSION}-linux-x64.tar.gz"

curl -fL --retry 3 \
	--output "$DOTNET_ARCHIVE" \
	"https://builds.dotnet.microsoft.com/dotnet/Sdk/${DOTNET_VERSION}/dotnet-sdk-${DOTNET_VERSION}-linux-x64.tar.gz"
mkdir -p "$DOTNET_ROOT"
tar -xzf "$DOTNET_ARCHIVE" -C "$DOTNET_ROOT"
export PATH="$DOTNET_ROOT:$PATH"
dotnet --info
```

Build RESTler following the upstream instructions:

```bash
git clone https://github.com/microsoft/restler-fuzzer.git
python restler-fuzzer/build-restler.py --dest_dir "$HOME/Downloads/restler-bin"
export PATH="$PATH:$HOME/Downloads/restler-bin/restler"
Restler --version
```

The `.NET SDK` is required when building RESTler. Add these lines to your shell
profile when RESTler will be rebuilt in new shells:

```bash
export DOTNET_ROOT="$HOME/Software/dotnet"
export PATH="$DOTNET_ROOT:$PATH"
```

Start the service before fuzzing:

```bash
source docker/set_env.sh
./setup_docker.sh --light
```

## Run

Use RESTler's short `test` pass first:

```bash
tests/fuzzy/run_restler_fuzz.sh
```

Run its stateful lean fuzzing mode for a longer duration:

```bash
FUZZ_MODE=fuzz-lean FUZZ_TIME_BUDGET_MINUTES=10 tests/fuzzy/run_restler_fuzz.sh
```

The runner compiles the current OpenAPI specification on every run and creates
a RESTler dictionary containing boundary, path traversal, SSRF, log injection,
and malformed URL payloads. Override `TARGET_IP`, `TARGET_PORT`, `API_SPEC`,
or `RESTLER_OUTPUT_DIR` for another deployment. All generated artifacts remain
under `tests/fuzzy/restler_output/` by default:

- `Compile/` contains the generated grammar and engine settings.
- `Test/` or `FuzzLean/` contains the runtime log, `ResponseBuckets/`, coverage
	reports, and `RestlerResults/*/logs/`.
- `ResponseBuckets/runSummary.json` records bug and HTTP-status totals.
- `coverage_failures_to_investigate.txt` explains operations RESTler could not
	cover.

Inspect `RestlerResults/*/bug_buckets/` for reproducible failures.

RESTler may generate intentional client errors for invalid inputs. Investigate
unexpected `5xx` responses and replay any generated bug bucket after a fix.