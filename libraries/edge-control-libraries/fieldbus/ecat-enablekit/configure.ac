# SPDX-License-Identifier: Apache-2.0
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

m4_define([libecat_version_major],[0])
m4_define([libecat_version_minor],[1])
m4_define([libecat_version_micro],[1])
m4_define([libecat_release_status],
    [m4_if(m4_eval(libecat_version_minor % 2), [1], [snapshot], [release])])

m4_define([libecat_version],
    [libecat_version_major.libecat_version_minor.libecat_version_micro])

AC_PREREQ(2.63)
AC_INIT([libecat],[libecat_version],[wei.e.zhang@intel.com])
AC_CONFIG_HEADERS([config.h])
AC_CONFIG_MACRO_DIR([m4])
AM_INIT_AUTOMAKE([foreign -Wall -Werror])

m4_ifdef([AM_SILENT_RULES],[AM_SILENT_RULES([YES])])
m4_ifdef([AM_PROG_LIB],[AM_PROG_LIB],[m4_warn(portability, [Missing AC_PROJ_LIB])])
m4_ifdef([AM_PROG_AR],[AM_PROG_AR])

LIBECAT_VERSION_MAJOR=libecat_version_major
LIBECAT_VERSION_MINOR=libecat_version_minor
LIBECAT_VERSION_MICRO=libecat_version_micro
LIBECAT_VERSION=libecat_version
AC_SUBST([LIBECAT_VERSION_MAJOR])
AC_SUBST([LIBECAT_VERSION_MINOR])
AC_SUBST([LIBECAT_VERSION_MAJOR])
AC_SUBST([LIBECAT_VERSION_MAJOR])
AC_SUBST([LIBECAT_VERSION])

CFLAGS+=" -fno-stack-protector"
#--------------------------------------------------------------------------------------------
# Xenomai path (optional)
#--------------------------------------------------------------------------------------------

AC_ARG_WITH([xenomai-dir],
	AC_HELP_STRING(
		[--with-xenomai-dir=<DIR>],
		[Xenomai path, for RTDM interface and Xenomai examples]
	),
	[
		xenomaidir=[$withval]
		xeno=1
	],
	[
		xenomaidir=""
		xeno=0
	]
)

AC_ARG_WITH([xenomai-config],
	AC_HELP_STRING(
		[--with-xenomai-config=<CMD>],
		[Xenomai config invokation, default to xenomai-dir/bin/xeno-config]
	),
	[
		xenomaiconfig=[$withval]
	],
	[
		xenomaiconfig="$xenomaidir/bin/xeno-config"
	]
)

AC_MSG_CHECKING([for Xenomai path])

if test -z "${xenomaidir}"; then
	AC_MSG_RESULT([not specified.])
else
	if test \! -r ${xenomaiconfig}; then
		AC_MSG_ERROR([no Xenomai installation found in ${xenomaidir}!])
	fi
	AC_MSG_RESULT([$xenomaidir])

	xeno_native_cflags=`$xenomaiconfig --alchemy --cflags`
	xeno_native_ldflags=`$xenomaiconfig --alchemy --ldflags`
	xeno_posix_cflags=`$xenomaiconfig --posix --cflags`
	xeno_posix_ldflags=`$xenomaiconfig --posix --auto-init-solib --ldflags`
	xeno_lib_cflags=`$xenomaiconfig --posix --cflags`
	xeno_lib_ldflags=`$xenomaiconfig --posix --auto-init-solib --ldflags`
fi

AC_SUBST(XENOMAI_DIR,[$xenomaidir])
AM_CONDITIONAL(ENABLE_XENOMAI, test "x$xeno" = "x1")
AC_SUBST(ENABLE_XENOMAI,[$xeno])

