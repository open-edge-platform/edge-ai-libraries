# ==============================================================================
# Build script for gstgencamsrc GStreamer GenICam source plugin (Windows)
#
# Prerequisites
# -------------
#   1. Visual Studio 2017 or later (Build Tools are sufficient).
#   2. GStreamer MSVC x86_64 installer from https://gstreamer.freedesktop.org
#      (install both runtime AND development packages)
#   3. GenICam SDK - either:
#      a) Pass -FetchGenicamSdk to download EMVA GenICam v3.1 automatically, OR
#      b) Have a vendor SDK installed (pylon, Impact Acquire, etc.) with
#         GENICAM_ROOT64 / GENICAM_ROOT set by the installer, OR
#      c) Pass -GenicamRoot <path> explicitly.
#   4. pkg-config is bundled inside the GStreamer MSVC install; no separate install needed.
#
# Usage
#   .\build_gencamsrc.ps1
#   .\build_gencamsrc.ps1 -GenicamRoot "D:\GenICam" -VcVersion 120
#   .\build_gencamsrc.ps1 -FetchGenicamSdk          # download SDK automatically
#   .\build_gencamsrc.ps1 -FetchGenicamSdk -TempDir "D:\tmp"  # custom extraction temp dir
# ==============================================================================

param(
    [string]$GenicamRoot     = "",
    [string]$VcVersion       = "120",   # 120=VS2013, 141=VS2017, 142=VS2019, 143=VS2022
    [string]$BuildType       = "Release",
    [switch]$FetchGenicamSdk,             # download EMVA GenICam SDK v3.1 automatically
    [string]$BuildDir        = "",        # override build directory (use a short path if source tree is deep)
    [string]$TempDir         = "C:\tmp"   # short temp dir for SDK extraction; keep short to avoid MAX_PATH
)

$ErrorActionPreference = "Stop"
$SRC_DIR = $PSScriptRoot

# ============================================================================
# Warn if the source path is deep enough to risk MAX_PATH (260 chars) during
# CMake/MSBuild - older .NET IO APIs used by MSBuild do not honour the
# LongPathsEnabled registry key.
# ============================================================================
if ($SRC_DIR.Length -gt 100) {
    Write-Warning "Source path is $($SRC_DIR.Length) characters long. CMake scratch and build paths`nmay exceed Windows MAX_PATH (260 chars) and cause MSB6003 errors.`nConsider cloning to a shorter path (e.g. C:\p\gencamsrc) or passing`n-BuildDir C:\tmp\gencam_build to redirect build output.`nIf SDK extraction also fails, pass -TempDir <short-path> (default: C:\tmp)."
}

# ============================================================================
# Fetch GenICam SDK (auto-triggered when bundled folder is absent and no
# -GenicamRoot / env var is provided, or when -FetchGenicamSdk is passed)
# ============================================================================
$BUNDLED_GENICAM = "$SRC_DIR\plugins\genicam-core\genicam_win"

$needFetch = $FetchGenicamSdk -or (
    ($GenicamRoot -eq "") -and
    (-Not $env:GENICAM_ROOT64) -and
    (-Not $env:GENICAM_ROOT) -and
    (-Not (Test-Path $BUNDLED_GENICAM))
)

