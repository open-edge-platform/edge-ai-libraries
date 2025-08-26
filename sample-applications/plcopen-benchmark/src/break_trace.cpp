// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#include <break_trace.hpp>
#include <err.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define TRACEBUFSIZ 1024
#define MAX_PATH 256

static char* fileprefix = (char*)"/sys/kernel/debug/tracing";
static int tracemark_fd = -1;
static int trace_fd     = -1;
static __thread char tracebuf[TRACEBUFSIZ];

int open_tracemark_fd()
{
  char path[MAX_PATH];

  /*
   * open the tracemark file if it's not already open
   */
  sprintf(path, "%s/%s", fileprefix, "trace_marker");
  tracemark_fd = open(path, O_WRONLY);
  if (tracemark_fd < 0)
  {
    warn("unable to open trace_marker file: %s\n", path);
    return -1;
  }

  return tracemark_fd;
}

int trace_on()
{
  char path[MAX_PATH];
  int trace_fd = -1;

  /*
   * if we're not tracing and the tracing_on fd is not open,
   * open the tracing_on file so that we can stop the trace
   * if we hit a breaktrace threshold
   */
  sprintf(path, "%s/%s", fileprefix, "tracing_on");
  if ((trace_fd = open(path, O_WRONLY)) < 0)
  {
    warn("unable to open tracing_on file: %s\n", path);
    return -1;
  }

  return trace_fd;
}

void close_tracemark_fd()
{
  if (tracemark_fd > 0)
    close(tracemark_fd);
}

void trace_off()
{
  if (trace_fd > 0)
    close(trace_fd);
}

void tracemark(char* fmt, ...)
{
  va_list ap;
  int len, ret;

  /* bail out if we're not tracing */
  /* or if the kernel doesn't support trace_mark */
  if (tracemark_fd < 0 || trace_fd < 0)
    return;

  va_start(ap, fmt);
  len = vsnprintf(tracebuf, TRACEBUFSIZ, fmt, ap);
  va_end(ap);

  /* write the tracemark message */
  ret = write(tracemark_fd, tracebuf, len);
  if (ret != len)
    printf("Error: Write tracemark failed.\n");

  /* now stop any trace */
  ret = write(trace_fd, "0\n", 2);
  if (ret != len)
    printf("Error: Stop trace event failed.\n");
}
