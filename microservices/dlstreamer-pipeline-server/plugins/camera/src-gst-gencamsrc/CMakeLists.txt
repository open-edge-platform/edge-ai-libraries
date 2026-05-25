cmake_minimum_required(VERSION 3.10)

project(gst-gencamsrc
    VERSION 1.3.0
    DESCRIPTION "GStreamer GenICam Source Plugin"
    LANGUAGES C CXX
)

# ---------------------------------------------------------------------------
# Language standards
# ---------------------------------------------------------------------------
set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

# ---------------------------------------------------------------------------
# Platform-specific preprocessor defines and compile options
# ---------------------------------------------------------------------------
if(WIN32)
    add_definitions(-DNOMINMAX)
    add_definitions(-DWIN32_LEAN_AND_MEAN)
    add_definitions(-DWIN32)
endif()

if(MSVC)
    # /W3 warning level; suppress noisy warnings common in GStreamer/GenICam headers
    add_compile_options(/W3 /wd4005 /wd4200 /wd4267 /wd4244 /wd4996)
    string(APPEND CMAKE_C_FLAGS_RELEASE   " /O2 /DNDEBUG")
    string(APPEND CMAKE_CXX_FLAGS_RELEASE " /O2 /DNDEBUG")
else()
    add_compile_options(-Wall)
    string(APPEND CMAKE_C_FLAGS_RELEASE   " -O2 -DNDEBUG")
    string(APPEND CMAKE_CXX_FLAGS_RELEASE " -O2 -DNDEBUG")
endif()

# ---------------------------------------------------------------------------
# GStreamer discovery
#   Linux/macOS : pkg-config (standard)
#   Windows     : pkg-config pointed at GStreamer MSVC installer layout via
#                 PKG_CONFIG_PATH (set by build_gstgencamsrc.ps1), or
#                 GSTREAMER_ROOT cache variable
# ---------------------------------------------------------------------------
if(WIN32)
    # Honour an explicit cache variable first, then env var set by the MSVC
    # GStreamer installer, then a conventional default path.
    if(NOT DEFINED GSTREAMER_ROOT OR GSTREAMER_ROOT STREQUAL "")
        if(DEFINED ENV{GSTREAMER_1_0_ROOT_MSVC_X86_64})
            set(GSTREAMER_ROOT "$ENV{GSTREAMER_1_0_ROOT_MSVC_X86_64}"
                CACHE PATH "GStreamer MSVC installation root")
        else()
            set(GSTREAMER_ROOT "C:/gstreamer/1.0/msvc_x86_64"
                CACHE PATH "GStreamer MSVC installation root")
        endif()
    endif()

    # Point pkg-config at GStreamer's own .pc files (mirrors PS1 script logic)
    set(ENV{PKG_CONFIG_PATH} "${GSTREAMER_ROOT}/lib/pkgconfig")
endif()

find_package(PkgConfig REQUIRED)

pkg_check_modules(GST REQUIRED
    gstreamer-1.0>=1.0.0
    gstreamer-base-1.0>=1.0.0
    gstreamer-controller-1.0>=1.0.0
)

# gstreamer-video-1.0 is needed for <gst/video/video-format.h>
pkg_check_modules(GST_VIDEO REQUIRED
    gstreamer-video-1.0>=1.0.0
)

if(WIN32)
    link_directories(${GST_LIBRARY_DIRS} ${GST_VIDEO_LIBRARY_DIRS})
endif()

# ---------------------------------------------------------------------------
# GenICam SDK paths
#   Linux   : bundled gcc7 SDK in plugins/genicam-core/genicam/
#   Windows : GenICam SDK installed separately; locate via GENICAM_ROOT64 /
#             GENICAM_ROOT env vars (set by SDK installer) or cache variable.
# ---------------------------------------------------------------------------
if(WIN32)
    if(DEFINED ENV{GENICAM_ROOT64})
        set(_DEFAULT_GENICAM_ROOT "$ENV{GENICAM_ROOT64}")
    elseif(DEFINED ENV{GENICAM_ROOT})
        set(_DEFAULT_GENICAM_ROOT "$ENV{GENICAM_ROOT}")
    else()
        set(_DEFAULT_GENICAM_ROOT "C:/Program Files/GenICam")
    endif()
else()
    set(_DEFAULT_GENICAM_ROOT "${CMAKE_SOURCE_DIR}/plugins/genicam-core/genicam")
endif()

set(GENICAM_ROOT "${_DEFAULT_GENICAM_ROOT}"
    CACHE PATH "Root directory of the GenICam SDK")

# Header layout differs by platform:
#   Windows SDK : Dev/library/CPP/include/  (deep layout from SDK installer)
#   Linux SDK   : include/                  (flat layout of bundled gcc7 SDK)
if(WIN32)
    set(GENICAM_INCLUDE_DIR "${GENICAM_ROOT}/Dev/library/CPP/include")
