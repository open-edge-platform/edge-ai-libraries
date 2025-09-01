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
 * @file esipdotype.c
 * 
 */

#include "esipdotype.h"

static void ecat_esi_parse_pdo_entry(xmlNodePtr ptr, struct list_head* list, esi_pdo_entry* entry)
{
    if (!entry) {
        return;
    }
    while (ptr != NULL) {
        if ((!xmlStrcmp(ptr->name, BAD_CAST"Index"))) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                ecat_sscanf(key, &(entry->index));
                xmlFree(key);
            }
        }
        if ((!xmlStrcmp(ptr->name, BAD_CAST"SubIndex"))) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                entry->subIndex = atoi((const char*)key);
                xmlFree(key);
            }
        }
        if ((!xmlStrcmp(ptr->name, BAD_CAST"BitLen"))) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                entry->bitLen = atoi((const char*)key);
                xmlFree(key);
            }
        }
        ptr = ptr->next;
    }
    list_add_tail(&entry->entry_list, list);
}

void ecat_esi_parse_device_pdo(xmlNodePtr ptr, struct list_head* list, uint8_t is_input)
{
    esi_pdo_info* pdo;
    xmlNodePtr nodePtr;
    if ((!list)||(!ptr)) {
        return;
    }
    pdo = (esi_pdo_info*)ecat_malloc(sizeof(esi_pdo_info));
    if (!pdo) {
        return;
    }
    memset(pdo, 0, sizeof(esi_pdo_info));
    INIT_LIST_HEAD(&pdo->pdo_list);
    INIT_LIST_HEAD(&pdo->entry_list);

    if (ptr != NULL) {
        xmlChar* id;
        id = xmlGetProp(ptr, BAD_CAST"Sm");
        if (id) {
            pdo->sm_id = atoi((const char*)id);
            xmlFree(id);
        }
    }
    if (is_input) {
        pdo->direction = EC_DIR_INPUT;
    } else {
        pdo->direction = EC_DIR_OUTPUT;
    }

    nodePtr = ptr->xmlChildrenNode;
    while (nodePtr != NULL) {
        if ((!xmlStrcmp(nodePtr->name, BAD_CAST"Index"))) {
            xmlChar* key;
            key = xmlNodeGetContent(nodePtr);
            if (key) {
                ecat_sscanf(key, &(pdo->index));
                xmlFree(key);
            }
        }
        if ((!xmlStrcmp(nodePtr->name, BAD_CAST"Entry"))) {
            esi_pdo_entry* entry;
            xmlNodePtr node = nodePtr->xmlChildrenNode;
            entry = (esi_pdo_entry*)ecat_malloc(sizeof(esi_pdo_entry));
            if (entry) {
                memset(entry, 0, sizeof(esi_pdo_entry));
                INIT_LIST_HEAD(&entry->entry_list);
                ecat_esi_parse_pdo_entry(node, &pdo->entry_list, entry);
                pdo->n_entries++;
            }
        }
        nodePtr = nodePtr->next;
    }
    list_add_tail(&pdo->pdo_list, list);
}

void ecat_free_esi_pdos_list(struct list_head* list)
{
    if (!list) {
        return;
    }
    esi_pdo_info* pdo = NULL;
    esi_pdo_info* next = NULL;
    list_for_each_entry_safe(pdo, next, list, pdo_list) {
        if (pdo) {
            list_del(&pdo->pdo_list);
            esi_pdo_entry* entry = NULL;
            esi_pdo_entry* next_entry = NULL;
            list_for_each_entry_safe(entry, next_entry, &pdo->entry_list, entry_list) {
                if (entry) {
                    list_del(&entry->entry_list);
                    ecat_free(entry);
                    entry = NULL;
                }
            }
            ecat_free(pdo);
            pdo = NULL;
        }
    }
}
