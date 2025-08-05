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
 * @file esidevicedc.c
 * 
 */

#include "esidevicedc.h"

static void ecat_esi_parse_device_DC_OpMode(xmlNodePtr ptr, struct list_head* list)
{
    esi_DeviceDcOpmode* opmode;
    if (!list) {
        return;
    }
    opmode = (esi_DeviceDcOpmode*)ecat_malloc(sizeof(esi_DeviceDcOpmode));
    if (!opmode) {
        return;
    }
    memset(opmode, 0, sizeof(esi_DeviceDcOpmode));
    INIT_LIST_HEAD(&opmode->opmode_list);
    while (ptr != NULL) {
        if ((!xmlStrcmp(ptr->name, BAD_CAST"Name"))) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                char len = strlen((const char*)key);
                if (opmode->name) {
                    ecat_free(opmode->name);
                }
                opmode->name = ecat_malloc(len+1);
                if (opmode->name) {
                    memset(opmode->name, 0, len+1);
                    memcpy(opmode->name, (const char*)key, len);
                }
                xmlFree(key);
            }
        }
        if ((!xmlStrcmp(ptr->name, BAD_CAST"Desc"))) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                char len = strlen((const char*)key);
                if (opmode->desc) {
                    ecat_free(opmode->desc);
                    opmode->desc = NULL;
                }
                opmode->desc = ecat_malloc(len+1);
                if (opmode->desc) {
                    memset(opmode->desc, 0, len+1);
                    memcpy(opmode->desc, (const char*)key, len);
                }
                xmlFree(key);
            }
        }
        if ((!xmlStrcmp(ptr->name, BAD_CAST"AssignActivate"))) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                ecat_sscanf(key, &opmode->assignactivate);
                xmlFree(key);
            }
        }
        if ((!xmlStrcmp(ptr->name, BAD_CAST"CycleTimeSync0"))) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                if (opmode->cycletimesync0) {
                    ecat_free(opmode->cycletimesync0);
                    opmode->cycletimesync0 = NULL;
                }
                opmode->cycletimesync0 = ecat_malloc(sizeof(uint32_t));
                if (opmode->cycletimesync0) {
                    *opmode->cycletimesync0 = atoi((const char*)key);
                }
                xmlFree(key);
            }
        }
        if ((!xmlStrcmp(ptr->name, BAD_CAST"ShiftTimeSync0"))) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                if (opmode->shifttimesync0) {
                    ecat_free(opmode->shifttimesync0);
                    opmode->shifttimesync0 = NULL;
                }
                opmode->shifttimesync0 = ecat_malloc(sizeof(uint32_t));
                if (opmode->shifttimesync0) {
                    *opmode->shifttimesync0 = atoi((const char*)key);
                }
                xmlFree(key);
            }
        }
        if ((!xmlStrcmp(ptr->name, BAD_CAST"CycleTimeSync1"))) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                if (opmode->cycletimesync1) {
                    ecat_free(opmode->cycletimesync1);
                    opmode->cycletimesync1 = NULL;
                }
                opmode->cycletimesync1 = ecat_malloc(sizeof(uint32_t));
                if (opmode->cycletimesync1) {
                    *opmode->cycletimesync1 = atoi((const char*)key);
                }
                xmlFree(key);
            }
        }
        if ((!xmlStrcmp(ptr->name, BAD_CAST"ShiftTimeSync1"))) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                if (opmode->shifttimesync1) {
                    ecat_free(opmode->shifttimesync0);
                    opmode->shifttimesync0 = NULL;
                }
                opmode->shifttimesync1 = ecat_malloc(sizeof(uint32_t));
                if (opmode->shifttimesync1) {
                    *opmode->shifttimesync1 = atoi((const char*)key);
                }
                xmlFree(key);
            }
        }
        ptr = ptr->next;
    }
    list_add_tail(&opmode->opmode_list, list);
}

void ecat_esi_parse_device_DC(xmlNodePtr ptr, esi_DeviceDc* dc)
{
    if (!dc) {
        return;
    }
    
    while (ptr != NULL) {
        if ((!xmlStrcmp(ptr->name, BAD_CAST"OpMode"))) {
            ecat_esi_parse_device_DC_OpMode(ptr, &dc->opmodes_list);
        }
        ptr = ptr->next;
    }
}

void ecat_free_esi_device_dc_opmode(esi_DeviceDc* dc)
{
    if (!dc) {
        return;
    }
    esi_DeviceDcOpmode* opmode;
    esi_DeviceDcOpmode* next;
    list_for_each_entry_safe(opmode, next, &dc->opmodes_list, opmode_list) {
        if (opmode) {
            list_del(&opmode->opmode_list);
            if (opmode->name) {
                ecat_free(opmode->name);
                opmode->name = NULL;
            }
            if (opmode->desc) {
                ecat_free(opmode->desc);
                opmode->desc = NULL;
            }
            if (opmode->cycletimesync0) {
                ecat_free(opmode->cycletimesync0);
                opmode->cycletimesync0 = NULL;
            }
            if (opmode->shifttimesync0) {
                ecat_free(opmode->shifttimesync0);
                opmode->shifttimesync0 = NULL;
            }
            if (opmode->cycletimesync1) {
                ecat_free(opmode->cycletimesync1);
                opmode->cycletimesync1 = NULL;
            }
            if (opmode->shifttimesync1) {
                ecat_free(opmode->shifttimesync1);
                opmode->shifttimesync1 = NULL;
            }
            ecat_free(opmode);
            opmode = NULL;
        }
    }
}