AC_SUBST(XENOMAI_NATIVE_CFLAGS,[$xeno_native_cflags])
AC_SUBST(XENOMAI_NATIVE_LDFLAGS,[$xeno_native_ldflags])
AC_SUBST(XENOMAI_POSIX_CFLAGS,[$xeno_posix_cflags])
AC_SUBST(XENOMAI_POSIX_LDFLAGS,[$xeno_posix_ldflags])
AC_SUBST(XENOMAI_LIB_CFLAGS,[$xeno_lib_cflags])
AC_SUBST(XENOMAI_LIB_LDFLAGS,[$xeno_lib_ldflags])

AC_ARG_WITH([libxml2-inc],
	AC_HELP_STRING(
		[--with-libxml2-inc=<CMD>],
		[libxml2 dependency include path, default to /usr/include]
	),
	[
		libxml2inc=[$withval]
	],
	[
		libxml2inc="/usr/include"
	]
)
AC_SUBST(LIBXML2_INCLUDE_PATH,[$libxml2inc])

AC_ARG_WITH([libxml2-lib],
	AC_HELP_STRING(
		[--with-libxml2-lib=<CMD>],
		[libxml2 dependency include path, default to /usr/lib]
	),
	[
		libxml2lib=[$withval]
	],
	[
		libxml2lib="/usr/lib"
	]
)
AC_SUBST(LIBXML2_LIB_PATH,[$libxml2lib])

# Support user-space mode ethercat stack with single-core
AC_MSG_CHECKING([whether to build with libethercatd])

AC_ARG_ENABLE([ethercatd],
	AS_HELP_STRING([--enable-ethercatd],
			[Enable building with libethercatd]),
	[
		case "${enableval}" in
		    yes) ethercatd=1
			;;
		    no) ethercatd=0
			;;
		    *) AC_MSG_ERROR([Invalid value for --enable-ethercatd])
		        ;;
		esac
	 ],
	 [ethercatd=0]
)
if test "x${ethercatd}" = "x1"; then
    AC_DEFINE([WITH_ETHERCATD], [1], [libethercatd support enabled])
    AC_MSG_RESULT([yes])
else
    AC_MSG_RESULT([no])
fi

AM_CONDITIONAL(WITH_ETHERCATD, test "x${ethercatd}" = "x1")
AC_SUBST(WITH_ETHERCATD,[${ethercatd}])

LIBECAT_LD_CURRENT=0
LIBECAT_LD_REVISION=1
LIBECAT_LD_AGE=0
LIBECAT_LT_VERSION_INFO=$LIBECAT_LD_CURRENT:$LIBECAT_LD_REVISION:$LIBECAT_LD_AGE
AC_SUBST(LIBECAT_LT_VERSION_INFO)

AC_CANONICAL_HOST

LT_PREREQ([2.2.6])
m4_pattern_allow([AM_PROG_AR], [AM_PROG_AR])
LT_INIT([disable-static])

# Checks for program.
AC_PROG_CC
AC_PROG_MAKE_SET

# Checks for libraries.
# AM_PATH_ETHERCAT_1_5(1.5.2,,AC_MSG_ERROR(libecat needs igh ethercat master stack 1.5.2))

# Checks for header files.
AC_HEADER_STDC
AC_CHECK_HEADERS([ \
    time.h \
    sys/time.h \
    errno.h \
    ecrt.h \
    stdio.h \
])

# Checks for typedefs, structures, and compiler characteristics.
AC_C_CONST
AC_STRUCT_TM
AC_TYPE_SIZE_T
AC_HEADER_TIME

# Checks for library functions.
AC_FUNC_MKTIME
AC_FUNC_STRFTIME
AC_CHECK_FUNCS([localeconv nl_langinfo strchr])

AC_CONFIG_FILES([
    Makefile
    libecat.pc
    libecat/Makefile
    include/Makefile
    eniconfig/Makefile
    eniconfig/slave/Makefile
    esiconfig/Makefile
    esiconfig/device/Makefile
    examples/Makefile
    examples/ecatmotor/Makefile
    examples/soemotor/Makefile
    examples/ecatdio/Makefile
    examples/multiaxis/Makefile
    tests/Makefile
])
AC_OUTPUT
