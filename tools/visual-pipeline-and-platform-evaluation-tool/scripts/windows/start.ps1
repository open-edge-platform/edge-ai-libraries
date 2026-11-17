# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

<#
.SYNOPSIS
Starts the native Windows ViPPET API with configured runtimes and data paths.

.DESCRIPTION
Calls setup.ps1 -EnvironmentOnly to check the existing venv and configure proxy
settings, then directly invokes setup_dls_env.ps1 and setup_python_env.ps1 to
configure the installed DLStreamer v2026.2.0 runtime and Python bindings. Starts
uvicorn via uv run using that explicit interpreter. Project discovery and Python
downloads are disabled; startup does not create venvs or install dependencies.
Vendor scripts may rebuild the plugin cache and patch bindings during validation.
The API listens only on 127.0.0.1, on port 7860 by default. The script runs in
the foreground and restores the original working directory and managed environment
variables on exit, including when preparation or backend startup fails. Repeated
starts can use different data directories without retaining generated defaults.

Missing data-path variables are set beneath DataDirectory and their directories
are created. Existing nonempty environment overrides take precedence:
MODELS_PATH, INPUT_VIDEO_DIR, AUTO_VIDEO_DIR, UPLOADED_VIDEO_DIR, OUTPUT_VIDEO_DIR,
UPLOADED_IMAGES_DIR and METADATA_DIR. Creates audio\input, audio\output and db
under DataDirectory. DATABASE_URL defaults to a persistent SQLite database at
db\app.db, rather than the backend's in-memory default.

SCRIPTS_PATH defaults to this checkout's shared\scripts. LABELS_PATH and
PUBLIC_MODEL_PROC_PATH default to DLStreamer's installed samples. These resource
directories must exist and are not created as empty substitutes. The default
recordings YAML comes from this checkout's shared\videos\default_recordings.yaml.
An explicit DEFAULT_RECORDINGS_FILE override is preserved; a missing override
warns that automatic recording downloads will be skipped.

Unspecified MODEL_DOWNLOAD_URL, METRICS_MANAGER_URL and LIVE_STREAM_SERVER_HOST
default to local services (ports 8000, 9090 and RTSP 8554). APP_LOG_LEVEL defaults
to INFO. Existing environment overrides are preserved. Supporting services and
the UI must be started separately. Backend startup can download recordings and
other external resources. Proxy settings apply to setup, uv and the backend.
Environment changes affect the backend and its children, not system settings,
and are restored in the calling process when this script exits.

Console messages prefixed with [start] and [setup] identify preparation stages.
After launch, uvicorn logs report backend readiness and runtime activity.

.PARAMETER GStreamerRoot
Installed GStreamer root. Defaults to C:\Program Files\gstreamer\1.0\msvc_x86_64.
Must match the system-wide GSTREAMER_1_0_ROOT_MSVC_X86_64 setting.

.PARAMETER DLStreamerRoot
Installed DLStreamer v2026.2.0 root containing bin, scripts and Python bindings.
Defaults to C:\Program Files\Intel\dlstreamer. Python Bindings must be installed.

.PARAMETER VenvDirectory
Existing backend environment. Defaults to Vippet\.venv-backend under the current
user's LocalApplicationData folder. Must match setup.ps1's VenvDirectory.

.PARAMETER DataDirectory
Base for data paths that are not already set in the environment. Defaults to
Vippet under LocalApplicationData. Does not relocate explicit environment paths
or change VenvDirectory. Prefer an absolute path for custom locations.

.PARAMETER ModelDownloadUrl
Optional model-download service URL. When supplied, replaces MODEL_DOWNLOAD_URL
for this session; otherwise the existing environment or http://127.0.0.1:8000 applies.
Configure the service to use model files accessible at the backend's MODELS_PATH.

.PARAMETER MetricsManagerUrl
Optional metrics-manager service URL. When supplied, replaces METRICS_MANAGER_URL
for this session; otherwise the existing environment or http://127.0.0.1:9090 applies.

.PARAMETER HttpProxy
Optional HTTP proxy URL forwarded to setup.ps1. Overrides HTTP_PROXY for this
process; omitted settings retain their existing environment values.

.PARAMETER HttpsProxy
Optional HTTPS traffic proxy forwarded to setup.ps1. Overrides HTTPS_PROXY.
Use environment variables instead of arguments for credentials. TLS verification
is not disabled; configure your organization's trusted CA separately if required.

.PARAMETER NoProxy
Optional comma-separated NO_PROXY replacement. setup.ps1 always includes
127.0.0.1, localhost and ::1 so local service traffic bypasses the proxy.

.PARAMETER Port
Local API port, from 1 to 65535. Defaults to 7860. Does not change the loopback
binding or configure the UI automatically.