if ($needFetch) {
    # EMVA GenICam Package 2018.06 contains GenApi 3.1.0 + VC120 binaries
    $GENICAM_DOWNLOAD_URL = "https://www.emva.org/wp-content/uploads/GenICam_Package_2018.06.zip"
    $GENICAM_ZIP          = "$env:TEMP\GenICam_Package_2018.06.zip"
    # Use a short base path to avoid MAX_PATH during Expand-Archive.
    # Ensure $TempDir exists (C:\tmp is not created by Windows by default).
    if (-Not (Test-Path $TempDir)) { New-Item -ItemType Directory -Path $TempDir | Out-Null }
    $GENICAM_EXTRACT_DIR  = "$TempDir\_gc_$PID"

    Write-Host ""
    Write-Host "========== Fetching GenICam SDK =========="
    Write-Host "URL    : $GENICAM_DOWNLOAD_URL"
    Write-Host "Target : $BUNDLED_GENICAM"

    try {
        # Validate any cached zip; delete and re-download if corrupt/incomplete
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        if (Test-Path $GENICAM_ZIP) {
            try {
                $zipStream = [System.IO.Compression.ZipFile]::OpenRead($GENICAM_ZIP)
                $zipStream.Dispose()
                Write-Host "Using cached zip: $GENICAM_ZIP"
            } catch {
                Write-Warning "Cached zip is corrupt or incomplete, re-downloading..."
                Remove-Item $GENICAM_ZIP -Force
            }
        }

        if (-Not (Test-Path $GENICAM_ZIP)) {
            Write-Host "Downloading..."
            Invoke-WebRequest -Uri $GENICAM_DOWNLOAD_URL -OutFile $GENICAM_ZIP -UseBasicParsing
        }

        Write-Host "Extracting..."
        if (Test-Path $GENICAM_EXTRACT_DIR) { Remove-Item -Recurse -Force $GENICAM_EXTRACT_DIR }
        Expand-Archive -Path $GENICAM_ZIP -DestinationPath $GENICAM_EXTRACT_DIR -Force

        # The GenICam_Package_2018.06.zip is a package-of-packages.
        # The actual Win64 VC120 SDK lives in inner zip files under
        # "Reference Implementation\":
        #   *Win64_x64_VS120*Development* -> Dev\
        #   *Win64_x64_VS120*Runtime*     -> Runtime\  (not CommonRuntime)
        $refDir = Get-ChildItem $GENICAM_EXTRACT_DIR -Recurse -Directory -Filter "Reference Implementation" |
            Select-Object -First 1 -ExpandProperty FullName

        if (-Not $refDir) {
            Write-Host "Extracted top-level contents:"
            Get-ChildItem $GENICAM_EXTRACT_DIR -Recurse -Depth 2 | ForEach-Object { Write-Host "  $($_.FullName)" }
            throw "Cannot locate 'Reference Implementation' folder inside the GenICam zip. Unexpected layout - please re-run with -GenicamRoot <path>."
        }

        # Extract and merge ALL Win64_x64_VS120 zips.
        # Only copy the minimum needed for build and run:
        #   Development zip  -> Dev\library\ (headers + import .lib)  skip symbols/Doc/xml
        #   Runtime zips     -> Runtime\bin\ (DLLs)
        $win64Zips = Get-ChildItem $refDir -Filter "*Win64_x64_VS120*.zip"
        if (-Not $win64Zips) {
            throw "No Win64_x64_VS120 zip files found in '$refDir'."
        }

        if (Test-Path $BUNDLED_GENICAM) { Remove-Item -Recurse -Force $BUNDLED_GENICAM }
        New-Item -ItemType Directory -Path "$BUNDLED_GENICAM\Dev\library" -Force | Out-Null
        New-Item -ItemType Directory -Path "$BUNDLED_GENICAM\Runtime\bin" -Force | Out-Null

        foreach ($z in $win64Zips) {
            Write-Host "Extracting: $($z.Name)"
            $zDir = "$GENICAM_EXTRACT_DIR\_$($z.BaseName)"

            if ($z.Name -match "Development") {
                # Extract full Development zip to the short temp path (no MAX_PATH risk
                # since $zDir is under C:\tmp\_gc_).  Then robocopy the whole tree to
                # Dev\ - skipping only symbols/ and Doc/ - so GenTL headers, xml/, etc.
                # are all captured regardless of where they sit inside the zip.
                Write-Host "  Extracting Development zip to temp..."
                Expand-Archive -Path $z.FullName -DestinationPath $zDir -Force
                Write-Host "  Copying Dev contents from $($z.BaseName)..."
                $null = robocopy $zDir "$BUNDLED_GENICAM\Dev" /E /256 /NFL /NDL /NJH /NJS `
                    /XD "symbols" "Doc"
                if ($LASTEXITCODE -gt 7) { throw "robocopy failed copying Dev from $($z.Name) (exit $LASTEXITCODE)" }
            } else {
                # Runtime, CommonRuntime, FirmwareUpdateRuntime - small zips, full extract then copy bin\
                Expand-Archive -Path $z.FullName -DestinationPath $zDir -Force
                $srcBin = Get-ChildItem $zDir -Recurse -Directory -Filter "bin" | Select-Object -First 1
                if ($srcBin) {
                    Write-Host "  Copying Runtime\bin from $($z.BaseName)..."
                    $null = robocopy $srcBin.FullName "$BUNDLED_GENICAM\Runtime\bin" /E /256 /NFL /NDL /NJH /NJS
                    if ($LASTEXITCODE -gt 7) { throw "robocopy failed copying Runtime\bin from $($z.Name) (exit $LASTEXITCODE)" }
                }
            }
        }

        # GenTL_v1_5.h and PFNC.h live in the outer zip under GenTL\ and SFNC\
        # (not inside the Development inner zip). Copy them into the include tree.
        # Discover the outer folder name dynamically rather than hardcoding it.
        $outerRoot = Get-ChildItem $GENICAM_EXTRACT_DIR -Directory | Select-Object -First 1 -ExpandProperty FullName
        if (-Not $outerRoot) { throw "Outer zip extracted to an unexpected structure (no top-level folder found)." }
        $genTLDest = "$BUNDLED_GENICAM\Dev\library\CPP\include\GenTL"
        New-Item -ItemType Directory -Path $genTLDest -Force | Out-Null
        Copy-Item "$outerRoot\GenTL\GenTL_v1_5.h" $genTLDest -Force
        Copy-Item "$outerRoot\SFNC\PFNC.h"        $genTLDest -Force
        Write-Host "  Copied GenTL_v1_5.h and PFNC.h to Dev\library\CPP\include\GenTL"

        # Verify we got the key pieces
        $devDir = "$BUNDLED_GENICAM\Dev"
        if (-Not (Test-Path "$devDir\library\CPP\include")) {
            Write-Host "Dev contents:"
            Get-ChildItem "$devDir" -Depth 3 | ForEach-Object { Write-Host "  $($_.FullName)" }
            throw "Dev\library\CPP\include not found after extraction. See contents above."
        }
        if (-Not (Test-Path "$devDir\library\CPP\lib\Win64_x64")) {
            throw "Dev\library\CPP\lib\Win64_x64 not found."
        }
        if (-Not (Test-Path "$devDir\library\CPP\include\GenTL\GenTL_v1_5.h")) {
            throw "GenTL\GenTL_v1_5.h not found - unexpected zip layout."
        }

        # Verify version header
        $verHeader = "$BUNDLED_GENICAM\Dev\library\CPP\include\_GenICamVersion.h"
        if (Test-Path $verHeader) {
            $verText = Get-Content $verHeader -Raw
            Write-Host "GenICam version info:"
            $verText -split "`n" | Where-Object { $_ -match 'VERSION|COMPILER|REVISION' } | ForEach-Object { Write-Host "  $_" }
        } else {
            Write-Warning "_GenICamVersion.h not found - zip structure may differ from expected."
        }

        Write-Host "GenICam SDK extracted to: $BUNDLED_GENICAM"
    } catch {
        Write-Error "GenICam SDK fetch failed: $_`n`nManual download: $GENICAM_DOWNLOAD_URL`nExtract Dev\ and Runtime\ into: $BUNDLED_GENICAM"
        exit 1
    } finally {
        if (Test-Path $GENICAM_EXTRACT_DIR) { Remove-Item -Recurse -Force $GENICAM_EXTRACT_DIR -ErrorAction SilentlyContinue }
    }

    # Override GenicamRoot so the locate block below uses the freshly fetched SDK
    $GenicamRoot = $BUNDLED_GENICAM
}

# ============================================================================
# Locate Visual Studio
# ============================================================================
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
if (-Not (Test-Path $vswhere)) {
    Write-Error "vswhere.exe not found. Install Visual Studio Build Tools first."
    exit 1
}
$vsPath = & $vswhere -latest -products * -property installationPath
if (-Not $vsPath) {
    Write-Error "No Visual Studio installation detected by vswhere."
    exit 1
}
Write-Host "VS installation  : $vsPath"

# ============================================================================
# Locate GStreamer
# Priority: registry key set by official installer > GSTREAMER_1_0_ROOT_MSVC_X86_64
# env var > conventional default path.
# ============================================================================
$regPath = "HKLM:\SOFTWARE\GStreamer1.0\x86_64"
$regInstallDir = (Get-ItemProperty -Path $regPath -Name "InstallDir" -ErrorAction SilentlyContinue).InstallDir
if ($regInstallDir) {
    $GSTREAMER_ROOT = $regInstallDir.TrimEnd('\')
    if (-Not $GSTREAMER_ROOT.EndsWith('\1.0\msvc_x86_64')) {
        $GSTREAMER_ROOT = "$GSTREAMER_ROOT\1.0\msvc_x86_64"
    }
} elseif ($env:GSTREAMER_1_0_ROOT_MSVC_X86_64) {
    $GSTREAMER_ROOT = $env:GSTREAMER_1_0_ROOT_MSVC_X86_64.TrimEnd('\')
} else {
    $GSTREAMER_ROOT = "$env:ProgramFiles\gstreamer\1.0\msvc_x86_64"
}
if (-Not (Test-Path $GSTREAMER_ROOT)) {
    Write-Error "GStreamer not found at $GSTREAMER_ROOT.`nInstall from https://gstreamer.freedesktop.org (MSVC x86_64 packages)."
    exit 1
}
Write-Host "GStreamer root   : $GSTREAMER_ROOT"

# Point pkg-config at GStreamer's own .pc files
$env:PKG_CONFIG_PATH = "$GSTREAMER_ROOT\lib\pkgconfig"
# Also add GStreamer's pkg-config.exe to PATH if not already there
$env:PATH = "$GSTREAMER_ROOT\bin;$env:PATH"
Write-Host "PKG_CONFIG_PATH  : $env:PKG_CONFIG_PATH"

# ============================================================================
# Locate GenICam SDK
# ============================================================================
if ($GenicamRoot -ne "") {
    $GENICAM_ROOT = $GenicamRoot
} elseif ($env:GENICAM_ROOT64) {
    $GENICAM_ROOT = $env:GENICAM_ROOT64
} elseif ($env:GENICAM_ROOT) {
    $GENICAM_ROOT = $env:GENICAM_ROOT
} elseif (Test-Path $BUNDLED_GENICAM) {
    # Fall back to the bundled SDK inside the repository
    $GENICAM_ROOT = $BUNDLED_GENICAM
    Write-Host "Using bundled GenICam SDK at: $GENICAM_ROOT"
} else {
    Write-Error "GenICam SDK root not specified.`nOptions:`n  1. Pass -GenicamRoot <path>`n  2. Set GENICAM_ROOT64 / GENICAM_ROOT environment variable`n  3. Pass -FetchGenicamSdk to download automatically`n  4. Manually place the SDK at: $BUNDLED_GENICAM"
    exit 1
}
if (-Not (Test-Path $GENICAM_ROOT)) {
    Write-Error "GenICam SDK not found at $GENICAM_ROOT.`nInstall the GenICam SDK and set GENICAM_ROOT64 / GENICAM_ROOT, or pass -GenicamRoot <path>."
    exit 1
}
Write-Host "GenICam root     : $GENICAM_ROOT"
Write-Host "GenICam VC ver   : $VcVersion"

# ============================================================================
# Launch VS Developer Shell (sets cl.exe, link.exe, etc. on PATH)
# ============================================================================
$VSDEVSHELL = Join-Path $vsPath "Common7\Tools\Launch-VsDevShell.ps1"
if (Test-Path $VSDEVSHELL) {
    Write-Host "Launching VS Dev Shell..."
    & $VSDEVSHELL -Arch amd64
} else {
    Write-Error "VS Dev Shell script not found at $VSDEVSHELL"
    exit 1
}

# ============================================================================
# CMake configure + build
# ============================================================================
if ($BuildDir -ne "") {
    $BUILD_DIR = $BuildDir
} else {
    $BUILD_DIR = "$SRC_DIR\build"
}
if (Test-Path $BUILD_DIR) {
    Write-Host "Removing existing build directory..."
    Remove-Item -Recurse -Force $BUILD_DIR
}
New-Item -ItemType Directory -Path $BUILD_DIR | Out-Null
Write-Host "Build directory  : $BUILD_DIR"

Write-Host ""
Write-Host "========== CMake Configure =========="
cmake `
    -S "$SRC_DIR" `
    -B "$BUILD_DIR" `
    -DCMAKE_BUILD_TYPE="$BuildType" `
    -DGSTREAMER_ROOT="$GSTREAMER_ROOT" `
    -DGENICAM_ROOT="$GENICAM_ROOT" `
    -DGENICAM_VC_VERSION="$VcVersion"

if ($LASTEXITCODE -ne 0) {
    Write-Error "CMake configure failed (exit code $LASTEXITCODE)"
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "========== CMake Build =========="
cmake --build "$BUILD_DIR" --config "$BuildType" --parallel $env:NUMBER_OF_PROCESSORS

if ($LASTEXITCODE -ne 0) {
    Write-Error "CMake build failed (exit code $LASTEXITCODE)"
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "========== Build Complete =========="
Write-Host "Plugin DLL : $BUILD_DIR\bin\$BuildType\gstgencamsrc.dll"
Write-Host ""
Write-Host "To install, run:"
Write-Host "  cmake --install $BUILD_DIR --config $BuildType"
Write-Host ""
Write-Host "Or copy the DLL manually to your GStreamer plugin directory:"
Write-Host "  $GSTREAMER_ROOT\lib\gstreamer-1.0\"
