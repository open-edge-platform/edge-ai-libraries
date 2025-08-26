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
 * @file eniconfig.c
 * 
 */

#include "esiconfig.h"
#include "../include/debug.h"

#include <libxml/parser.h>
#include <libxml/tree.h>
#include <libxml/xmlmemory.h>

#include <ecrt.h>

#define SLAVE_PROFILE_LOG "SLAVE_PROFILE: "

uint16_t ecat_esi_get_pdo_size_by_sm_id(esi_device_info* device, uint16_t sm_id)
{
    if (!device) {
        return 0;
    }
    if (list_empty(&device->pdos_list)) {
        return 0;
    }
    esi_pdo_info* pdo = NULL;
    uint16_t size = 0;
    list_for_each_entry(pdo, &device->pdos_list, pdo_list) {
        if (pdo) {
            if (pdo->sm_id == sm_id) {
                size++;
            }
        }
    }
    return size;
}

uint16_t ecat_esi_get_sm_size(esi_device_info* device)
{
    if (!device) {
        return 0;
    }
    if (list_empty(&device->pdos_list)) {
        return 0;
    }
    uint16_t size = 0;
    esi_pdo_info* pdo = NULL;
    list_for_each_entry(pdo, &device->pdos_list, pdo_list) {
        if (pdo) {
            if (size < pdo->sm_id) {
                size = pdo->sm_id;
            }
        }
    }
    return (size+1);
}

static void ecat_init_slave_esi(ecat_slave_esi* esi)
{
    if (!esi) {
        return;
    }

    memset(esi,0, sizeof(ecat_slave_esi));
}

ecat_slave_esi* ecat_load_slave_profile(char* name)
{
    ecat_slave_esi* esi;
    xmlDocPtr doc;
    xmlNodePtr cur;

    if (!name) {
        MOTION_CONSOLE_ERR(SLAVE_PROFILE_LOG "xml configuration name is Null!\n");
        return NULL;
    }

    doc = xmlParseFile(name);
    if (!doc) {
        MOTION_CONSOLE_ERR(SLAVE_PROFILE_LOG "Failed to parse xml file(%s)!\n", name);
        goto FAILED;
    }
    cur = xmlDocGetRootElement(doc);
    if (!cur) {
        MOTION_CONSOLE_ERR(SLAVE_PROFILE_LOG "Root is empty\n");
        goto FAILED;
    }

    if ((xmlStrcmp(cur->name, BAD_CAST"EtherCATInfo"))) {
        MOTION_CONSOLE_ERR(SLAVE_PROFILE_LOG "The root is not EtherCATInfo\n");
        goto FAILED;
    }

    cur = cur->xmlChildrenNode;
    if (!cur) {
        MOTION_CONSOLE_ERR(SLAVE_PROFILE_LOG "The format of slave is not correct");
        goto FAILED;
    }

    esi = (ecat_slave_esi*)ecat_malloc(sizeof(ecat_slave_esi));
    if (!esi) {
        MOTION_CONSOLE_ERR(SLAVE_PROFILE_LOG "slave esi profile alloc failed.\n");
        goto FAILED;
    }

    ecat_init_slave_esi(esi);
    while (cur != NULL) {
        if ((!xmlStrcmp(cur->name, BAD_CAST"Vendor"))) {
            if (esi->vendor == NULL) {
                esi->vendor = (esi_VendorType*)ecat_malloc(sizeof(esi_VendorType));
                if (esi->vendor) {
                    memset(esi->vendor, 0, sizeof(esi_VendorType));
                }
            }
            xmlNodePtr nodePtr = cur->xmlChildrenNode;
            ecat_esi_parse_vendor(nodePtr, esi->vendor);
        }
        if ((!xmlStrcmp(cur->name, BAD_CAST"Descriptions"))) {
            if (esi->descriptions == NULL) {
                esi->descriptions = (esi_descriptions_info*)ecat_malloc(sizeof(esi_descriptions_info));
                if (esi->descriptions) {
                    memset(esi->descriptions, 0, sizeof(esi_descriptions_info));
                }
            }
            xmlNodePtr nodePtr = cur->xmlChildrenNode;
            ecat_esi_parse_descriptions(nodePtr, esi->descriptions);
        }
        cur = cur->next;
    }
    xmlFreeDoc(doc);
    doc = NULL;
    return esi;
FAILED:
    if (doc) {
        xmlFreeDoc(doc);
        doc = NULL;
    }
    return NULL;
}

void ecat_free_esi_profile(ecat_slave_esi* esi)
{
    if (!esi) {
        return;
    }
    ecat_free_esi_vendor_info(esi->vendor);
    ecat_free_esi_description_info(esi->descriptions);
    ecat_free(esi);
    esi = NULL;
}

static void test_descriptions(esi_descriptions_info* desc)
{
    printf("Descriptions:\n");
    if (desc) {
        if (desc->groups) {
            printf("|%15s|%12s\n","group","pass");
        } else {
            printf("|%15s|%12s\n","group","N/A");
        }
        if (desc->devices) {
            printf("|%15s|%12s\n","devices","pass");
        } else {
            printf("|%15s|%12s\n","devices","N/A");
        }
    } else {
        printf("|%15s|%12s\n","descriptions","N/A");
    }
}

static void test_vendor(esi_VendorType* vendor)
{
    printf("Vendor:\n");
    if (vendor) {
        printf("|%15s|%12s\n","vendor","pass");
    } else {
        printf("|%15s|%12s\n","vendor","N/A");
    }
}

void test_esiconfig(char* name)
{
    ecat_slave_esi* esi;
    esi = ecat_load_slave_profile(name);
    if (esi) {
        test_vendor(esi->vendor);
        test_descriptions(esi->descriptions);
        ecat_free_esi_profile(esi);
        MOTION_CONSOLE_ERR("*****$$$ ESI/XML TEST PASS $$$*****\n");
    } else {
        MOTION_CONSOLE_ERR("*****$$$ ESI/XML TEST FAIL $$$*****\n");
    }
}
