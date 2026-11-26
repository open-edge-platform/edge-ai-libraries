# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

<#
.SYNOPSIS
Installs or updates the Windows backend, or checks an existing environment.

.DESCRIPTION
Full setup creates an isolated venv with an existing CPython 3.12 or newer x64 interpreter,
or reuses the interpreter in an existing venv. It then installs backend requirements
and gstreamer-python==1.28.2 for DLStreamer
v2026.2.0. Packages are copied, not hard-linked from uv's cache, because the vendor
Python setup may patch GstAnalytics.py. Existing environments are never recreated.
Rerun full setup after requirements.txt changes. Packages removed from requirements
are not uninstalled, and already satisfied requirements are not forcibly upgraded.
CPython 3.12 x64 is the supported version for gvapython. Newer versions produce a
warning and are experimental; dependency installation and native checks may fail.

Neither mode invokes DLStreamer vendor scripts or validates native libraries.
start.ps1 configures and validates native runtimes before launching the backend.
EnvironmentOnly checks the existing venv and interpreter and configures proxy
settings without installing uv, creating a venv, or installing packages.
start.ps1 uses this mode on every run.
Python downloads and uv project discovery are disabled. Models, native runtimes,
drivers, resource files, the UI and supporting services are not installed here.
Full setup restores the original process environment on success or failure,
except for a deduplicated PATH refresh after installing uv with WinGet.
EnvironmentOnly retains proxy settings on success and restores them on failure.
After failed package installation, rerun setup to retry in the existing valid venv.
An incomplete directory without python.exe or pyvenv.cfg requires inspection or
another location; it is never deleted automatically.

Console messages prefixed with [setup] identify each major operation before it
starts. Output from uv and WinGet remains visible.

.PARAMETER PythonExe
Existing CPython 3.12 or newer x64 executable used to create a new venv during full setup.
An existing venv always uses its own interpreter; PythonExe does not replace it.
Defaults to C:\Program Files\Python312\python.exe. GI need not already be
installed in this base interpreter. Versions newer than 3.12 produce a warning.

.PARAMETER GStreamerRoot
Accepted for compatibility with shared setup/start options. Runtime paths are
configured and validated only by start.ps1.

.PARAMETER DLStreamerRoot
Accepted for compatibility with shared setup/start options. DLStreamer vendor
scripts are invoked only by start.ps1.

.PARAMETER VenvDirectory
Defaults to Vippet\.venv-backend under LocalApplicationData. Full setup creates
or updates a venv; EnvironmentOnly requires an existing valid venv.
Use the same directory for setup and start; activation is not required.

.PARAMETER EnvironmentOnly
Check an existing venv and configure session proxy settings. Does not install
packages or uv, invoke vendor scripts, rebuild caches or patch bindings.

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
Creates or updates the default backend environment.

.EXAMPLE
.\scripts\windows\setup.ps1 -PythonExe 'C:\Runtime\Python\python.exe' -InstallUv
Installs uv through WinGet if needed, then prepares the backend environment.

.EXAMPLE
.\scripts\windows\setup.ps1 -EnvironmentOnly -VenvDirectory 'D:\Vippet\venv-backend'
Checks an existing environment without downloading or installing dependencies.

.EXAMPLE
.\scripts\windows\setup.ps1 -PythonExe 'C:\Runtime\Python\python.exe' -HttpProxy 'http://proxy.example.com:912' -HttpsProxy 'http://proxy.example.com:912' -NoProxy 'localhost,127.0.0.1,.example.com'
Prepares the environment behind a proxy. No proxy address is stored in the repository.

.NOTES
Examples assume the current directory is the ViPPET component root. Replace
example paths with actual installations. EnvironmentOnly changes apply only to this
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

$savedEnvironment = @{}
foreach ($name in @('HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'PATH')) {
    $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
$environmentConfigured = $false
$ErrorActionPreference = 'Stop'
try {
if ($EnvironmentOnly) {
    Write-Host '[setup] Checking the existing backend environment and configuring proxy settings (no package installation)...'
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

Write-Host '[setup] Checking the backend environment directory...'
$venvExists = Test-Path -LiteralPath $VenvDirectory
$existingPython = Join-Path $VenvDirectory 'Scripts\python.exe'
if ($EnvironmentOnly) {
    if (!(Test-Path -LiteralPath $existingPython -PathType Leaf)) {
        throw "Backend environment not found: $VenvDirectory. Run full setup first or select an existing environment."
    }
}
if ($venvExists -and (!(Test-Path -LiteralPath $existingPython -PathType Leaf) -or
    !(Test-Path -LiteralPath (Join-Path $VenvDirectory 'pyvenv.cfg') -PathType Leaf))) {
    throw "Not a valid backend venv: $VenvDirectory. Inspect the incomplete directory or select another location; no files were deleted."
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
    $env:PATH = ((@(
        $env:PATH
        [Environment]::GetEnvironmentVariable('Path', 'User')
        [Environment]::GetEnvironmentVariable('Path', 'Machine')
    ) -join ';') -split ';' | Where-Object { $_ } | Select-Object -Unique) -join ';'
    $savedEnvironment['PATH'] = $env:PATH
    $uv = Get-Command uv -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (!$uv) { throw 'WinGet completed, but uv is still unavailable on PATH. Open a new PowerShell session and rerun setup.ps1.' }
}
Write-Host '[setup] Checking that uv can run...'
& $uv.Path --version
if ($LASTEXITCODE -ne 0) { throw 'uv was found but could not run. Repair its installation before continuing.' }
Write-Host '[setup] Checking the selected Python version and architecture (supported: CPython 3.12 x64)...'
if ($venvExists) {
    if (!$EnvironmentOnly -and $PSBoundParameters.ContainsKey('PythonExe')) {
        Write-Warning 'Reusing the existing venv interpreter; -PythonExe applies only when creating a new environment.'
    }
    $python = (Resolve-Path -LiteralPath $existingPython).Path
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
    if (!$venvExists) {
        Write-Host '[setup] Creating the isolated backend environment...'
        & $uv.Path venv --no-project --no-python-downloads --python $python $VenvDirectory
        if ($LASTEXITCODE -ne 0) { throw 'Creating the backend environment failed.' }
    } else {
        Write-Host '[setup] Reusing the existing backend environment and updating requirements...'
    }
    $venvPython = (Resolve-Path -LiteralPath (Join-Path $VenvDirectory 'Scripts\python.exe')).Path
    $backend = Join-Path $PSScriptRoot '..\..\vippet'
    Write-Host '[setup] Installing backend requirements and Windows GStreamer bindings. Downloads may take a few minutes...'
    & $uv.Path pip install --no-python-downloads --link-mode copy --python $venvPython -r (Join-Path $backend 'requirements.txt') 'gstreamer-python==1.28.2'
    if ($LASTEXITCODE -ne 0) { throw 'Installing backend and Windows GStreamer requirements failed.' }
}
$environmentConfigured = $true
Write-Host "[setup] Completed successfully. Backend environment prepared: $VenvDirectory. Run start.ps1 to configure and validate native runtimes."
} finally {
    if (!$EnvironmentOnly -or !$environmentConfigured) {
        foreach ($name in $savedEnvironment.Keys) {
            [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], 'Process')
        }
    }
}
