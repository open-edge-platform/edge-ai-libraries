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
 * @file esidevice.c
 * 
 */

#include "esidevice.h"
#include "device/esidevicetype.h"

#define ESI_DEVICE_LOG "ESI_DEVICE: "

static void ecat_esi_parse_device(xmlNodePtr ptr, struct list_head* list)
{
    esi_device_info* device;
    if (!list) {
        return;
    }
    device = (esi_device_info*)ecat_malloc(sizeof(esi_device_info));
    if (!device) {
        return;
    }
    memset(device, 0, sizeof(esi_device_info));
    INIT_LIST_HEAD(&device->device_list);
    INIT_LIST_HEAD(&device->pdos_list);
    while (ptr != NULL) {
        if ((!xmlStrcmp(ptr->name, BAD_CAST"Type"))) {
            ecat_esi_parse_device_type(ptr, &device->type);
        }
        if ((!xmlStrcmp(ptr->name, BAD_CAST"Info"))) {
            ecat_esi_parse_device_info(ptr, &device->info);
        }
        if ((!xmlStrcmp(ptr->name, BAD_CAST"DC"))) {
            if (!device->DC) {
                device->DC = (esi_DeviceDc*)ecat_malloc(sizeof(esi_DeviceDc));
                if (device->DC) {
                    memset(device->DC, 0, sizeof(esi_DeviceDc));
                    INIT_LIST_HEAD(&device->DC->opmodes_list);
                }
            }
            ecat_esi_parse_device_DC(ptr, device->DC);
        }
        if ((!xmlStrcmp(ptr->name, BAD_CAST"RxPdo"))) {
            ecat_esi_parse_device_pdo(ptr, &device->pdos_list, 0);
        }
        if ((!xmlStrcmp(ptr->name, BAD_CAST"TxPdo"))) {
            ecat_esi_parse_device_pdo(ptr, &device->pdos_list, 1);
        }
        ptr = ptr->next;
    }

    list_add_tail(&device->device_list, list);
}


void ecat_esi_parse_devices(xmlNodePtr ptr, esi_devices_info* devices)
{
    if (!devices) {
        return;
    }
    while (ptr != NULL) {
        if ((!xmlStrcmp(ptr->name, BAD_CAST"Device"))) {
            xmlNodePtr nodePtr = ptr->xmlChildrenNode;
            ecat_esi_parse_device(nodePtr, &devices->devices_list);
        }
        ptr = ptr->next;
    }
}

void ecat_free_esi_desc_devices(esi_devices_info* devices)
{
    if (!devices) {
        return;
    }
    esi_device_info* device = NULL;
    esi_device_info* next = NULL;
    list_for_each_entry_safe(device, next, &devices->devices_list, device_list) {
        if (device) {
            list_del(&device->device_list);
            ecat_free_esi_devicetype(&device->type);
            if (device->DC) {
                ecat_free_esi_device_dc_opmode(device->DC);
            }
            ecat_free_esi_pdos_list(&device->pdos_list);
            ecat_free(device);
            device = NULL;
        }
    }
    ecat_free(devices);
    devices = NULL;
}
