// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#pragma once

#include <linux/perf_event.h>
#include <sys/types.h>

/* Instruction set count sample

int main(int argc, char **argv)
{
    struct perf_event_attr pe;
    long long count;
    int fd;

    setup_perf_event_attr(&pe);

    fd = perf_event_open(&pe, 0, -1, -1, 0);
    if (fd == -1) {
        fprintf(stderr, "Error opening leader %llx\n", pe.config);
        exit(EXIT_FAILURE);
    }

    perf_event_start_count(fd);

    .......................

    count = perf_event_end_count(fd);
    printf("Used %lld instructions\n", count);

    close(fd);
}
*/

long perf_event_open(struct perf_event_attr* hw_event, pid_t pid, int cpu,
                     int group_fd, unsigned long flags);

int setup_perf_event_attr(struct perf_event_attr* pe);

void perf_event_start_count(int fd);

long long perf_event_end_count(int fd);