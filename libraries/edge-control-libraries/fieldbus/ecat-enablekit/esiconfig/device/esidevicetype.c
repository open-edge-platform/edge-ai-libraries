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

#include "esidevicetype.h"

void ecat_esi_parse_device_type(xmlNodePtr ptr, esi_DeviceType* device)
{
    if (!device) {
        return;
    }
    if (ptr != NULL) {
        xmlChar* key;
        key = xmlGetProp(ptr, BAD_CAST"ProductCode");
        if (key) {
            ecat_sscanf((const char *)key, &device->attr.productCode);
            xmlFree(key);
        }
        key = xmlGetProp(ptr, BAD_CAST"RevisionNo");
        if (key) {
            ecat_sscanf((const char *)key, &device->attr.revisionNo);
            xmlFree(key);
        }
        key = xmlNodeGetContent(ptr);
        if (key) {
            char len = strlen((const char*)key);
            device->attr.name = ecat_malloc(len+1);
            if (device->attr.name) {
                memset(device->attr.name, 0, len+1);
                memcpy(device->attr.name, (const char*)key, len);
            }
            xmlFree(key);
        }
    }
}

void ecat_free_esi_devicetype(esi_DeviceType* type)
{
    if (!type) {
        return;
    }
    if (type->attr.name) {
        ecat_free(type->attr.name);
        type->attr.name = NULL;
    }
}
