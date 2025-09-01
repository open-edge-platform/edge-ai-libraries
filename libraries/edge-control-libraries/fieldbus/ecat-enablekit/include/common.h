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

/**
 * 
 * @file common.h
 * 
 */

#ifndef __COMMON_H__
#define __COMMON_H__

#include <stdint.h>
#include <string.h>
#include <stdlib.h>

static inline int ecat_sscanf(const char* key, void* val)
{
    if ((val == NULL) || (key == NULL)) {
        return -1;
    }
    if(sscanf((const char *)key, "#x%x", val) != EOF) {
        /* HexValue */
        return 0;
    } else if(sscanf((const char *)key, "%ld", val) != EOF) {
        /* DecValue */
        return 0;
    }
    return -1;
}

static inline int ecat_sscan_hexbinary(const char* key, uint32_t* val, int32_t size)
{
    char* cur = key;
    uint32_t* curval = val;
    uint8_t* temp;
    if ((val == NULL) || (key == NULL)) {
        return -1;
    }
    uint32_t len = strlen(key);
    while (size > 0) {
        if (sscanf((const char*)cur, "%08x", curval) == EOF) {
            //printf("fail to sscanf(%s)\n",cur);
            return -1;
        }
        temp = (uint8_t*)curval;
        if (len >= 8) {
            *curval = ((0xFFFFFFFF)&(temp[0]<<24))|(temp[1]<<16)|(temp[2]<<8)|(temp[3]);
        } else if(len >= 6) {
            *curval = ((0xFFFFFFFF)&(temp[0]<<16))|(temp[1]<<8)|(temp[2]);
        } else if(len >= 4) {
            *curval = ((0xFFFFFFFF)&(temp[0]<<8))|(temp[1]);
        }
        if (size == 1) {
            break;
        }
        size -= 1;
        cur += 8;
        len -= 8;
        curval += 1;
    }
    return 0;
}

//#define ECAT_MEM_DEBUG

#ifdef ECAT_MEM_DEBUG
#include <execinfo.h>
static void printStack(void) {
    #define STACK_SIZE 32
    void *trace[STACK_SIZE];
    size_t size = backtrace(trace, STACK_SIZE);
    char **symbols = (char **)backtrace_symbols(trace, size);
    size_t i = 0;
    for(; i<size; i++) {
        printf("%d--->%s\n", i, symbols[i]);
    }
    return;
}
#endif
static inline void* ecat_malloc(size_t size)
{
    void* p;
    //if (size == 16)
    //    printStack();
    p = malloc(size);
#ifdef ECAT_MEM_DEBUG
    printf("%s: ecat_malloc (%u) returns %p\n", __func__,(unsigned int)size, p);
#endif
    return p;
}

static inline void ecat_free(void* p)
{
#ifdef ECAT_MEM_DEBUG
    printf("ecat_free pointer %p\n", p);
#endif
    return free(p);
}
#endif
