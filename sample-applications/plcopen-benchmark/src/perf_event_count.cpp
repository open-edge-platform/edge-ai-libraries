// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#include <asm/unistd.h>
#include <linux/perf_event.h>
#include <perf_event_count.hpp>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

long perf_event_open(struct perf_event_attr* hw_event, pid_t pid, int cpu,
                     int group_fd, unsigned long flags)
{
  if (!hw_event)
    return -1;

  return syscall(__NR_perf_event_open, hw_event, pid, cpu, group_fd, flags);
}

int setup_perf_event_attr(struct perf_event_attr* pe)
{
  if (!pe)
    return -1;

  memset(pe, 0, sizeof(struct perf_event_attr));
  pe->type           = PERF_TYPE_HARDWARE;
  pe->size           = sizeof(struct perf_event_attr);
  pe->config         = PERF_COUNT_HW_INSTRUCTIONS;
  pe->disabled       = 1;
  pe->exclude_kernel = 1;
  // Don't count hypervisor events.
  pe->exclude_hv = 1;

  return 0;
}

void perf_event_start_count(int fd)
{
  ioctl(fd, PERF_EVENT_IOC_RESET, 0);
  ioctl(fd, PERF_EVENT_IOC_ENABLE, 0);
}

long long perf_event_end_count(int fd)
{
  long long count = 0;
  ioctl(fd, PERF_EVENT_IOC_DISABLE, 0);
  if (read(fd, &count, sizeof(long long)) != -1)
    return count;
  else
    return 0;
}
