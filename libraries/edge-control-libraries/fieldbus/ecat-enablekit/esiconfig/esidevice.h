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
 * @file esidevice.h
 * 
 */

#ifndef __ESI_DEVICE_H__
#define __ESI_DEVICE_H__

#include "esicommon.h"
#include "device/esidevicetype.h"
#include "device/esideviceinfo.h"
#include "device/esidevicedc.h"
#include "device/esipdotype.h"

typedef struct {
    struct list_head device_list;
    esi_DeviceType type;
    esi_InfoType info;
    esi_DeviceDc* DC;
    struct list_head pdos_list;
} esi_device_info;

typedef struct {
    struct list_head devices_list;
} esi_devices_info;

void ecat_esi_parse_devices(xmlNodePtr ptr, esi_devices_info* devices);
void ecat_free_esi_desc_devices(esi_devices_info* devices);
#endif
