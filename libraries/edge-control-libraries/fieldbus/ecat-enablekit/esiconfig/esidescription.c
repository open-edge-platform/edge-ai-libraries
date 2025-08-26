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
 * @file esidescription.c
 * 
 */

#include "esidescription.h"
#include "../include/debug.h"

#include <libxml/parser.h>
#include <libxml/tree.h>
#include <libxml/xmlmemory.h>

#include <ecrt.h>

#define ESI_DESCRIPTION_LOG "ESI_DESCRIPTION: "

void ecat_esi_parse_descriptions(xmlNodePtr ptr, esi_descriptions_info* description)
{
    if (!description) {
        return;
    }
    while (ptr != NULL) {
        if ((!xmlStrcmp(ptr->name, BAD_CAST"Devices"))) {
            if (description->devices == NULL) {
                description->devices = (esi_devices_info*)ecat_malloc(sizeof(esi_devices_info));
                if (description->devices) {
                    memset(description->devices, 0, sizeof(esi_devices_info));
                    INIT_LIST_HEAD(&description->devices->devices_list);
                }
            }
            xmlNodePtr nodePtr = ptr->xmlChildrenNode;
            ecat_esi_parse_devices(nodePtr, description->devices);
        }
        if ((!xmlStrcmp(ptr->name, BAD_CAST"Groups"))) {

        }
        ptr = ptr->next;
    }
}

static void ecat_free_esi_desc_group(esi_groups_info* groups)
{
    if (!groups) {
        return;
    }
    ecat_free(groups);
    groups = NULL;
}

void ecat_free_esi_description_info(esi_descriptions_info* descriptions)
{
    if (!descriptions) {
        return;
    }
    ecat_free_esi_desc_group(descriptions->groups);
    ecat_free_esi_desc_devices(descriptions->devices);
    ecat_free(descriptions);
    descriptions = NULL;
}
