// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#pragma once

#include <stdint.h>

int open_tracemark_fd();
int trace_on();
void tracemark(char* fmt, ...) __attribute__((format(printf, 1, 2)));
void close_tracemark_fd();
void trace_off();