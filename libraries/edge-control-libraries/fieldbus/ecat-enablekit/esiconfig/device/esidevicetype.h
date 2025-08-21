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
 * @file esidevicetype.h
 * 
 */

#ifndef __ESI_DEVICETYPE_H__
#define __ESI_DEVICETYPE_H__

#include "../esicommon.h"

typedef struct {
    uint32_t productCode;
    uint32_t revisionNo;
    uint32_t serialNo;
    uint8_t* name;
}esi_DeviceType_attr;

typedef struct {
    esi_DeviceType_attr attr;
} esi_DeviceType;

void ecat_esi_parse_device_type(xmlNodePtr ptr, esi_DeviceType* device);
void ecat_free_esi_devicetype(esi_DeviceType* attr);
#endif
