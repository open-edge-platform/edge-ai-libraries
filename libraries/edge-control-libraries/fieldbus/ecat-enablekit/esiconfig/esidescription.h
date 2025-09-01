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

#ifndef __ESI_DESCRIPTION_H__
#define __ESI_DESCRIPTION_H__

#include "esicommon.h"
#include "esidevice.h"

typedef struct {
    uint8_t* type;
    uint8_t* name;
}esi_GroupType;

typedef struct {
    struct list_head group_list;
    esi_GroupType group;
} esi_group_info;

typedef struct {
    struct list_head groups_list;
}esi_groups_info;

typedef struct {
    esi_groups_info* groups;
    esi_devices_info* devices;
} esi_descriptions_info;
void ecat_esi_parse_descriptions(xmlNodePtr ptr, esi_descriptions_info* description);
void ecat_free_esi_description_info(esi_descriptions_info* descriptions);
#endif

