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
 * @file esidevicedc.h
 * 
 */

#ifndef __ESI_DEVICEDC_H__
#define __ESI_DEVICEDC_H__

#include "../esicommon.h"

typedef struct {
    struct list_head opmode_list;
    uint8_t* name;
    uint8_t* desc;
    uint16_t assignactivate;
    uint32_t* cycletimesync0;
    uint32_t* shifttimesync0;
    uint32_t* cycletimesync1;
    uint32_t* shifttimesync1;
} esi_DeviceDcOpmode;

typedef struct {
    struct list_head opmodes_list;
} esi_DeviceDc;

void ecat_esi_parse_device_DC(xmlNodePtr ptr, esi_DeviceDc* dc);
void ecat_free_esi_device_dc_opmode(esi_DeviceDc* dc);
#endif
