# ---------------------------------------------------------------------------
# genicamapi – internal static library (equivalent to noinst_LTLIBRARIES)
#
# Wraps the rc_genicam_api sources and the bundled GenICam shared libraries.
# It is not installed; it is linked statically into the GStreamer plugin.
#
# Platform notes:
#   Linux   : gentl_wrapper_linux.cc uses dlfcn / dirent for .cti discovery
#   Windows : gentl_wrapper_win.cc  uses LoadLibrary / FindFirstFile
# ---------------------------------------------------------------------------

# Select the platform-specific GenTL dynamic-loader wrapper
if(WIN32)
    set(GENTL_WRAPPER_SRC gentl_wrapper_win.cc)
else()
    set(GENTL_WRAPPER_SRC gentl_wrapper_linux.cc)
endif()

set(GENICAMAPI_SOURCES
    buffer.cc
    config.cc
    cport.cc
    device.cc
    exception.cc
    ${GENTL_WRAPPER_SRC}
    image.cc
    imagelist.cc
    image_store.cc
    interface.cc
    pointcloud.cc
    stream.cc
    system.cc
)

add_library(genicamapi STATIC ${GENICAMAPI_SOURCES})

# Must be PIC so the static lib can be folded into the MODULE/SHARED plugin
set_target_properties(genicamapi PROPERTIES POSITION_INDEPENDENT_CODE ON)

# Consumers need to include headers from this directory;
# GenICam SDK headers are a private build-time detail.
target_include_directories(genicamapi
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}
    PRIVATE
        ${GENICAM_INCLUDE_DIR}
)

# Platform-specific runtime loader dependency
if(WIN32)
    # LoadLibrary / GetProcAddress are in Kernel32 (linked by default on MSVC)
    target_link_libraries(genicamapi PRIVATE)
else()
    # dlopen / dlclose / dlerror live in libdl on Linux
    target_link_libraries(genicamapi PRIVATE dl)
endif()

# Propagate the pre-built GenICam shared-library dependencies to consumers.
target_link_libraries(genicamapi
    PUBLIC
        ${GENICAM_LIBRARIES}
)
