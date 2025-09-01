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

noinst_LTLIBRARIES = libesiconfig.la

#AM_CPPFLAGS = -I$(top_srcdir)

SUBDIRS = \
	device
	
libesiconfig_la_SOURCES = \
    esiconfig.c \
    esidescription.c \
    esidevice.c \
    esivendor.c

noinst_HEADERS = \
    esiconfig.h \
    esidescription.h \
    esidevice.h \
    esivendor.h \
    esicommon.h \
    ${top_srcdir}/include/common.h

libesiconfig_la_CPPFLAGS = \
	-I${top_srcdir}

libesiconfig_la_AMFLAGS = -I m4
libesiconfig_la_CFLAGS = -fno-strict-aliasing -Wall -I${LIBXML2_INCLUDE_PATH}/libxml2
if ENABLE_XENOMAI
libesiconfig_la_LDFLAGS = $(AM_LDFLAGS) -L${XENOMAI_DIR}/lib -no-undefined -version-info $(LIBECAT_LT_VERSION_INFO)
libesiconfig_la_LIBADD = -lxml2 ${top_builddir}/esiconfig/device/libesidevice.la
else
libesiconfig_la_LDFLAGS = $(AM_LDFLAGS) -no-undefined -version-info $(LIBECAT_LT_VERSION_INFO)
libesiconfig_la_LIBADD = -lxml2 ${top_builddir}/esiconfig/device/libesidevice.la
endif
CLEANFILES = *~

