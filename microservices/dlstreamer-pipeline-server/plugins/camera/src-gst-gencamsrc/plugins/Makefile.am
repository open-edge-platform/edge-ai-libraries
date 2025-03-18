plugin_LTLIBRARIES = libgstgencamsrc.la

# sources used to compile this plug-in
libgstgencamsrc_la_SOURCES = gstgencamsrc.c \
			     gstgencamsrc.h \
			     gencambase.cc \
			     gencambase.h \
			     genicam.cc \
			     genicam.h

# compiler and linker flags used to compile this plugin, set in configure.ac
libgstgencamsrc_la_CFLAGS = $(GST_CFLAGS)
libgstgencamsrc_la_LIBADD = ../plugins/genicam-core/rc_genicam_api/libgenicamapi.la $(GST_LIBS)
libgstgencamsrc_la_LDFLAGS = $(GST_PLUGIN_LDFLAGS) $(GST_LICENSE_PLUGIN_LDFLAGS)
