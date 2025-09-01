// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
// http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing,
// software distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions
// and limitations under the License.

#ifndef __SHMRINGBUF_H__
#define __SHMRINGBUF_H__

#include <stdint.h>

#ifdef __cplusplus
extern "C"{
#endif

#define MAX_BLKS 32

typedef void * shm_handle_t;

shm_handle_t shm_blkbuf_init(char *name, uint32_t blks, uint32_t blk_size);
shm_handle_t shm_blkbuf_open(char *name);
int shm_blkbuf_close(shm_handle_t handle);
int shm_blkbuf_empty(shm_handle_t handle);
int shm_blkbuf_full(shm_handle_t handle);
uint32_t shm_blkbuf_write(shm_handle_t handle, void *buf, uint32_t len);
uint32_t shm_blkbuf_read(shm_handle_t handle, void *buf, uint32_t len);
void shm_dump(shm_handle_t handle);

#ifdef __cplusplus
}
#endif

#endif
