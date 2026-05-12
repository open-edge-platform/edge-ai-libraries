# gstgencamsrc — Project Guidelines

## Overview

GStreamer source plugin for GenICam cameras. Cross-platform CMake build supports both Linux (Ubuntu 22/24, GCC) and Windows (MSVC). Autotools build (`configure.ac`, `Makefile.am`, `autogen.sh`, `setup.sh`) has been removed — CMake is the only build system.

- Linux plugin: `libgstgencamsrc.so` installed to `/usr/local/lib/gstreamer-1.0/`
- Windows plugin DLL: `C:\dlstreamer_dlls\gstgencamsrc.dll`
- GStreamer (Windows): `C:\Program Files\gstreamer\1.0\msvc_x86_64`
- Cameras tested: Basler (pylon SDK) and Balluff (Impact Acquire SDK)

## Build

### Linux

```bash
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j$(nproc)
sudo cmake --install build
sudo ldconfig
```

`cmake --install` installs:
- `libgstgencamsrc.so` → `/usr/local/lib/gstreamer-1.0/`
- GenICam `.so` files (from `plugins/genicam-core/genicam/bin/`) → `/usr/local/lib/`

**`sudo ldconfig` is required** after install — without it the runtime linker cannot find the GenICam shared libraries and the plugin fails to load with `libGenApi_gcc7_v3_1.so: cannot open shared object file`.

### Windows

```powershell
cd src-gst-gencamsrc
.\build_gencamsrc.ps1                   # auto-downloads GenICam SDK on first run
.\build_gencamsrc.ps1 -FetchGenicamSdk  # force re-download
Copy-Item "build\bin\Release\gstgencamsrc.dll" "C:\dlstreamer_dlls\gstgencamsrc.dll" -Force
```

