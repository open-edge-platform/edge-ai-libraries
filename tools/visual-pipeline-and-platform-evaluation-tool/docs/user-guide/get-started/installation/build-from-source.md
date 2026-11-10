<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Build from Source

Build the Visual Pipeline and Platform Evaluation Tool from source to customize, debug, or extend its
functionality. In this guide, the following tasks are covered:

- Setting up the development environment.
- Compiling the source code and resolving dependencies.
- Generating a runnable build for local testing or deployment.

This guide is intended for developers working directly with the source code.

## Prerequisites

Before starting, ensure the following:

- **System requirements**: The system meets the [minimum requirements](./system-requirements.md).
- **Internet access**: The host has outbound internet connectivity. Base images, apt and Python packages, npm
  dependencies, sample videos, and models are downloaded during the build and on first start. Offline or
  air-gapped installation is not supported. See
  [Network Requirements](./system-requirements.md#network-requirements).
- **Docker platform**: **Docker Engine** is installed. On Linux, install it from the Docker apt repository, see
  [Install Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/), then complete the
  [post-installation steps](https://docs.docker.com/engine/install/linux-postinstall/) to run Docker as a non-root user.

  > [!NOTE]
   > Do not use Docker Desktop on Linux. It runs the Docker daemon inside a virtual machine that is not forwarding GPU
   > device on Linux (yet).

- **Dependencies installed**:
  - **Git**: [Install Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git).
  - **Make**: Standard build tool, typically provided by the `build-essential` (or equivalent) package on Linux.

For GPU and/or NPU usage, appropriate drivers must be installed. The recommended method is to use the DLS installation
script, which detects available devices and installs the required drivers. Follow the `Prerequisites` section in
[Install Guide Ubuntu](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/dlstreamer/install/install_guide_ubuntu.html#prerequisites).

> [!NOTE]
> The same steps apply to Ubuntu 24.04 running under WSL 2 on Windows - run all commands
> inside the WSL distribution. On WSL, only the CPU and GPU (WSL) variants are supported. See
> [System Requirements](./system-requirements.md#windows-subsystem-for-linux-wsl).

This guide assumes basic familiarity with Git commands and terminal usage. For more information, see
[Git Documentation](https://git-scm.com/doc).

Before building, review the [Pre-Installation Steps](./pre-installation-steps.md) for optional
configuration such as the Hugging Face access token used to download models from the
Hugging Face Hub.

## Steps to Build

Choose the section for your host operating system. The Ubuntu procedure builds and runs the
application in Docker. The native Windows procedure prepares a Python environment and starts
the backend directly on the host. Native pipeline compatibility is experimental and depends
on the installed multimedia runtime; the UI and supporting services are separate processes.

### Native Ubuntu 24.04

1. Open a terminal on your Ubuntu host.
1. Install Docker Engine and the Docker Compose plugin using the
   [Docker apt repository instructions](https://docs.docker.com/engine/install/ubuntu/).
   Complete the [post-installation steps](https://docs.docker.com/engine/install/linux-postinstall/)
   so you can run Docker as a non-root user. Do not use Docker Desktop on Linux.
1. Install Git and Make, and configure GPU or NPU drivers if required, as described in
   [Prerequisites](#prerequisites).
1. Verify the tools before continuing:

   ```bash
   git --version
   make --version
   docker info
   docker compose version
   ```

Continue in the same Ubuntu terminal to build and verify the application.

1. Clone the repository:

   ```bash
   cd ~
   git clone https://github.com/open-edge-platform/edge-ai-libraries.git -b main
   cd edge-ai-libraries/tools/visual-pipeline-and-platform-evaluation-tool
   ```

1. Build and start the application:

   ```bash
   make build run
   ```

   Both `make build` and `make run` automatically invoke `setup_env.sh`, which detects the
   available hardware (CPU/GPU/NPU) and writes the appropriate `.env` file. They also create
   the required directories under `shared/`.

   The images are tagged with the version of the checked-out sources (for example `2026.3.0-dev`), or with
   `DOCKER_TAG` if it is set in the environment. `make run` does not rebuild images: after changing the
   sources, run `make build` again. To run published images instead, see
   [Use Pre-Built Docker Images](./docker-compose.md).

1. Verify that the application is running:

   ```bash
   docker compose ps
   ```

1. Access the application:

   Open a browser and navigate to `http://localhost` (or `http://<HOST-IP>`) to access
   the Visual Pipeline and Platform Evaluation Tool UI.

1. Access the application API documentation:

   Open a browser and navigate to `http://localhost/api/v1/docs` (or `http://<HOST-IP>/api/v1/docs`)
   to access the Swagger UI.

### Native Windows

These steps run directly in Windows PowerShell, without WSL or Docker. The Docker, Make and
Linux driver prerequisites above apply to the Ubuntu procedure, not to native Windows.

1. Install [Git for Windows](https://git-scm.com/downloads/win), open PowerShell and verify Git:

   ```powershell
   git --version
   ```

1. Clone the repository and change to the ViPPET component root, not its `vippet` subdirectory:

   ```powershell
   Set-Location $HOME
   git clone https://github.com/open-edge-platform/edge-ai-libraries.git -b main
   Set-Location edge-ai-libraries\tools\visual-pipeline-and-platform-evaluation-tool
   ```

1. Continue with steps 1 through 5 below in the same PowerShell window. You do not need
   to activate a venv, create data directories, copy the recordings YAML or manually run
   the DLStreamer setup scripts. `setup.ps1` prepares Python; `start.ps1` configures
   resources and creates writable directories automatically.

> [!IMPORTANT]
> Install compatible Python, GStreamer, DLStreamer/OpenVINO and Python bindings as described below.
> Installing Python dependencies alone is not sufficient. Multimedia adaptation of the full
> pipeline catalog remains separate. Do not run `make build run`, `setup_env.sh` or the Docker
> commands in this guide as native Windows steps.

## Native Windows subprocess execution

The backend supports Windows subprocess output monitoring and a stdin stop channel.
Linux continues to use its existing pipe monitoring and SIGINT control. Windows readers
drain stdout and stderr independently, preserving FPS parsing and diagnostics.
Cancellation requests the existing GStreamer EOS shutdown, waits up to 10 seconds,
then kills an unresponsive process. Reader errors still trigger subprocess cleanup.
This is per-execution cleanup, not coordinated shutdown of all application workers.

### 1. Install and verify native prerequisites

These scripts target **DLStreamer v2026.2.0**, with an installed **CPython 3.12 x64**
interpreter. The vendor's `gvapython` element requires Python 3.12. Install Python,
compatible GStreamer MSVC x64, DLStreamer Runtime, Python Bindings and Samples components,
and the required GPU/NPU drivers before running setup. Follow the vendor's
[Windows installation guide for v2026.2.0](https://github.com/open-edge-platform/dlstreamer/blob/v2026.2.0/docs/user-guide/install/install_guide_windows.md).
Git for Windows must be on `PATH` when binding patches are needed. The scripts do not
install native runtimes, drivers or Python interpreters and do not download Python.

Newer CPython x64 versions are accepted experimentally in both setup modes. Setup
warns with the selected version and the supported 3.12 version; this does not certify
dependency or `gvapython` compatibility. Older versions and 32-bit interpreters are rejected.

The default locations are:

| Parameter                     | Default                                      |
| ----------------------------- | -------------------------------------------- |
| `PythonExe` (full setup only) | `C:\Program Files\Python312\python.exe`      |
| `GStreamerRoot`               | `C:\Program Files\gstreamer\1.0\msvc_x86_64` |
| `DLStreamerRoot`              | `C:\Program Files\Intel\dlstreamer`          |
| `VenvDirectory`               | `%LOCALAPPDATA%\Vippet\.venv-backend`        |
| `DataDirectory` (start only)  | `%LOCALAPPDATA%\Vippet`                      |

Check your Python installation and registered GStreamer root, adjusting the Python
path if necessary:

```powershell
& 'C:\Program Files\Python312\python.exe' --version
[Environment]::GetEnvironmentVariable('GSTREAMER_1_0_ROOT_MSVC_X86_64', 'Machine')
```

`GStreamerRoot` defaults to `C:\Program Files\gstreamer\1.0\msvc_x86_64`.
It must contain `bin` and `lib\gstreamer-1.0` and match the **system-wide**
`GSTREAMER_1_0_ROOT_MSVC_X86_64` variable. The vendor runtime script reads that
system-wide setting directly; passing another root cannot override it. Repair the
installation or select its registered root if the check fails.

`DLStreamerRoot` defaults to `C:\Program Files\Intel\dlstreamer`. It must contain
`bin`, `scripts\setup_dls_env.ps1` and `scripts\setup_python_env.ps1`. DLStreamer
plugins are loaded from its `bin`, not an assumed `lib\gstreamer-1.0` directory.
An empty DLStreamer root is no longer supported. The installed vendor scripts
validate their Python binding and typelib directories.

There are two entry points: `setup.ps1` for preparation or session configuration,
and `start.ps1` for backend startup. Run all following commands from the ViPPET component root.

Both scripts require a working `uv`. Full setup can install it with `-InstallUv`
in step 3 if WinGet is available. Alternatively, install it beforehand:

```powershell
winget install --id=astral-sh.uv -e --source winget
```

Alternatively, full setup accepts `-InstallUv` to install missing `uv` with
`winget install --id=astral-sh.uv -e --source winget`. This requires WinGet and
never upgrades existing `uv`. Installer failures stop setup. If `uv` remains
unavailable after installation, open a new PowerShell session and retry.

### 2. Configure network access for the current session

Set proxy variables **before** downloading Python, installing uv or packages, or
starting the backend. Skip this example if no proxy is needed or the correct settings
are already inherited. Otherwise, substitute your approved proxy and bypass domains:

```powershell
$env:HTTP_PROXY = 'http://proxy.example.com:912'
$env:HTTPS_PROXY = $env:HTTP_PROXY
$env:NO_PROXY = '127.0.0.1,localhost,::1,.example.com'
```

Both scripts also accept `-HttpProxy`, `-HttpsProxy` and `-NoProxy`. Explicit
parameters replace their respective process environment values; omitted parameters
preserve existing settings. Loopback hosts are always included in `NO_PROXY` so
model-download, metrics and other local HTTP traffic bypass the proxy. Preserve
your organization's approved package-index and registry bypass entries as needed.
No corporate proxy address or credentials are hard-coded, logged or persisted.
Proxy settings must be supplied again in a new session unless already inherited.

WinGet's network/proxy support depends on its installed version and policy; these
variables do not configure Windows system-wide proxy settings. Configure WinGet
separately or install uv beforehand if your managed environment requires it.
For TLS-inspecting proxies, configure approved CA trust for uv and Python according
to your organization's policy. Do not disable certificate verification.

### 3. Prepare the backend once

Choose either the default or custom-location example below. The destination venv
directory must not already exist. Full setup creates it and installs dependencies;
it does not launch the backend. There is no need to activate the venv.

For default locations:

```powershell
.\scripts\windows\setup.ps1 -InstallUv
```

`-PythonExe` defaults to `C:\Program Files\Python312\python.exe` and can be omitted
when Python is installed there. `-InstallUv` only installs missing uv; omit it if uv
is already available. It does not install Python or upgrade existing uv.

Alternatively, to choose explicit locations, define settings shared by setup and start:

```powershell
$common = @{
   GStreamerRoot = 'C:\Program Files\gstreamer\1.0\msvc_x86_64'
   DLStreamerRoot = 'C:\Program Files\Intel\dlstreamer'
   VenvDirectory = "$env:LOCALAPPDATA\Vippet\.venv-backend"
}

.\scripts\windows\setup.ps1 @common `
   -PythonExe 'C:\Program Files\Python312\python.exe' `
   -InstallUv
```

Use the registered runtime paths and an installed interpreter at your actual locations.
Proxy variables set in step 2 are inherited. To supply proxies as script parameters
instead, add `HttpProxy`, `HttpsProxy` and `NoProxy` to `$common`. Keep `PythonExe`
and `InstallUv` on setup only, and `DataDirectory`, service URL parameters and `Port`
on start only; they cannot be shared between both scripts.

Setup uses `uv venv`, then installs `vippet/requirements.txt` plus
`gstreamer-python==1.28.2` with `uv pip install`. Requirements select **OpenVINO 2026.2.0
on Windows** to match DLStreamer v2026.2.0; Linux retains 2026.1.0. Do not separately
install another OpenVINO version. The complete vendor requirements are not installed because they
include `opencv-python`, while ViPPET uses `opencv-python-headless`.

Packages are installed with `--link-mode copy` because the vendor Python script may
patch `GstAnalytics.py` inside the venv. This avoids changing uv's shared package
cache through hard links. The base interpreter does not need GI installed.

Setup then selects the venv Python on `PATH` and calls the **installed** vendor
scripts in order: `setup_dls_env.ps1`, then `setup_python_env.ps1`. They run in the
same PowerShell process without `-Persist`, configure session paths, validate
`gvadetect`, regenerate its plugin registry cache and may patch the binding files.
GI from the selected venv takes precedence over binding paths left by an older
session. Final validation checks GI, `gstgva`, OpenVINO, OpenCV and `gvadetect`.

An existing venv is never overwritten. After failed setup, inspect it manually or
select a new `-VenvDirectory`. Use the same path for setup and start. No activation
script is needed. Follow your script-signing policy; no policy bypass is used.

Wait for `[setup] Completed successfully` before proceeding. Messages prefixed
with `[setup]` identify the current operation; uv and vendor output remains visible.
If setup fails, resolve the reported error before starting the backend.

### 4. Start the backend

After successful default setup, run:

```powershell
.\scripts\windows\start.ps1
```

If you chose the custom-location example, use the same `$common` in the same window:

```powershell
.\scripts\windows\start.ps1 @common `
   -DataDirectory "$env:LOCALAPPDATA\Vippet" `
   -ModelDownloadUrl 'http://127.0.0.1:8000' `
   -MetricsManagerUrl 'http://127.0.0.1:9090' `
   -Port 7860
```

`DataDirectory` controls default writable paths; it does not relocate the venv or
explicit environment overrides. Use the same `VenvDirectory` that setup prepared.
The script stays in the foreground. Leave this terminal open and wait for uvicorn's
`Application startup complete` message; `[start] Launching` alone is not a readiness check.
Startup may download recordings. The API listens at `http://127.0.0.1:7860` by default;
use your selected `-Port` if different. Press Ctrl+C in this terminal to stop it.

Start calls `setup.ps1 -EnvironmentOnly` on **every launch**. This mode checks the
existing venv and configures the vendor runtime and Python bindings for the current
session. It does not create venvs, install dependencies, install uv or download
Python. It still runs the vendor checks, including cache regeneration and optional
binding patches. These vendor scripts execute in the same PowerShell process before
uvicorn starts; the backend and its pipeline subprocesses inherit their environment.
Do not manually run the vendor scripts or setup again before each start.

### 5. Connect resources and supporting services

Start creates missing writable data directories beneath `%LOCALAPPDATA%\Vippet`
(or `-DataDirectory`), preserving explicit environment overrides:

| Setting                                               | Default                                                |
| ----------------------------------------------------- | ------------------------------------------------------ |
| `MODELS_PATH`                                         | `<data>\models\output`                                 |
| `INPUT_VIDEO_DIR`                                     | `<data>\videos\input`                                  |
| `AUTO_VIDEO_DIR`                                      | `<data>\videos\input\auto`                             |
| `UPLOADED_VIDEO_DIR`                                  | `<data>\videos\input\uploaded`                         |
| `OUTPUT_VIDEO_DIR`                                    | `<data>\videos\output`                                 |
| `UPLOADED_IMAGES_DIR`                                 | `<data>\images\input\uploaded`                         |
| `METADATA_DIR`                                        | `<data>\metadata`                                      |
| `DATABASE_URL`                                        | Persistent SQLite database at `<data>\db\app.db`       |
| `SCRIPTS_PATH`                                        | `<component>\shared\scripts`                           |
| `LABELS_PATH`                                         | `<DLStreamerRoot>\samples\labels`                      |
| `PUBLIC_MODEL_PROC_PATH`                              | `<DLStreamerRoot>\samples\gstreamer\model_proc\public` |
| `DEFAULT_RECORDINGS_FILE`                             | `<component>\shared\videos\default_recordings.yaml`    |
| `MODEL_DOWNLOAD_URL`                                  | `http://127.0.0.1:8000`                                |
| `METRICS_MANAGER_URL`                                 | `http://127.0.0.1:9090`                                |
| `LIVE_STREAM_SERVER_HOST` / `LIVE_STREAM_SERVER_PORT` | `127.0.0.1` / `8554`                                   |
| `APP_LOG_LEVEL`                                       | `INFO`                                                 |

The audio input/output directories and database directory are also created. Audio
directories are placeholders; the current backend does not read dedicated audio
path variables. Video handling reads `AUTO_VIDEO_DIR` and `UPLOADED_VIDEO_DIR`, not
the parent `INPUT_VIDEO_DIR` alone.

Read-only resource directories are validated, not created as empty substitutes.
Install DLStreamer Samples or override their paths if absent. Models are not
provided by creating their output directory. The default recordings YAML is read
from the checkout; an explicit missing YAML override retains the backend's
skip-download behavior with a warning. A valid YAML can trigger downloads during
startup, so proxy configuration also matters when launching the backend.

Do not run the old manual directory-preparation block: `start.ps1` provides these
defaults. For nonstandard resources, set only the necessary environment overrides
before start, pointing to existing files or directories. Existing overrides are
preserved, so values from an earlier manual setup can override `-DataDirectory`
and the installed resource defaults. Check them when reusing an existing terminal.

The scripts start only the backend. Start model-download, metrics-manager and an
RTSP server separately when using their features. Configure model-download to write
models into a directory accessible at the backend's `MODELS_PATH`. Container paths
must be mapped to the corresponding host directory. Services on other hosts need
explicit reachable addresses; container DNS names such as `model-download` are not
automatically available on the Windows host.

To connect the development UI, set `VITE_API_URL=http://127.0.0.1:7860` in its
environment before starting it with the existing UI development instructions.

### Subsequent launches and existing environments

In each new PowerShell window, return to the component root, supply any required
proxy settings and custom parameters again, and run `start.ps1`. Recreate `$common`
if using that example; PowerShell variables and session environment changes do not
persist to new terminals. Do not recreate the venv or reinstall dependencies on each launch.

To reuse a manually prepared, complete environment, skip full setup and run:

```powershell
.\scripts\windows\start.ps1 `
    -VenvDirectory "$env:LOCALAPPDATA\Vippet\.venv-backend"
```

This environment must already contain the backend requirements and Windows bindings.
If you only need session configuration for manual pipeline work, without starting API:

```powershell
.\scripts\windows\setup.ps1 -EnvironmentOnly `
    -VenvDirectory "$env:LOCALAPPDATA\Vippet\.venv-backend"
```

This mode requires uv on `PATH`, existing native runtimes and an existing venv.
It does not accept `-PythonExe` or `-InstallUv`, cannot repair missing dependencies,
and is unnecessary before `start.ps1`, which invokes it automatically.

Older Windows environments containing OpenVINO 2026.1.0 must be updated before
session configuration. Otherwise, loading `gstvideoanalytics.dll` or importing
OpenVINO can fail with `The specified procedure could not be found`. Import order
does not fix this version mismatch. For the default venv only:

```powershell
uv pip install --no-python-downloads --link-mode copy `
    --python "$env:LOCALAPPDATA\Vippet\.venv-backend\Scripts\python.exe" `
    'openvino==2026.2.0'
```

Use your actual venv Python path if different. This upgrade is not needed for a new
environment successfully installed from the current requirements.

## Optional: run pipelines on DL Streamer Pipeline Server 2.0 (experimental)

By default, pipelines run inside the `vippet` container. To run them on a separate
[DL Streamer Pipeline Server 2.0](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/microservices/dlstreamer-pipeline-server/dlsps2/README.md)
container instead, add `DLSPS2=1`:

```bash
make build run DLSPS2=1
make stop DLSPS2=1
```

This builds the server image from `microservices/dlstreamer-pipeline-server/dlsps2` in the
same repository, gives it the same devices as `vippet`, and sets
`VIPPET_EXECUTION_BACKEND=dlsps2`. Current limitations:

- Only pipeline validation and single-stream performance tests run on the server. Density
  tests, multi-stream performance tests and tests with latency metrics still run inside
  `vippet`.
- A pipeline that finishes in less than about one second reports 0 FPS.

The server is not part of `compose.yml`, so `docker compose logs` does not show it. Use
`docker logs -f dlstreamer-pipeline-server` to follow its log, or `make shell-dlsps` to
open a shell in it.

## Stop the application

Stop and remove all running containers:

```bash
make stop
```

Downloaded models and videos under `shared/` are preserved. To also remove
those artifacts, run:

```bash
make clean
```
