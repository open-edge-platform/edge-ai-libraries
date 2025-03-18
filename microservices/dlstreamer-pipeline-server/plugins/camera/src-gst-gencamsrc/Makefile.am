SUBDIRS = plugins/genicam-core/rc_genicam_api plugins

EXTRA_DIST = autogen.sh

ACLOCAL_AMFLAGS = -I m4

AM_LDFLAGS = -Wl,--whole-archive /home/pipeline-server/libLicensingLinkLibrary.a -Wl,--no-whole-archive -rdynamic