- GenICam SDK auto-downloaded to `plugins\genicam-core\genicam_win\` on first build (EMVA GenAPI v3.1, VC120/VS2013); folder is git-ignored
- `-GenicamRoot` / `GENICAM_ROOT64` env var still accepted to point at a system-installed SDK instead
- **Source path must be short** (e.g. `C:\p\gencamsrc`). The Development zip contains paths like `GenApi\SnipperTest\XMLExtractionTest_TestGenICamSupport_FloatingInt.h` that push total path length over 260 chars if the source root is deep.

## GenICam SDK Layout

| Platform | Root | Headers | Libraries |
|----------|------|---------|-----------|
| Linux | `plugins/genicam-core/genicam/` | `include/` | `bin/lib*.so` |
| Windows | `plugins/genicam-core/genicam_win/` | `Dev/library/CPP/include/` | `Dev/library/CPP/lib/Win64_x64/` |

`CMakeLists.txt` sets `GENICAM_INCLUDE_DIR` and `GENICAM_LIB_DIR` per-platform automatically.

### GenICam_Package_2018.06.zip structure (Windows download)

The outer zip is a package-of-packages. Key layout:
- `GenICam_Package_2018.06/GenTL/GenTL_v1_5.h` — copied to `Dev/library/CPP/include/GenTL/`
- `GenICam_Package_2018.06/SFNC/PFNC.h` — copied to `Dev/library/CPP/include/GenTL/`
- `GenICam_Package_2018.06/Reference Implementation/*Win64_x64_VS120*.zip` — 4 inner zips:
  - `Development` → extracted to `Dev/` (contains `library/CPP/include/` and `library/CPP/lib/Win64_x64/`)
  - `Runtime`, `CommonRuntime`, `FirmwareUpdateRuntime` → `bin/` copied to `Runtime/bin/`

`GenTL_v1_5.h` and `PFNC.h` are **not** inside the Development inner zip — they are standalone spec files in the outer zip.

## Runtime Environment Setup — Windows (before gst-inspect / gst-launch)

```powershell
$vc120 = "<path-to-src-gst-gencamsrc>\plugins\genicam-core\genicam_win\Runtime\bin\Win64_x64"
$gstRoot = "C:\Program Files\gstreamer\1.0\msvc_x86_64"
$dls = "C:\dlstreamer_dlls"
$env:PATH = "$vc120;$gstRoot\bin;$dls;$env:PATH"
$env:GST_PLUGIN_PATH = $dls
$env:GENICAM_GENTL64_PATH = "C:\Program Files\Balluff\ImpactAcquire\bin\x64"
Remove-Item "C:\Temp\gst-registry-clean.bin" -ErrorAction SilentlyContinue
$env:GST_REGISTRY_1_0 = "C:\Temp\gst-registry-clean.bin"
```

**Always delete the GStreamer registry before testing** — stale cache causes "No such element 'gencamsrc'" even when the DLL is valid.

## Key Source Files

| File | Purpose |
|------|---------|
| `plugins/gstgencamsrc.c` | GStreamer plugin registration, element properties |
| `plugins/genicam.cc` | Core camera class; `Genicam::Start()` enumerates and opens device |
| `plugins/genicam-core/rc_genicam_api/buffer.h` | GenICam buffer API — includes `<cstdint>` for GCC 13 compatibility |
| `plugins/genicam-core/rc_genicam_api/gentl_wrapper_win.cc` | Windows CTI loading via `LoadLibraryA` + symbol resolution |
| `plugins/genicam-core/rc_genicam_api/system.cc` | `getSystems()` scans `GENICAM_GENTL64_PATH` for `.cti` files |

## Known Pitfalls — Do Not Repeat

1. **`genicam.cc` try-catch around `rcg::getDevice()` breaks `gst-inspect`** — the try-catch changes the DLL in a way that breaks plugin registration. Do not add it.

2. **`LoadLibraryExA` with `LOAD_WITH_ALTERED_SEARCH_PATH` breaks `gst-inspect`** — reverted; `LoadLibraryA` is correct here.

3. **Stale GStreamer registry (Windows)** — always `Remove-Item "C:\Temp\gst-registry-clean.bin"` before any `gst-inspect` or `gst-launch` run.

4. **`GST_PLUGIN_SYSTEM_PATH_1_0` is not needed** — GStreamer auto-detects system plugins when `$gstRoot\bin` is in PATH.

5. **Missing `ldconfig` after install (Linux)** — `cmake --install` copies the GenICam `.so` files to `/usr/local/lib/` but the dynamic linker cache is not updated automatically. Always run `sudo ldconfig` (or `ldconfig` inside Docker) after `cmake --install build`.

6. **GCC 13 / Ubuntu 24 stricter headers** — `buffer.h` requires `#include <cstdint>` explicitly. GCC 11 pulled it in transitively; GCC 13 does not. Do not remove the `<cstdint>` include.

7. **`GENICAM_INCLUDE_DIR` is platform-specific** — Windows SDK uses `Dev/library/CPP/include/`, Linux bundled SDK uses `include/`. The `CMakeLists.txt` `if(WIN32)` block handles this; do not hardcode one path.

8. **Em dashes in `.ps1` files cause CP1252 parse errors on Windows** — Git on Linux saves files as UTF-8 but PowerShell on Windows reads them as CP1252 if there is no BOM. The UTF-8 em dash (`U+2014`, `0xE2 0x80 0x94`) becomes `0x94` in CP1252 (right double-quote), breaking string literals. Always use plain ASCII hyphens `-` in `.ps1` files, never em dashes.

9. **Source path must be short for Windows SDK extraction** — The Development zip contains `GenApi\SnipperTest\XMLExtractionTest_TestGenICamSupport_FloatingInt.h`. If the source root exceeds ~80 chars, the extracted path hits the 260-char Windows MAX_PATH limit. Clone or copy the repo to a short path like `C:\p\gencamsrc` before building.

## The Balluff Fix (already applied)

**Root cause**: `LoadLibraryA` on `mvGenTLProducer.cti` succeeds, but Balluff's `DllMain` sets Windows error code 183 (ERROR_ALREADY_EXISTS) as a side effect. The subsequent `GetLastError()` check after all `GetProcAddress` calls incorrectly treats this as a symbol resolution failure, discarding the CTI.

**Fix** (`gentl_wrapper_win.cc`): Call `SetLastError(ERROR_SUCCESS)` before the `GetProcAddress` block to clear the stale error.

**Diagnostic** (`system.cc`): Added `std::cerr` warning in the CTI load failure catch block so failures are visible instead of silent.
