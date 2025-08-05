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

# Process this file with automake to produce Makefile.in

CLEANFILES =
ACLOCAL_AMFLAGS = -I m4 ${ACLOCAL_FLAGS}
AM_MAKEFLAGS = --no-print-directory

pkgconfigdir = $(libdir)/pkgconfig
pkgconfig_DATA = libecat.pc
EXTRA_DIST = libecat.pc.in
CLEANFILES += libecat.pc

dist_doc_DATA =

SUBDIRS = \
	include \
	eniconfig \
	esiconfig \
	libecat

# userspace example and tests depends on libmotion
SUBDIRS += \
	tests \
	examples

DIST_SUBDIRS = \
	eniconfig \
	esiconfig \
	examples

