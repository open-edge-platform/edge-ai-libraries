// SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions
# and limitations under the License.

## Process this file with automake to produce Makefile.in
EXTRA_DIST =
lib_LTLIBRARIES = libecat.la

AM_CPPFLAGS = \
	-include $(top_builddir)/config.h \
	-DSYSCONFDIR=\""$(sysconfdir)"\" \
	-DLIBEXECDIR=\""$(libexecdir)"\" \
	-I${top_builddir}/libecat \
	-I${top_builddir}/include

AM_CFLAGS = ${my_CFLAGS}

libecat_la_SOURCES = \
	motionentry.c \
	motionentry.h \
	motionutils.c \
	motionutils.h

libecat_la_CFLAGS = -fno-strict-aliasing -Wall -I${LIBXML2_INCLUDE_PATH}/libxml2
if ENABLE_XENOMAI
libecat_la_LDFLAGS = $(AM_LDFLAGS) -L${XENOMAI_DIR}/lib -lethercat_rtdm -no-undefined -version-info $(LIBECAT_LT_VERSION_INFO)
libecat_la_LIBADD = \
	-lethercat_rtdm -lxml2 \
	${top_builddir}/esiconfig/libesiconfig.la \
	${top_builddir}/eniconfig/libeniconfig.la
else
libecat_la_LDFLAGS = $(AM_LDFLAGS) -no-undefined -version-info $(LIBECAT_LT_VERSION_INFO)
if WITH_ETHERCATD
libecat_la_LDFLAGS += -lethercatd
else
libecat_la_LDFLAGS += -lethercat
endif
libecat_la_LIBADD = \
	-lxml2 \
	${top_builddir}/esiconfig/libesiconfig.la \
	${top_builddir}/eniconfig/libeniconfig.la
if WITH_ETHERCATD
libecat_la_LIBADD += -lethercatd
else
libecat_la_LIBADD += -lethercat
endif
endif

include_HEADERS = \
	motionentry.h

CLEANFILES = *~

uninstall-local:
	rm -f $(DESTDIR)$(pkgconfigdir)/libecat.pc
