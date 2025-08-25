#------------------------------------------------------------------------------
#
#  $Id$
#
#  Copyright (C) 2006-2012  Florian Pose, Ingenieurgemeinschaft IgH
#
#  This file is part of the IgH EtherCAT Master.
#
#  The IgH EtherCAT Master is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License version 2, as
#  published by the Free Software Foundation.
#
#  The IgH EtherCAT Master is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
#  Public License for more details.
#
#  You should have received a copy of the GNU General Public License along with
#  the IgH EtherCAT Master; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
#
#  ---
#
#  The license mentioned above concerns the source code only. Using the
#  EtherCAT technology and brand is only permitted in compliance with the
#  industrial property and similar rights of Beckhoff Automation GmbH.
#
#------------------------------------------------------------------------------

noinst_PROGRAMS = ecat_multi_axis_example

ecat_multi_axis_example_SOURCES = main.c circle.c

if ENABLE_XENOMAI
ecat_multi_axis_example_CFLAGS = \
	-Wall \
	-lm \
	-I${top_builddir}/libecat \
	$(XENOMAI_POSIX_CFLAGS)

ecat_multi_axis_example_LDFLAGS = \
	-L$(top_builddir)/libecat \
$(XENOMAI_POSIX_LDFLAGS)
else
ecat_multi_axis_example_CFLAGS = \
	-Wall \
	-lm \
	-I${top_builddir}/libecat

ecat_multi_axis_example_LDFLAGS = \
	-L$(top_builddir)/libecat -lrt -lpthread
endif

ecat_multi_axis_example_LDADD = \
	$(top_builddir)/libecat/libecat.la
#------------------------------------------------------------------------------
