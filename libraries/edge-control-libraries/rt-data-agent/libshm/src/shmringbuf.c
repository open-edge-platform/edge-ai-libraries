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
#include <unistd.h>
#include <string.h>
#include <malloc.h>
#include <fcntl.h>
#include <errno.h>
#include <assert.h>
#include <stdint.h>
#include <sys/types.h>
#include <sys/mman.h>
#include <sys/shm.h>
#include <safestring/safe_lib.h>

#include "shmringbuf.h"

struct blk_buf_t
{
	uint32_t read;
	uint32_t len;
};

struct blk_ringbuf_t
{
	int fd;
	char name[256];
	uint32_t size;
	uint32_t blks;
	uint32_t blk_size;
	uint32_t rd;
	uint32_t wr;
	struct blk_buf_t blk_bufs[MAX_BLKS];
};

static struct blk_ringbuf_t *blk_ringbuf_init(void *buf, uint32_t blks, uint32_t blk_size)
{
	uint32_t i, blk_offset;
	void *p_blk;
	struct blk_ringbuf_t *p_ring;

	assert(buf && blks && blk_size);
	
	p_ring = (struct blk_ringbuf_t *)buf;
	p_ring->blks = blks;
	p_ring->blk_size = blk_size;
	p_ring->rd = 0;
	p_ring->wr = 0;
	blk_offset = sizeof(struct blk_ringbuf_t);
	p_blk = (void *)((uint8_t *)buf + blk_offset);

	for (i = 0; i < blks; i++)
	{
		p_ring->blk_bufs[i].read = 0;
		p_ring->blk_bufs[i].len = 0;
	}

	return p_ring;
}

static void *get_blkbuf_addr(struct blk_ringbuf_t *p_ring, uint32_t blk)
{
	assert(p_ring);
	void *p_blk = (uint8_t *)p_ring + sizeof(struct blk_ringbuf_t);
	return (void *)((uint8_t *)p_blk + blk * p_ring->blk_size);
}

static int is_blkbuf_writeable(struct blk_ringbuf_t *p_ring)
{
	assert(p_ring);
	uint32_t rd = p_ring->rd;
	uint32_t wr = p_ring->wr;

	/* Always keep one block empty */
	if (((wr + 1) % p_ring->blks) == rd)
		return 0;
	else
		return 1;
}

static int is_blkbuf_readable(struct blk_ringbuf_t *p_ring)
{
	assert(p_ring);
	uint32_t rd = p_ring->rd;
	uint32_t wr = p_ring->wr;

	if (rd == wr)
		return 0;
	else
	{
		return 1;
	}
}

static uint32_t blk_ringbuf_write(struct blk_ringbuf_t *p_ring, void *buf, uint32_t len)
{
	assert(p_ring);
	uint32_t wr = p_ring->wr;
	void *bufaddr = get_blkbuf_addr(p_ring, wr);

	/* Check if the size to be written is too big */
	if (len > p_ring->blk_size) {
		printf("Size %d is bigger then block size %d\n", len, p_ring->blk_size);
		len = p_ring->blk_size;
	}

	/* check if it is writeable */
	if (!is_blkbuf_writeable(p_ring))
		return 0;

	memcpy_s(bufaddr, p_ring->blk_size, buf, len);
	p_ring->blk_bufs[wr].len = len;
	p_ring->wr = (++wr) % p_ring->blks;

	return len;
}

static uint32_t blk_ringbuf_read(struct blk_ringbuf_t *p_ring, void *buf, uint32_t len)
{
	assert(p_ring);
	uint32_t size;
	uint32_t rd = p_ring->rd;
	void *bufaddr = get_blkbuf_addr(p_ring, rd);
	uint8_t *p_read;

	/* check if it is readble */
	if (!is_blkbuf_readable(p_ring))
		return 0; 
	
	/* get max readble size, never across blocks */
	size = p_ring->blk_bufs[rd].len - p_ring->blk_bufs[rd].read;
	size = (size > len)? len: size;
	p_read = (uint8_t *)bufaddr + p_ring->blk_bufs[rd].read;
	memcpy_s(buf, len, (void *)p_read, size);

	p_ring->blk_bufs[rd].read += size;
	if (p_ring->blk_bufs[rd].read == p_ring->blk_bufs[rd].len) {
		p_ring->blk_bufs[rd].read = 0;
		p_ring->rd = (++rd) % p_ring->blks;
	}

	return size;
}

