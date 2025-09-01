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
 * @file enislavedc.c
 * 
 */

#include "enislavedc.h"

#define ENI_SLAVE_DC_LOG "ENI_SLAVE_DC"

/**
*@brief This function is responsible for parsing EtherCAT ENI slave dc
*@param ptr is used to point at certain row of ENI file for parsing
*@param dc is pointing at ENI slave dc object to collect parsing results
*/

void ecat_eni_parse_slavedc(xmlNodePtr ptr, eni_slave_dc* dc)
{
    if (!dc) {
        return;
    }
    while (ptr != NULL) {
        if (!xmlStrcmp(ptr->name, BAD_CAST"PotentialReferenceClock")) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                dc->potentialReferenceClock = atoi((const char*)key);
                xmlFree(key);
            }
        }
        if (!xmlStrcmp(ptr->name, BAD_CAST"ReferenceClock")) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                dc->referenceClock = atoi((const char*)key);
                xmlFree(key);
            }
        }
        if ((!xmlStrcmp(ptr->name, BAD_CAST"CycleTime0"))) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                if (!dc->cycleTime0) {
                    dc->cycleTime0 = (uint32_t*)ecat_malloc(sizeof(uint32_t));
                }
                if (dc->cycleTime0) {
                    *dc->cycleTime0 = atoi((const char*)key);
                }
                xmlFree(key);
            }
        }
        if ((!xmlStrcmp(ptr->name, BAD_CAST"CycleTime1"))) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                if (!dc->cycleTime1) {
                    dc->cycleTime1 = (uint32_t*)ecat_malloc(sizeof(uint32_t));
                }
                if (dc->cycleTime1) {
                    *dc->cycleTime1 = atoi((const char*)key);
                }
                xmlFree(key);
            }
        }
        if ((!xmlStrcmp(ptr->name, BAD_CAST"ShiftTime"))) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                if (!dc->shiftTime) {
                    dc->shiftTime = (uint32_t*)ecat_malloc(sizeof(uint32_t));
                }
                if (dc->shiftTime) {
                    *dc->shiftTime = atoi((const char*)key);
                }
                xmlFree(key);
            }
        }
        ptr = ptr->next;
    }
}

void ecat_eni_free_slave_dc(eni_slave_dc* dc)
{
    if (!dc) {
        return;
    }
    if (dc->cycleTime0) {
        ecat_free(dc->cycleTime0);
        dc->cycleTime0 = NULL;
    }
    if (dc->cycleTime1) {
        ecat_free(dc->cycleTime1);
        dc->cycleTime1 = NULL;
    }
    if (dc->shiftTime) {
        ecat_free(dc->shiftTime);
        dc->shiftTime = NULL;
    }
    ecat_free(dc);
    dc = NULL;
}
