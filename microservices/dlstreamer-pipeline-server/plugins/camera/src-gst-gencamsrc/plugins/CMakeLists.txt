# ---------------------------------------------------------------------------
# gstgencamsrc – GStreamer GenICam source plugin
#
# Equivalent to the plugin_LTLIBRARIES target in plugins/Makefile.am.
#
# Platform behaviour:
#   Linux   : built as MODULE (.so) – loaded via dlopen at runtime
#   Windows : built as SHARED (.dll) – MODULE is not supported by MSVC linker;
#             GStreamer’s plugin scanner on Windows loads SHARED DLLs directly
# ---------------------------------------------------------------------------

set(GSTGENCAMSRC_SOURCES
    gstgencamsrc.c
    gencambase.cc
    genicam.cc
)

# On Windows use SHARED (DLL); on Linux use MODULE (.so via dlopen)
if(WIN32)
    set(_PLUGIN_TYPE SHARED)
else()
    set(_PLUGIN_TYPE MODULE)
endif()

add_library(gstgencamsrc ${_PLUGIN_TYPE} ${GSTGENCAMSRC_SOURCES})

target_include_directories(gstgencamsrc
    PRIVATE
        # Plugin source directory (for cross-includes between .c/.cc)
        ${CMAKE_CURRENT_SOURCE_DIR}
        # GenICam SDK headers (Base/GCException.h, GenApi/GenApi.h, etc.)
        ${GENICAM_INCLUDE_DIR}
        # GStreamer headers
        ${GST_INCLUDE_DIRS}
        ${GST_VIDEO_INCLUDE_DIRS}
)

# Extra compiler flags from pkg-config (e.g. -pthread, preprocessor defines)
target_compile_options(gstgencamsrc PRIVATE
    ${GST_CFLAGS_OTHER}
    ${GST_VIDEO_CFLAGS_OTHER}
)

target_link_libraries(gstgencamsrc
    PRIVATE
        # Internal genicam wrapper (transitive GenICam .so/.lib deps)
        genicamapi
        # GStreamer runtime libraries
        ${GST_LIBRARIES}
        ${GST_VIDEO_LIBRARIES}
)

# ---------------------------------------------------------------------------
# Platform-specific output name, prefix, suffix, linker flags
# ---------------------------------------------------------------------------
if(WIN32)
    # GStreamer on Windows scans for gst*.dll (no "lib" prefix)
    set_target_properties(gstgencamsrc PROPERTIES
        PREFIX ""
        SUFFIX ".dll"
        WINDOWS_EXPORT_ALL_SYMBOLS ON
        RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
        LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib"
    )
    # Add GStreamer import-library directory so .lib files are resolved
    target_link_directories(gstgencamsrc PRIVATE
        ${GST_LIBRARY_DIRS}
        ${GST_VIDEO_LIBRARY_DIRS}
    )
else()
    # Linux: GStreamer scans for libgst*.so (keep default "lib" prefix)
    set_target_properties(gstgencamsrc PROPERTIES
        SUFFIX ".so"
    )
endif()

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------
include(GNUInstallDirs)

if(WIN32)
    # Windows: read install dir from GStreamer env var or use a conventional path
    if(DEFINED ENV{GSTREAMER_1_0_ROOT_MSVC_X86_64})
        set(GST_PLUGIN_INSTALL_DIR
            "$ENV{GSTREAMER_1_0_ROOT_MSVC_X86_64}/lib/gstreamer-1.0"
            CACHE PATH "GStreamer plugin install directory")
    else()
        set(GST_PLUGIN_INSTALL_DIR
            "${CMAKE_INSTALL_BINDIR}/gstreamer-1.0"
            CACHE PATH "GStreamer plugin install directory")
    endif()
    install(TARGETS gstgencamsrc
        RUNTIME DESTINATION "${GST_PLUGIN_INSTALL_DIR}"
        LIBRARY DESTINATION "${GST_PLUGIN_INSTALL_DIR}"
    )
else()
    # Linux: mirror the plugindir logic from configure.ac
    if(CMAKE_INSTALL_PREFIX STREQUAL "$ENV{HOME}")
        set(GST_PLUGIN_INSTALL_DIR "$ENV{HOME}/.gstreamer-1.0/plugins")
    else()
        set(GST_PLUGIN_INSTALL_DIR "${CMAKE_INSTALL_LIBDIR}/gstreamer-1.0")
    endif()
    install(TARGETS gstgencamsrc
        LIBRARY DESTINATION "${GST_PLUGIN_INSTALL_DIR}"
    )
endif()
