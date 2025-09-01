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
 * @file motionutils.c
 * 
 */

#include <stdio.h>
#include <string.h>
#include <ctype.h>
#include <math.h>

#include "motionutils.h"

long motion_strtol(char *src, int base)
{
    long result = 0;
    int count = 0;
    if(src == NULL)
        return 0;
    int len = strlen(src);
    if(base == 16)
        count = 2;
    else if(base == 10)
        count = 0;
    else if(base == 2)
        count = 0;
    while(count < len){
        if(*(src+count) <= 0x39)
            result += (*(src+count)-0x30)*pow(base,len-count-1);
        else if(*(src+count) <= 0x46)
            result += (*(src+count)-0x37)*pow(base,len-count-1);
        else
            result += (*(src+count)-0x57)*pow(base,len-count-1);
        count++;
    }
    return result;
}



