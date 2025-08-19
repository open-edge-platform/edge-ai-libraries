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


noinst_PROGRAMS = ecat_soe_example

ecat_soe_example_SOURCES = \
	single_soe_vel.c

if ENABLE_XENOMAI
ecat_soe_example_CFLAGS = \
	-Wall \
	-I${top_builddir}/libecat \
	$(XENOMAI_POSIX_CFLAGS)

ecat_soe_example_LDFLAGS = \
	-L$(top_builddir)/libecat \
	$(XENOMAI_POSIX_LDFLAGS)
else
ecat_soe_example_CFLAGS = \
	-Wall \
	-I${top_builddir}/libecat

ecat_soe_example_LDFLAGS = \
	-L$(top_builddir)/libecat -lrt -lpthread

endif

ecat_soe_example_LDADD = \
	$(top_builddir)/libecat/libecat.la