/*
* Public APIs
*/

shm_handle_t shm_blkbuf_init(char *name, uint32_t blks, uint32_t blk_size)
{
	int fd;
	void *shm_addr;
	struct blk_ringbuf_t *p_ring;
	uint32_t blocks = blks + 1 ; /* extra one block to avoid race */
	uint32_t size = sizeof(struct blk_ringbuf_t) + blocks*blk_size;

	assert(name);
	fd = shm_open(name, O_CREAT | O_RDWR, S_IRUSR | S_IWUSR);
    if (fd == -1) {
        perror("shm_open error!");
        return NULL;
    }

	if (ftruncate(fd, size) == -1) {
		perror("ftruncate error!");
		return NULL;
	}

    shm_addr = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (shm_addr == MAP_FAILED) {
        perror("mmap error!");
        return NULL;
    }

	p_ring = blk_ringbuf_init(shm_addr, blocks, blk_size);
	p_ring->size = size;
	p_ring->fd = fd;
	strncpy_s(p_ring->name, 256, name, 256);
	return (shm_handle_t)p_ring;
}

shm_handle_t shm_blkbuf_open(char *name)
{
	int fd;
	void *shm_addr;
	struct blk_ringbuf_t *p_ring;
	uint32_t size;

	assert(name);
	fd = shm_open(name, O_RDWR, 0);
    if (fd == -1) {
        perror("shm_open error!");
        return NULL;
    }

	/* first map to get the size */
    shm_addr = mmap(NULL, sizeof(struct blk_ringbuf_t), PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (shm_addr == MAP_FAILED) {
        perror("mmap error!");
        return NULL;
    }

	/* get size */
	p_ring = (struct blk_ringbuf_t *)shm_addr;
	size = p_ring->size;

	munmap((void *)shm_addr, sizeof(struct blk_ringbuf_t));

	/* Do the real mmap */
	printf("-- size %d\n", size);
    shm_addr = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (shm_addr == MAP_FAILED) {
        perror("mmap error!");
        return NULL;
    }
	return (shm_handle_t)shm_addr;
}

int shm_blkbuf_close(shm_handle_t handle)
{
	struct blk_ringbuf_t *p_ring = (struct blk_ringbuf_t *)handle;
	char name[256];

	strcpy_s(name, 256, p_ring->name);
	munmap((void *)handle, p_ring->size);
	shm_unlink(name);

	return 0;
}

void shm_dump(shm_handle_t handle)
{
	int i;
	struct blk_ringbuf_t *p_ring = (struct blk_ringbuf_t *)handle;

	printf("share memory name %s\n", p_ring->name);
	printf("share memory size %d\n", p_ring->size);
	printf("share memory blocks %d\n", p_ring->blks);
	printf("share memory block size %d\n", p_ring->blk_size);
	printf("p_ring->rd %d\n", p_ring->rd);
	printf("p_ring->wr %d\n", p_ring->wr);

	for (i = 0; i < p_ring->blks; i++)
	{
		printf("blocks %d: read %d, len %d\n",
			i, p_ring->blk_bufs[i].read, p_ring->blk_bufs[i].len);
	}
}

uint32_t shm_blkbuf_write(shm_handle_t handle, void *buf, uint32_t len)
{
	struct blk_ringbuf_t *p_ring = (struct blk_ringbuf_t *)handle;

	return blk_ringbuf_write(p_ring, buf, len);
}

uint32_t shm_blkbuf_read(shm_handle_t handle, void *buf, uint32_t len)
{
	struct blk_ringbuf_t *p_ring = (struct blk_ringbuf_t *)handle;

	return blk_ringbuf_read(p_ring, buf, len);
}

int shm_blkbuf_empty(shm_handle_t handle)
{
	struct blk_ringbuf_t *p_ring = (struct blk_ringbuf_t *)handle;

	return !is_blkbuf_readable(p_ring);
}

int shm_blkbuf_full(shm_handle_t handle)
{
	struct blk_ringbuf_t *p_ring = (struct blk_ringbuf_t *)handle;

	return !is_blkbuf_writeable(p_ring);
}