.EXAMPLE
.\scripts\windows\start.ps1
Starts the backend at http://127.0.0.1:7860 using the default environment and
data directories and GStreamer at C:\Program Files\gstreamer\1.0\msvc_x86_64,
plus DLStreamer at C:\Program Files\Intel\dlstreamer. Existing environment
overrides are preserved.

.EXAMPLE
$env:LABELS_PATH = 'C:\Program Files\Intel\dlstreamer\samples\labels'
$env:MODELS_PATH = 'D:\AI\models'
$env:PUBLIC_MODEL_PROC_PATH = 'D:\AI\model-proc'
$env:DEFAULT_RECORDINGS_FILE = 'D:\Vippet\custom-recordings.yaml'
$startOptions = @{
    GStreamerRoot = 'C:\Runtime\gstreamer'
    DLStreamerRoot = 'C:\Program Files\Intel\dlstreamer'
    VenvDirectory = 'D:\Vippet\venv-backend'
    DataDirectory = 'D:\Vippet\data'
    ModelDownloadUrl = 'http://127.0.0.1:8000'
    MetricsManagerUrl = 'http://127.0.0.1:9090'
    Port = 7861
}
.\scripts\windows\start.ps1 @startOptions
Starts at http://127.0.0.1:7861 with custom resources, services and environment.
Provide the referenced resource files and start supporting services separately.

.NOTES
Examples assume the current directory is the ViPPET component root. Replace all
example paths and service addresses with actual locations. For a development UI,
set VITE_API_URL to the API URL in the UI process environment before starting it.
Successful API startup does not guarantee every pipeline or hardware plugin is
compatible with the selected Windows runtime.
View this help with Get-Help .\scripts\windows\start.ps1 -Full.
#>