else()
    set(GENICAM_INCLUDE_DIR "${GENICAM_ROOT}/include")
endif()

# Library sub-directory differs by platform
if(WIN32)
    # GenICam Windows SDK ships import libraries under Dev/library/CPP/lib/
    # and runtime DLLs under Runtime/bin/Win64_x64.
    set(GENICAM_LIB_DIR "${GENICAM_ROOT}/Dev/library/CPP/lib/Win64_x64")
    set(GENICAM_RUNTIME_DIR "${GENICAM_ROOT}/Runtime/bin/Win64_x64")
else()
    set(GENICAM_LIB_DIR "${GENICAM_ROOT}/bin")
endif()

# GenICam link-library names differ between Linux (gcc7) and Windows (VC141+)
# Override GENICAM_VC_VERSION on the cmake command line if your SDK uses a
# different MSVC toolset suffix, e.g. -DGENICAM_VC_VERSION=142 for VS2019.
if(WIN32)
    set(GENICAM_VC_VERSION "120" CACHE STRING
        "MSVC toolset suffix used in GenICam lib names (120=VS2013, 141=VS2017, 142=VS2019, 143=VS2022)")
    set(GENICAM_LIBRARY_NAMES
        GenApi_MD_VC${GENICAM_VC_VERSION}_v3_1
        GCBase_MD_VC${GENICAM_VC_VERSION}_v3_1
        log4cpp_MD_VC${GENICAM_VC_VERSION}_v3_1
        Log_MD_VC${GENICAM_VC_VERSION}_v3_1
        XmlParser_MD_VC${GENICAM_VC_VERSION}_v3_1
    )
else()
    set(GENICAM_LIBRARY_NAMES
        GenApi_gcc7_v3_1
        GCBase_gcc7_v3_1
        log4cpp_gcc7_v3_1
        Log_gcc7_v3_1
        MathParser_gcc7_v3_1
        XmlParser_gcc7_v3_1
        NodeMapData_gcc7_v3_1
    )
endif()

# Resolve each GenICam library to its full path.
message(STATUS "GENICAM_LIB_DIR       : ${GENICAM_LIB_DIR}")
set(GENICAM_LIBRARIES "")
foreach(_lib ${GENICAM_LIBRARY_NAMES})
    if(WIN32)
        find_library(_found_${_lib}
            NAMES ${_lib}
            PATHS "${GENICAM_LIB_DIR}"
            NO_DEFAULT_PATH
        )
    else()
        find_library(_found_${_lib}
            NAMES ${_lib}
            PATHS ${GENICAM_LIB_DIR}
            PATH_SUFFIXES ""
        )
    endif()
    if(NOT _found_${_lib})
        message(FATAL_ERROR
            "GenICam library '${_lib}' not found.\n"
            "Searched: ${GENICAM_LIB_DIR}\n"
            "Linux  : bundled .so files are installed automatically by 'cmake --install build'.\n"
            "Windows: install the GenICam SDK and set -DGENICAM_ROOT=<path> or "
            "ensure GENICAM_ROOT64 / GENICAM_ROOT environment variables are set."
        )
    endif()
    list(APPEND GENICAM_LIBRARIES "${_found_${_lib}}")
    unset(_found_${_lib} CACHE)
endforeach()

message(STATUS "Build type       : ${CMAKE_BUILD_TYPE}")
message(STATUS "GenICam root     : ${GENICAM_ROOT}")
message(STATUS "GenICam lib dir  : ${GENICAM_LIB_DIR}")
if(WIN32)
    message(STATUS "GenICam runtime  : ${GENICAM_RUNTIME_DIR}")
endif()
message(STATUS "GenICam libs     : ${GENICAM_LIBRARIES}")

# ---------------------------------------------------------------------------
# Subdirectories (order matters: rc_genicam_api before plugins)
# ---------------------------------------------------------------------------
add_subdirectory(plugins/genicam-core/rc_genicam_api)
add_subdirectory(plugins)

# ---------------------------------------------------------------------------
# Install GenICam shared libraries on Linux so the runtime linker finds them.
# cmake --install copies them to ${CMAKE_INSTALL_PREFIX}/lib (default:
# /usr/local/lib); run ldconfig afterwards to update the shared-library cache.
# ---------------------------------------------------------------------------
if(NOT WIN32)
    include(GNUInstallDirs)
    file(GLOB GENICAM_SHARED_LIBS "${GENICAM_LIB_DIR}/lib*.so*")
    install(FILES ${GENICAM_SHARED_LIBS}
        DESTINATION "${CMAKE_INSTALL_LIBDIR}"
    )
endif()
