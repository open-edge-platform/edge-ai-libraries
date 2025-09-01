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
 * @file esivendor.c
 * 
 */

#include "esivendor.h"
#include "../include/debug.h"

#include <libxml/parser.h>
#include <libxml/tree.h>
#include <libxml/xmlmemory.h>

#include <ecrt.h>

#define ESI_VENDOR_LOG "ESI_VENDOR: "

void ecat_esi_parse_vendor(xmlNodePtr ptr, esi_VendorType* vendor)
{
    if (!vendor) {
        return;
    }
    while (ptr != NULL) {
        if ((!xmlStrcmp(ptr->name, BAD_CAST"Id"))) {
            xmlChar* id;
            id = xmlNodeGetContent(ptr);
            if (id) {
                vendor->id = atoi((const char*)id);
                xmlFree(id);
            }
        }
        if ((!xmlStrcmp(ptr->name, BAD_CAST"Name"))) {

        }
        ptr = ptr->next;
    }
}

void ecat_free_esi_vendor_info(esi_VendorType* vendor)
{
    if (!vendor) {
        return;
    }
    if (vendor->name) {
        ecat_free(vendor->name);
        vendor->name = NULL;
    }
    ecat_free(vendor);
    vendor = NULL;
}

