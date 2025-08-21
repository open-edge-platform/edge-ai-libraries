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

#include <stdio.h>
#include <stdlib.h>

#include "shmringbuf.h"

int main(int argc, char **argv)
{
	int i, len;
	uint8_t data[1200] = {0};
	shm_handle_t handle;

	handle = shm_blkbuf_init("shm_test", 10, 1024);

	if(!handle)
		return -1;

	for (i=0; i<5; i++)
	{
		len = shm_blkbuf_write(handle, data, 800);
		printf("len written %d\n", len);
	}

	shm_dump(handle);

	for (i=0; i<6; i++)
	{
		len = shm_blkbuf_read(handle, data, 1100);
		printf("len read %d\n", len);
	}

	shm_dump(handle);

	for (i=0; i<12; i++)
	{
		len = shm_blkbuf_write(handle, data, 600);
		printf("len written %d\n", len);
	}

	shm_dump(handle);

	for (i=0; i<7; i++)
	{
		len = shm_blkbuf_read(handle, data, 350);
		printf("len read %d\n", len);
	}

	shm_dump(handle);
	shm_blkbuf_close(handle);
}
