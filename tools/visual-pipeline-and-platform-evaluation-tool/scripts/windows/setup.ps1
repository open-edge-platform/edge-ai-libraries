# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

<#
.SYNOPSIS
Prepares the Windows backend or configures an existing environment for this session.

.DESCRIPTION
Full setup creates an isolated venv with an existing CPython 3.12 or newer x64 interpreter,
then installs backend requirements and gstreamer-python==1.28.2 for DLStreamer
v2026.2.0. Packages are copied, not hard-linked from uv's cache, because the vendor
Python setup may patch GstAnalytics.py. Existing environments are never overwritten.
CPython 3.12 x64 is the supported version for gvapython. Newer versions produce a
warning and are experimental; dependency installation and native checks may fail.

Both modes validate installed runtime paths, select the venv's Python on PATH,
and invoke the installed setup_dls_env.ps1 and setup_python_env.ps1 in this
PowerShell process. The vendor scripts configure DLL/plugin/Python/typelib paths,
check gvadetect, rebuild the GStreamer registry cache and may patch Python bindings.
Git must be available when that patch is needed. No -Persist option is used.

EnvironmentOnly performs session configuration and validation without installing
uv, creating a venv, or installing packages. start.ps1 uses this mode on every run.
Python downloads and uv project discovery are disabled. Models, native runtimes,
drivers, resource files, the UI and supporting services are not installed here.
After failed full setup, inspect the incomplete venv or select a new directory.

Console messages prefixed with [setup] identify each major operation before it
starts. Output from uv, WinGet and vendor scripts remains visible.

.PARAMETER PythonExe
Existing CPython 3.12 or newer x64 executable used to create the venv during full setup.
Defaults to C:\Program Files\Python312\python.exe. GI need not already be
installed in this base interpreter. Versions newer than 3.12 produce a warning.

.PARAMETER GStreamerRoot
Installed GStreamer root containing bin and lib\gstreamer-1.0 directories.
Defaults to C:\Program Files\gstreamer\1.0\msvc_x86_64.
Must match the system-wide GSTREAMER_1_0_ROOT_MSVC_X86_64 variable used by the
DLStreamer v2026.2.0 vendor script. No machine-wide setting is changed here.

.PARAMETER DLStreamerRoot
Installed DLStreamer v2026.2.0 root containing bin and scripts\setup_dls_env.ps1
and scripts\setup_python_env.ps1. Defaults to C:\Program Files\Intel\dlstreamer.
Python Bindings must be included in the installed DLStreamer components.

.PARAMETER VenvDirectory
Defaults to Vippet\.venv-backend under LocalApplicationData. Full setup requires
a new directory; EnvironmentOnly requires an existing Scripts\python.exe.
Use the same directory for setup and start; activation is not required.

.PARAMETER EnvironmentOnly
Configure the current session using an existing venv. Does not install packages
or uv. Vendor validation, cache rebuilding and binding patches may still occur.

.PARAMETER InstallUv
Opt in to installing uv with WinGet only when uv is missing from PATH. Defaults
to false. WinGet errors stop setup; no fallback installer or policy bypass is used.
After installation, user and machine PATH entries are appended to this process's
PATH. If uv is still unavailable, open a new PowerShell session and retry.

.PARAMETER HttpProxy
Optional HTTP proxy URL. Overrides HTTP_PROXY for this process and its children.
When omitted, the existing environment value is preserved. Use environment
variables rather than command arguments for proxy credentials.

.PARAMETER HttpsProxy
Optional proxy URL for HTTPS traffic. Overrides HTTPS_PROXY for this process.
An http:// URL is valid for an HTTP CONNECT proxy. Existing settings are preserved
when this parameter is omitted. TLS verification is never disabled.

.PARAMETER NoProxy
Optional comma-separated proxy bypass list replacing the existing NO_PROXY list.
127.0.0.1, localhost and ::1 are always included for local services.

.EXAMPLE
.\scripts\windows\setup.ps1 -PythonExe 'C:\Runtime\Python\python.exe'
Creates the default backend environment and configures DLStreamer for this session.

.EXAMPLE
.\scripts\windows\setup.ps1 -PythonExe 'C:\Runtime\Python\python.exe' -InstallUv
Installs uv through WinGet if needed, then prepares the backend environment.

.EXAMPLE
.\scripts\windows\setup.ps1 -EnvironmentOnly -VenvDirectory 'D:\Vippet\venv-backend'
Configures an existing environment without downloading or installing dependencies.

.EXAMPLE
.\scripts\windows\setup.ps1 -PythonExe 'C:\Runtime\Python\python.exe' -HttpProxy 'http://proxy.example.com:912' -HttpsProxy 'http://proxy.example.com:912' -NoProxy 'localhost,127.0.0.1,.example.com'
Prepares the environment behind a proxy. No proxy address is stored in the repository.

