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
 * @file esipdotype.h
 * 
 */

#ifndef __ESI_PDOTYPE_H__
#define __ESI_PDOTYPE_H__

#include "../esicommon.h"

typedef ec_direction_t ecat_direction_t;
typedef ec_watchdog_mode_t ecat_watchdog_mode_t;

typedef enum {
    UINT8 = 0,
    uINT16
}EsiDataType;

typedef struct {
    struct list_head entry_list;
    uint16_t index;
    uint8_t subIndex;
    uint8_t bitLen;
    EsiDataType type;
}esi_pdo_entry;

typedef struct {
    struct list_head pdo_list;
    uint16_t sm_id;
    uint16_t index;
    uint16_t n_entries;
    struct list_head entry_list;
    ec_direction_t direction;
}esi_pdo_info;

void ecat_esi_parse_device_pdo(xmlNodePtr ptr, struct list_head* list, uint8_t is_input);
void ecat_free_esi_pdos_list(struct list_head* list);
#endif
