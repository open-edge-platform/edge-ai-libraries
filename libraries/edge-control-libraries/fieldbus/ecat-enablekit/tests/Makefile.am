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


EXTRA_DIST =

noinst_PROGRAMS = test-motion

test_motion_SOURCES = test-motionentry.c

test_motion_INCLUDES = \
	${includedir}

test_motion_CFLAGS = -fno-strict-aliasing -Wall -I${LIBXML2_INCLUDE_PATH}/libxml2
test_motion_LDADD = ${top_builddir}/libecat/libecat.la -lxml2