param(
    [string]$GStreamerRoot = 'C:\Program Files\gstreamer\1.0\msvc_x86_64',
    [ValidateNotNullOrEmpty()]
    [string]$DLStreamerRoot = 'C:\Program Files\Intel\dlstreamer',
    [string]$VenvDirectory = (Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Vippet\.venv-backend'),
    [string]$DataDirectory = (Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Vippet'),
    [string]$ModelDownloadUrl,
    [string]$MetricsManagerUrl,
    [ValidateNotNullOrEmpty()][string]$HttpProxy,
    [ValidateNotNullOrEmpty()][string]$HttpsProxy,
    [ValidateNotNullOrEmpty()][string]$NoProxy,
    [ValidateRange(1, 65535)][int]$Port = 7860
)

$savedEnvironment = @{}
foreach ($name in @('HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'PATH', 'VIRTUAL_ENV',
    'GSTREAMER_1_0_ROOT_MSVC_X86_64', 'DLSTREAMER_DIR', 'GST_PLUGIN_PATH',
    'PYTHONPATH', 'PYGI_DLL_DIRS', 'GI_TYPELIB_PATH', 'SCRIPTS_PATH', 'LABELS_PATH',
    'PUBLIC_MODEL_PROC_PATH', 'DEFAULT_RECORDINGS_FILE', 'MODELS_PATH', 'INPUT_VIDEO_DIR',
    'AUTO_VIDEO_DIR', 'UPLOADED_VIDEO_DIR', 'OUTPUT_VIDEO_DIR', 'UPLOADED_IMAGES_DIR',
    'METADATA_DIR', 'DATABASE_URL', 'MODEL_DOWNLOAD_URL', 'METRICS_MANAGER_URL',
    'LIVE_STREAM_SERVER_HOST', 'LIVE_STREAM_SERVER_PORT', 'APP_LOG_LEVEL')) {
    $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
$ErrorActionPreference = 'Stop'
try {
Write-Host '[start] Preparing the backend session with setup.ps1 -EnvironmentOnly...'
$setupOptions = @{
    EnvironmentOnly = $true
    VenvDirectory = $VenvDirectory
}
foreach ($proxyParameter in @('HttpProxy', 'HttpsProxy', 'NoProxy')) {
    if ($PSBoundParameters.ContainsKey($proxyParameter)) {
        $setupOptions[$proxyParameter] = $PSBoundParameters[$proxyParameter]
    }
}
& "$PSScriptRoot\setup.ps1" @setupOptions
$uv = Get-Command uv -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
$python = (Resolve-Path -LiteralPath (Join-Path $VenvDirectory 'Scripts\python.exe')).Path

Write-Host '[start] Checking GStreamer and DLStreamer installations and system registration...'
$gstreamer = (Resolve-Path -LiteralPath $GStreamerRoot).Path.TrimEnd('\')
$dlstreamer = (Resolve-Path -LiteralPath $DLStreamerRoot).Path
foreach ($directory in @((Join-Path $gstreamer 'bin'), (Join-Path $gstreamer 'lib\gstreamer-1.0'), (Join-Path $dlstreamer 'bin'))) {
    if (!(Test-Path -LiteralPath $directory -PathType Container)) { throw "Required runtime directory not found: $directory" }
}
$setupDls = Join-Path $dlstreamer 'scripts\setup_dls_env.ps1'
$setupPython = Join-Path $dlstreamer 'scripts\setup_python_env.ps1'
foreach ($script in @($setupDls, $setupPython)) {
    if (!(Test-Path -LiteralPath $script -PathType Leaf)) { throw "Required DLStreamer script not found: $script" }
}
$machineGStreamer = [Environment]::GetEnvironmentVariable('GSTREAMER_1_0_ROOT_MSVC_X86_64', 'Machine')
if (!$machineGStreamer -or (Resolve-Path -LiteralPath $machineGStreamer).Path.TrimEnd('\') -ine $gstreamer) {
    throw 'GStreamerRoot must match the installed system-wide GSTREAMER_1_0_ROOT_MSVC_X86_64 setting required by DLStreamer v2026.2.0. Repair the GStreamer installation or select its registered root.'
}
$env:GSTREAMER_1_0_ROOT_MSVC_X86_64 = $gstreamer
$env:VIRTUAL_ENV = Split-Path -Parent (Split-Path -Parent $python)

Write-Host '[start] Running DLStreamer setup_dls_env.ps1 (runtime configuration and plugin validation)...'
$global:LASTEXITCODE = 0
& $setupDls
if ($LASTEXITCODE -ne 0) { throw "DLStreamer runtime setup failed with code $LASTEXITCODE." }
$env:PATH = ((@(Split-Path -Parent $python) + @($env:PATH -split ';')) |
    Where-Object { $_ } | Select-Object -Unique) -join ';'
$selectedPython = Get-Command python -ErrorAction Stop | Select-Object -First 1
if ($selectedPython.CommandType -ne 'Application' -or $selectedPython.Path -ine $python) {
    throw 'The selected venv Python is not the python command on PATH. Remove conflicting command overrides before continuing.'
}
Write-Host '[start] Locating GStreamer Python bindings in the selected environment...'
$bindingsPath = (& $uv.Path run --no-project --no-python-downloads --python $python -- $python -I -c "from pathlib import Path; import gstreamer_python; print(Path(gstreamer_python.__file__).parent / 'Lib' / 'site-packages')" | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or !(Test-Path -LiteralPath $bindingsPath -PathType Container)) {
    throw 'The selected venv is missing GStreamer Python bindings. Rerun full setup for this environment.'
}
$env:PYTHONPATH = ((@($bindingsPath, (Join-Path $dlstreamer 'python')) + @($env:PYTHONPATH -split ';')) |
    Where-Object { $_ } | Select-Object -Unique) -join ';'
$env:PYGI_DLL_DIRS = ((@((Join-Path $gstreamer 'bin')) + @($env:PYGI_DLL_DIRS -split ';')) |
    Where-Object { $_ } | Select-Object -Unique) -join ';'
$typelibDirectory = Join-Path $dlstreamer 'lib\girepository-1.0'
if (!(Test-Path -LiteralPath $typelibDirectory -PathType Container)) {
    $typelibDirectory = Join-Path $dlstreamer 'build\src\gst\metadata'
}
$env:GI_TYPELIB_PATH = ((@($typelibDirectory) + @($env:GI_TYPELIB_PATH -split ';')) |
    Where-Object { $_ } | Select-Object -Unique) -join ';'
Write-Host '[start] Running DLStreamer setup_python_env.ps1 (binding configuration, optional patching and validation)...'
$global:LASTEXITCODE = 0
$previousErrorActionPreference = $ErrorActionPreference
try {
    $ErrorActionPreference = 'Continue'
    & $setupPython
} finally {
    $ErrorActionPreference = $previousErrorActionPreference
}
if ($LASTEXITCODE -ne 0) { throw "DLStreamer Python setup failed with code $LASTEXITCODE." }

$validationCode = @'
import struct
import sys
from pathlib import Path
import gi
import gstgva
import openvino
import cv2
assert sys.implementation.name == 'cpython' and sys.version_info[:2] >= (3, 12) and struct.calcsize('P') == 8, 'CPython 3.12 or newer x64 is required'
assert Path(gi.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()), 'GI was loaded from another Python environment'
gi.require_version('Gst', '1.0')
from gi.repository import Gst
Gst.init(None)
assert Gst.ElementFactory.make('gvadetect', None) is not None, 'gvadetect is unavailable'
print('Python:', sys.executable)
print(Gst.version_string())
'@
Write-Host '[start] Validating GI, gstgva, OpenVINO, OpenCV and the gvadetect element. Native library loading may take a moment...'
& $uv.Path run --no-project --no-python-downloads --python $python -- $python -c $validationCode
if ($LASTEXITCODE -ne 0) { throw 'The backend environment cannot load its native dependencies.' }

$component = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$dataRoot = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($DataDirectory)
if ($ModelDownloadUrl) { $env:MODEL_DOWNLOAD_URL = $ModelDownloadUrl }
if ($MetricsManagerUrl) { $env:METRICS_MANAGER_URL = $MetricsManagerUrl }

Write-Host '[start] Validating scripts, labels and model-proc resource directories...'
$resourcePaths = @{
    SCRIPTS_PATH = (Join-Path $component 'shared\scripts')
    LABELS_PATH = (Join-Path $DLStreamerRoot 'samples\labels')
    PUBLIC_MODEL_PROC_PATH = (Join-Path $DLStreamerRoot 'samples\gstreamer\model_proc\public')
}
foreach ($name in $resourcePaths.Keys) {
    $resource = [Environment]::GetEnvironmentVariable($name, 'Process')
    if (!$resource) { $resource = $resourcePaths[$name] }
    if (!(Test-Path -LiteralPath $resource -PathType Container)) {
        throw "Resource directory for $name not found: $resource. Install the DLStreamer Samples component or set an existing resource directory."
    }
    Set-Item -Path "Env:$name" -Value (Resolve-Path -LiteralPath $resource).Path
}
Write-Host '[start] Configuring the recordings YAML...'
if (!$env:DEFAULT_RECORDINGS_FILE) {
    $recordings = Join-Path $component 'shared\videos\default_recordings.yaml'
    if (!(Test-Path -LiteralPath $recordings -PathType Leaf)) { throw "Default recordings YAML not found: $recordings" }
    $env:DEFAULT_RECORDINGS_FILE = $recordings
} else {
    $env:DEFAULT_RECORDINGS_FILE = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($env:DEFAULT_RECORDINGS_FILE)
    if (!(Test-Path -LiteralPath $env:DEFAULT_RECORDINGS_FILE -PathType Leaf)) {
        Write-Warning 'DEFAULT_RECORDINGS_FILE does not exist; automatic recording downloads will be skipped.'
    }
}

Write-Host '[start] Preparing writable data directories and database configuration...'
$dataPaths = @{
    MODELS_PATH = 'models\output'
    INPUT_VIDEO_DIR = 'videos\input'
    AUTO_VIDEO_DIR = 'videos\input\auto'
    UPLOADED_VIDEO_DIR = 'videos\input\uploaded'
    OUTPUT_VIDEO_DIR = 'videos\output'
    UPLOADED_IMAGES_DIR = 'images\input\uploaded'
    METADATA_DIR = 'metadata'
}
foreach ($name in $dataPaths.Keys) {
    $dataPath = [Environment]::GetEnvironmentVariable($name, 'Process')
    if (!$dataPath) { $dataPath = Join-Path $dataRoot $dataPaths[$name] }
    $dataPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($dataPath)
    Set-Item -Path "Env:$name" -Value $dataPath
    New-Item -ItemType Directory -Force -Path $dataPath | Out-Null
}
foreach ($directory in @('audio\input', 'audio\output', 'db')) {
    New-Item -ItemType Directory -Force -Path (Join-Path $dataRoot $directory) | Out-Null
}
if (!$env:DATABASE_URL) {
    $dbPath = (Join-Path $dataRoot 'db\app.db').Replace('\', '/')
    $env:DATABASE_URL = "sqlite+aiosqlite:///$dbPath"
}
Write-Host '[start] Configuring service addresses and application logging...'
$serviceDefaults = @{
    MODEL_DOWNLOAD_URL = 'http://127.0.0.1:8000'
    METRICS_MANAGER_URL = 'http://127.0.0.1:9090'
    LIVE_STREAM_SERVER_HOST = '127.0.0.1'
    LIVE_STREAM_SERVER_PORT = '8554'
    APP_LOG_LEVEL = 'INFO'
}
foreach ($name in $serviceDefaults.Keys) {
    if (![Environment]::GetEnvironmentVariable($name, 'Process')) {
        Set-Item -Path "Env:$name" -Value $serviceDefaults[$name]
    }
}

Push-Location (Join-Path $component 'vippet')
try {
    Write-Host "[start] Launching the native API via uv with $python on 127.0.0.1:$Port"
    Write-Host '[start] Waiting for backend initialization. Recordings may be downloaded; watch uvicorn logs for readiness. Press Ctrl+C to stop.'
    & $uv.Path run --no-project --no-python-downloads --python $python -- $python -m uvicorn api.main:app --host 127.0.0.1 --port $Port
    if ($LASTEXITCODE -ne 0) { throw "Backend exited with code $LASTEXITCODE" }
    Write-Host '[start] Backend stopped successfully.'
} finally {
    Pop-Location
}
} finally {
    foreach ($name in $savedEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], 'Process')
    }
}