.NOTES
Examples assume the current directory is the ViPPET component root. Replace
example paths with actual installations. Environment changes apply only to this
PowerShell process and future children. Follow your script-signing policy;
execution-policy changes are not part of this procedure.
View this help with Get-Help .\scripts\windows\setup.ps1 -Full.
#>

[CmdletBinding(DefaultParameterSetName = 'Install')]
param(
    [Parameter(ParameterSetName = 'Install')][string]$PythonExe = 'C:\Program Files\Python312\python.exe',
    [Parameter(Mandatory, ParameterSetName = 'Environment')][switch]$EnvironmentOnly,
    [string]$GStreamerRoot = 'C:\Program Files\gstreamer\1.0\msvc_x86_64',
    [ValidateNotNullOrEmpty()]
    [string]$DLStreamerRoot = 'C:\Program Files\Intel\dlstreamer',
    [string]$VenvDirectory = (Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Vippet\.venv-backend'),
    [Parameter(ParameterSetName = 'Install')][switch]$InstallUv,
    [ValidateNotNullOrEmpty()][string]$HttpProxy,
    [ValidateNotNullOrEmpty()][string]$HttpsProxy,
    [ValidateNotNullOrEmpty()][string]$NoProxy
)

$ErrorActionPreference = 'Stop'
if ($EnvironmentOnly) {
    Write-Host '[setup] Configuring the existing backend environment for this session (no package installation)...'
} else {
    Write-Host '[setup] Starting backend environment installation...'
}
Write-Host '[setup] Configuring and validating proxy settings...'
foreach ($proxySetting in @{ HttpProxy = 'HTTP_PROXY'; HttpsProxy = 'HTTPS_PROXY'; NoProxy = 'NO_PROXY' }.GetEnumerator()) {
    if ($PSBoundParameters.ContainsKey($proxySetting.Key)) {
        Set-Item -Path "Env:$($proxySetting.Value)" -Value $PSBoundParameters[$proxySetting.Key]
    }
}
foreach ($proxyName in @('HTTP_PROXY', 'HTTPS_PROXY')) {
    $proxyValue = [Environment]::GetEnvironmentVariable($proxyName, 'Process')
    if ($proxyValue) {
        $proxyUri = $null
        if (![uri]::TryCreate($proxyValue, [UriKind]::Absolute, [ref]$proxyUri) -or
            $proxyUri.Scheme -notin @('http', 'https') -or !$proxyUri.Host) {
            throw "$proxyName must be an absolute HTTP or HTTPS proxy URL."
        }
    }
}
$env:NO_PROXY = ((@($env:NO_PROXY -split ',') + @('127.0.0.1', 'localhost', '::1')) |
    ForEach-Object { $_.Trim() } | Where-Object { $_ } | Select-Object -Unique) -join ','

Write-Host '[setup] Checking GStreamer and DLStreamer installations and system registration...'
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

Write-Host '[setup] Checking the backend environment directory...'
if ($EnvironmentOnly) {
    if (!(Test-Path -LiteralPath (Join-Path $VenvDirectory 'Scripts\python.exe') -PathType Leaf)) {
        throw "Backend environment not found: $VenvDirectory. Run full setup first or select an existing environment."
    }
} elseif (Test-Path -LiteralPath $VenvDirectory) {
    throw "Refusing to overwrite an existing environment: $VenvDirectory. Reuse it with start.ps1 or select a new directory."
}

Write-Host '[setup] Locating uv...'
$uv = Get-Command uv -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if (!$uv) {
    if (!$InstallUv) {
        throw 'uv is not available on PATH. Install it with winget install --id=astral-sh.uv -e, or rerun setup.ps1 with -InstallUv.'
    }
    $winget = Get-Command winget -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (!$winget) { throw 'WinGet is not available. Install uv using an approved method, add it to PATH, and rerun setup.ps1.' }
    Write-Host '[setup] Installing uv with WinGet. This may take a few minutes...'
    & $winget.Path install --id=astral-sh.uv -e --source winget
    if ($LASTEXITCODE -ne 0) { throw "Installing uv with WinGet failed with code $LASTEXITCODE." }
    $env:PATH = (@(
        $env:PATH
        [Environment]::GetEnvironmentVariable('Path', 'User')
        [Environment]::GetEnvironmentVariable('Path', 'Machine')
    ) | Where-Object { $_ }) -join ';'
    $uv = Get-Command uv -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (!$uv) { throw 'WinGet completed, but uv is still unavailable on PATH. Open a new PowerShell session and rerun setup.ps1.' }
}
Write-Host '[setup] Checking that uv can run...'
& $uv.Path --version
if ($LASTEXITCODE -ne 0) { throw 'uv was found but could not run. Repair its installation before continuing.' }
Write-Host '[setup] Checking the selected Python version and architecture (supported: CPython 3.12 x64)...'
if ($EnvironmentOnly) {
    $python = (Resolve-Path -LiteralPath (Join-Path $VenvDirectory 'Scripts\python.exe')).Path
} else {
    $python = (Resolve-Path -LiteralPath $PythonExe).Path
}
$pythonCheckCode = @'
import json
import platform
import struct
import sys
assert platform.python_implementation() == 'CPython' and sys.version_info[:2] >= (3, 12) and struct.calcsize('P') == 8, 'CPython 3.12 or newer x64 is required'
print(json.dumps({'version': platform.python_version(), 'newer': sys.version_info[:2] > (3, 12)}))
'@
$pythonDetailsJson = (& $uv.Path run --no-project --no-python-downloads --python $python -- $python -I -c $pythonCheckCode | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { throw 'The selected interpreter must be CPython 3.12 or newer x64. Check -PythonExe or the existing -VenvDirectory.' }
$pythonDetails = $pythonDetailsJson | ConvertFrom-Json
if ($pythonDetails.newer) {
    Write-Warning "Selected: CPython $($pythonDetails.version) x64. Supported for DLStreamer v2026.2.0 gvapython: CPython 3.12 x64. Continuing experimentally; dependencies, native bindings or gvapython pipelines may be incompatible."
} else {
    Write-Host "[setup] Selected supported interpreter: CPython $($pythonDetails.version) x64."
}
if (!$EnvironmentOnly) {
    Write-Host '[setup] Creating the isolated backend environment...'
    & $uv.Path venv --no-project --no-python-downloads --python $python $VenvDirectory
    if ($LASTEXITCODE -ne 0) { throw 'Creating the backend environment failed.' }
    $venvPython = (Resolve-Path -LiteralPath (Join-Path $VenvDirectory 'Scripts\python.exe')).Path
    $backend = Join-Path $PSScriptRoot '..\..\vippet'
    Write-Host '[setup] Installing backend requirements and Windows GStreamer bindings. Downloads may take a few minutes...'
    & $uv.Path pip install --no-python-downloads --link-mode copy --python $venvPython -r (Join-Path $backend 'requirements.txt') 'gstreamer-python==1.28.2'
    if ($LASTEXITCODE -ne 0) { throw 'Installing backend and Windows GStreamer requirements failed.' }
}
$venvPython = (Resolve-Path -LiteralPath (Join-Path $VenvDirectory 'Scripts\python.exe')).Path
$env:VIRTUAL_ENV = Split-Path -Parent (Split-Path -Parent $venvPython)

Write-Host '[setup] Running DLStreamer setup_dls_env.ps1 (runtime configuration and plugin validation)...'
$global:LASTEXITCODE = 0
& $setupDls
if ($LASTEXITCODE -ne 0) { throw "DLStreamer runtime setup failed with code $LASTEXITCODE." }
$env:PATH = "$(Split-Path -Parent $venvPython);$env:PATH"
$selectedPython = Get-Command python -ErrorAction Stop | Select-Object -First 1
if ($selectedPython.CommandType -ne 'Application' -or $selectedPython.Path -ine $venvPython) {
    throw 'The selected venv Python is not the python command on PATH. Remove conflicting command overrides before continuing.'
}
Write-Host '[setup] Locating GStreamer Python bindings in the selected environment...'
$bindingsPath = (& $uv.Path run --no-project --no-python-downloads --python $venvPython -- $venvPython -I -c "from pathlib import Path; import gstreamer_python; print(Path(gstreamer_python.__file__).parent / 'Lib' / 'site-packages')" | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or !(Test-Path -LiteralPath $bindingsPath -PathType Container)) {
    throw 'The selected venv is missing gstreamer-python==1.28.2 bindings. Run full setup using a new environment directory.'
}
$env:PYTHONPATH = (@($bindingsPath, $env:PYTHONPATH) | Where-Object { $_ }) -join ';'
Write-Host '[setup] Running DLStreamer setup_python_env.ps1 (binding configuration, optional patching and validation)...'
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
Write-Host '[setup] Validating GI, gstgva, OpenVINO, OpenCV and the gvadetect element. Native library loading may take a moment...'
& $uv.Path run --no-project --no-python-downloads --python $venvPython -- $venvPython -c $validationCode
if ($LASTEXITCODE -ne 0) { throw 'The backend environment cannot load its native dependencies.' }
Write-Host "[setup] Completed successfully. Backend environment configured for this session: $env:VIRTUAL_ENV"
