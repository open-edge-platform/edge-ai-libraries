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
 * @file enislaveprocessdata.c
 * 
 */

#include "enislaveprocessdata.h"

#define ENI_SLAVE_PROCESSDATA_LOG "ENI_SLAVE_PROCESSDATA"

/**
*@brief This function is responsible for parsing EtherCAT ENI slave processdata send list
*@param ptr is used to point at certain row of ENI file for parsing
*@param list is pointing at ENI slave process data object send list to collect parsing results
*/

static void ecat_eni_parse_slaveprocessdata_send(xmlNodePtr ptr, struct list_head* list)
{
    if (!list) {
        return;
    }

    eni_slave_processdata_send* send;
    send = (eni_slave_processdata_send*)ecat_malloc(sizeof(eni_slave_processdata_send));
    if (!send) {
        return;
    }
    memset(send, 0, sizeof(eni_slave_processdata_send));
    INIT_LIST_HEAD(&send->list);
    while (ptr != NULL) {
        if ((!xmlStrcmp(ptr->name, BAD_CAST"BitStart"))) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                // FIXME add some error and validty checking. if node is set correctly and has the type
                send->bit_start = atoi((const char*)key);
                xmlFree(key);
            }
        }

        if ((!xmlStrcmp(ptr->name, BAD_CAST"BitLength"))) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                // FIXME add some error and validty checking. if node is set correctly and has the type
                send->bit_len = atoi((const char*)key);
                xmlFree(key);
            }
        }
        ptr = ptr->next;
    }
    list_add_tail(&send->list, list);
}

/**
*@brief This function is responsible for parsing EtherCAT ENI slave processdata receive list
*@param ptr is used to point at certain row of ENI file for parsing
*@param list is pointing at ENI slave process data object receive list to collect parsing results
*/

static void ecat_eni_parse_slaveprocessdata_recv(xmlNodePtr ptr, struct list_head* list)
{
    if (!list) {
        return;
    }

    eni_slave_processdata_recv* recv;
    recv = (eni_slave_processdata_recv*)ecat_malloc(sizeof(eni_slave_processdata_recv));
    if (!recv) {
        return;
    }
    memset(recv, 0, sizeof(eni_slave_processdata_recv));
    INIT_LIST_HEAD(&recv->list);
    while (ptr != NULL) {
        if ((!xmlStrcmp(ptr->name, BAD_CAST"BitStart"))) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                // FIXME add some error and validty checking. if node is set correctly and has the type
                recv->bit_start = atoi((const char*)key);
                xmlFree(key);
            }
        }

        if ((!xmlStrcmp(ptr->name, BAD_CAST"BitLength"))) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                // FIXME add some error and validty checking. if node is set correctly and has the type
                recv->bit_len = atoi((const char*)key);
                xmlFree(key);
            }
        }
        ptr = ptr->next;
    }
    list_add_tail(&recv->list, list);
}

uint8_t ecat_eni_slave_smlist_size(struct list_head* list)
{

    if (!list) {
        return 0;
    }

    if (list_empty(list)) {
        return 0;
    }
    uint8_t size = 0;
    eni_slave_processdata_sm* sm = NULL;
    list_for_each_entry(sm, list, list) {
        if (sm) {
            size++;
        }
    }
    return size;
}

uint32_t ecat_eni_slave_sm_pdolist_size(struct list_head* list)
{
    if (!list) {
        return 0;
    }

    if (list_empty(list)) {
        return 0;
    }
    uint32_t size = 0;
    eni_slave_pdo_indices* pdo = NULL;
    list_for_each_entry(pdo, list, list) {
        if (pdo) {
            size++;
        }
    }
    return size;
}

uint32_t ecat_eni_slave_entry_size(struct list_head* list)
{
    if (!list) {
        return 0;
    }

    if (list_empty(list)) {
        return 0;
    }
    uint32_t size = 0;
    eni_entry_type* entry = NULL;
    list_for_each_entry(entry, list, list) {
        if (entry) {
            size++;
        }
    }
    return size;
}

/**
*@brief This function is responsible for parsing EtherCAT ENI slave processdata sync manager
*@param ptr is used to point at certain row of ENI file for parsing
*@param list is pointing at ENI slave process data sync manager list object to collect parsing results
*/

static void ecat_eni_parse_slaveprocessdata_sm(xmlNodePtr ptr, struct list_head* list)
{
    uint8_t index;
    int8_t loop;
    uint8_t sm_size;
    if ((!list)||(!ptr)) {
        return;
    }
    if(sscanf((const char *)ptr->name, "Sm%d", &index) == EOF) {
        return;
    }
    sm_size = ecat_eni_slave_smlist_size(list);
    if (index > sm_size) {
        for (loop = sm_size; loop < index; loop++) {
            // add invaild sm into list
            eni_slave_processdata_sm* sm_null = (eni_slave_processdata_sm*)ecat_malloc(sizeof(eni_slave_processdata_sm));
            if (!sm_null) {
                return;
            }
            memset(sm_null, 0, sizeof(eni_slave_processdata_sm));
            INIT_LIST_HEAD(&sm_null->list);
            INIT_LIST_HEAD(&sm_null->pdo_list);
            list_add_tail(&sm_null->list, list);
        }
    }
    eni_slave_processdata_sm* sm = (eni_slave_processdata_sm*)ecat_malloc(sizeof(eni_slave_processdata_sm));
    if (!sm) {
        return;
    }
    memset(sm, 0, sizeof(eni_slave_processdata_sm));
    INIT_LIST_HEAD(&sm->list);
    INIT_LIST_HEAD(&sm->pdo_list);
    xmlNodePtr nodePtr = ptr->xmlChildrenNode;
    while (nodePtr != NULL) {
        if ((!xmlStrcmp(nodePtr->name, BAD_CAST"Type"))) {
            xmlChar* s = xmlNodeGetContent(nodePtr);
            if (s) {
                if (strcmp((const char*)s, "Outputs")==0) {
                    sm->type = ENI_SM_OUTPUTS_TYPE;
                } else if (strcmp((const char*)s, "Inputs")==0) {
                    sm->type = ENI_SM_INPUTS_TYPE;
                } else {
                    sm->type = ENI_SM_INVAILD_TYPE;
                }
                xmlFree(s);
            }
        }
        if ((!xmlStrcmp(nodePtr->name, BAD_CAST"StartAddress"))) {
            xmlChar* key;
            key = xmlNodeGetContent(nodePtr);
            if (key) {
                // FIXME add some error and validty checking. if node is set correctly and has the type
                sm->startAddress = atoi((const char*)key);
                xmlFree(key);
            }
        }
        if ((!xmlStrcmp(nodePtr->name, BAD_CAST"ControlByte"))) {
            xmlChar* key;
            key = xmlNodeGetContent(nodePtr);
            if (key) {
                // FIXME add some error and validty checking. if node is set correctly and has the type
                sm->controlByte = atoi((const char*)key);
                xmlFree(key);
            }
        }
        if ((!xmlStrcmp(nodePtr->name, BAD_CAST"Enable"))) {
            xmlChar* key;
            key = xmlNodeGetContent(nodePtr);
            if (key) {
                // FIXME add some error and validty checking. if node is set correctly and has the type
                sm->enable = atoi((const char*)key);
                xmlFree(key);
            }
        }
        /* this variable is not used anymore referring to ETG2100*/
        if ((!xmlStrcmp(nodePtr->name, BAD_CAST"Watchdog"))) {
            xmlChar* key;
            key = xmlNodeGetContent(nodePtr);
            if (key) {
                int32_t* watchdog = (int32_t*)ecat_malloc(sizeof(int32_t));
                if (watchdog) {
                    *watchdog = atoi((const char*)key);
		    if (!sm->watchdog)
                        sm->watchdog = watchdog;
		    else
			ecat_free(watchdog);
                }
                xmlFree(key);
            }
        }
        if ((!xmlStrcmp(nodePtr->name, BAD_CAST"Pdo"))) {
            xmlChar* key;
            key = xmlNodeGetContent(nodePtr);
            if (key) {
                eni_slave_pdo_indices* pdo = (eni_slave_pdo_indices*)ecat_malloc(sizeof(eni_slave_pdo_indices));
                if (pdo) {
                    memset(pdo, 0, sizeof(eni_slave_pdo_indices));
                    INIT_LIST_HEAD(&pdo->list);
                    pdo->index = atoi((const char*)key);
                    list_add_tail(&pdo->list, &sm->pdo_list);
                }
                xmlFree(key);
            }
        }
        nodePtr = nodePtr->next;
    }
    list_add_tail(&sm->list, list);
}

static void ecat_eni_parse_pdo_entry(xmlNodePtr ptr, struct list_head* list)
{
    if (!list) {
        return;
    }

    eni_entry_type* entry;
    entry = (eni_entry_type*)ecat_malloc(sizeof(eni_entry_type));
    if (!entry) {
        return;
    }
    memset(entry, 0, sizeof(eni_entry_type));
    INIT_LIST_HEAD(&entry->list);
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
                entry->subindex = atoi((const char*)key);
                xmlFree(key);
            }
        }
        if ((!xmlStrcmp(ptr->name, BAD_CAST"BitLen"))) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                entry->bitlen = atoi((const char*)key);
                xmlFree(key);
            }
        }
        if ((!xmlStrcmp(ptr->name, BAD_CAST"Name"))) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                char len = strlen((const char*)key);
                if (entry->name.name) {
                    ecat_free(entry->name.name);
                }
                entry->name.name = ecat_malloc(len+1);
                if (entry->name.name) {
                    memset(entry->name.name, 0, len+1);
                    memcpy(entry->name.name, (const char*)key, len);
                }
                xmlFree(key);
            }
        }
        ptr = ptr->next;
    }
    list_add_tail(&entry->list, list);
}

static void ecat_eni_parse_device_pdo(xmlNodePtr ptr, struct list_head* list)
{
    if (!list) {
        return;
    }
    eni_slave_processdata_pdo* pdo;
    xmlNodePtr nodePtr = NULL;
    pdo = (eni_slave_processdata_pdo*)ecat_malloc(sizeof(eni_slave_processdata_pdo));
    if (!pdo) {
        return;
    }
    memset(pdo, 0, sizeof(eni_slave_processdata_pdo));
    pdo->pdo_type.sm = 0xFF;
    INIT_LIST_HEAD(&pdo->list);
    INIT_LIST_HEAD(&pdo->pdo_type.entry_list);
    if (ptr != NULL) {
        xmlChar* id;
        id = xmlGetProp(ptr, BAD_CAST"Fixed");
        if (id) {
            pdo->pdo_type.fixed = atoi((const char*)id);
            xmlFree(id);
        }
        id = xmlGetProp(ptr, BAD_CAST"Mandatory");
        if (id) {
            pdo->pdo_type.mandatory = atoi((const char*)id);
            xmlFree(id);
        }
        id = xmlGetProp(ptr, BAD_CAST"Sm");
        if (id) {
            pdo->pdo_type.sm = atoi((const char*)id);
            xmlFree(id);
        }
        nodePtr = ptr->xmlChildrenNode;
    }
    
    while (nodePtr != NULL) {
        if ((!xmlStrcmp(nodePtr->name, BAD_CAST"Index"))) {
            xmlChar* key;
            key = xmlNodeGetContent(nodePtr);
            if (key) {
                ecat_sscanf(key, &(pdo->pdo_type.index));
                xmlFree(key);
            }
        }
        if ((!xmlStrcmp(nodePtr->name, BAD_CAST"Name"))) {
            xmlChar* key;
            key = xmlNodeGetContent(nodePtr);
            if (key) {
                eni_name_type* eni_name;
                char len = strlen((const char*)key);
                eni_name = &pdo->pdo_type.name;
                if (eni_name->name) {
                    ecat_free(eni_name->name);
                    eni_name->name = NULL;
                }
                eni_name->name = ecat_malloc(len+1);
                if (eni_name->name) {
                    memset(eni_name->name, 0, len+1);
                    memcpy(eni_name->name, (const char*)key, len);
                }
                xmlFree(key);
            }
        }
        if ((!xmlStrcmp(nodePtr->name, BAD_CAST"Entry"))) {
            xmlNodePtr entry_ptr = nodePtr->xmlChildrenNode;
            ecat_eni_parse_pdo_entry(entry_ptr, &pdo->pdo_type.entry_list);
        }
        nodePtr = nodePtr->next;
    }
    list_add_tail(&pdo->list, list);
}

eni_slave_processdata_pdo* ecat_get_pdo_info_by_index(eni_slave_processdata* processdata, uint8_t sm_id, uint32_t index)
{
    if (!processdata) {
        return NULL;
    }
    eni_slave_processdata_pdo* pdo = NULL;
    list_for_each_entry(pdo, &processdata->txpdo_list, list) {
        if ((pdo) && (pdo->pdo_type.sm == sm_id) && (pdo->pdo_type.index == index)) {
            return pdo;
        }
    }
    list_for_each_entry(pdo, &processdata->rxpdo_list, list) {
        if ((pdo) && (pdo->pdo_type.sm == sm_id) && (pdo->pdo_type.index == index)) {
            return pdo;
        }
    }
    return NULL;
}

/**
*@brief This function is responsible for parsing EtherCAT ENI slave processdata
*@param ptr is used to point at certain row of ENI file for parsing
*@param processdata is pointing at ENI slave process data object to collect parsing results
*/

void ecat_eni_parse_slaveprocessdata(xmlNodePtr ptr, eni_slave_processdata* processdata)
{
    if (!processdata) {
        return;
    }
    
    INIT_LIST_HEAD(&processdata->send_list);
    INIT_LIST_HEAD(&processdata->recv_list);
    INIT_LIST_HEAD(&processdata->sm_list);
    INIT_LIST_HEAD(&processdata->txpdo_list);
    INIT_LIST_HEAD(&processdata->rxpdo_list);
    while (ptr != NULL) {
        if ((!xmlStrcmp(ptr->name, BAD_CAST"Send"))) {
            xmlNodePtr nodePtr = ptr->xmlChildrenNode;
            ecat_eni_parse_slaveprocessdata_send(nodePtr, &processdata->send_list);
        }

        if ((!xmlStrcmp(ptr->name, BAD_CAST"Recv"))) {
            xmlNodePtr nodePtr = ptr->xmlChildrenNode;
            ecat_eni_parse_slaveprocessdata_recv(nodePtr, &processdata->recv_list);
        }

        if ((!xmlStrncmp(ptr->name, BAD_CAST"Sm", 2))) {
            ecat_eni_parse_slaveprocessdata_sm(ptr, &processdata->sm_list);
        }
        
        if ((!xmlStrcmp(ptr->name, BAD_CAST"TxPdo"))) {
            ecat_eni_parse_device_pdo(ptr, &processdata->txpdo_list);
        }

        if ((!xmlStrcmp(ptr->name, BAD_CAST"RxPdo"))) {
            ecat_eni_parse_device_pdo(ptr, &processdata->rxpdo_list);
        }
        ptr = ptr->next;
    }
}

static void ecat_eni_free_send_list(struct list_head* list)
{
    if (!list) {
        return;
    }

    eni_slave_processdata_send* send = NULL;
    eni_slave_processdata_send* next = NULL;
    list_for_each_entry_safe(send, next, list, list) {
        if (send) {
            list_del(&send->list);
            ecat_free(send);
            send = NULL;
        }
    }
    INIT_LIST_HEAD(list);
}

static void ecat_eni_free_recv_list(struct list_head* list)
{
    if (!list) {
        return;
    }
    eni_slave_processdata_recv* recv = NULL;
    eni_slave_processdata_recv* next = NULL;
    list_for_each_entry_safe(recv, next, list, list) {
        if (recv) {
            list_del(&recv->list);
            ecat_free(recv);
            recv = NULL;
        }
    }
    INIT_LIST_HEAD(list);
}

static void ecat_eni_free_sm_list(struct list_head* list)
{
    if (!list) {
        return;
    }

    eni_slave_processdata_sm* sm = NULL;
    eni_slave_processdata_sm* next_sm = NULL;
    list_for_each_entry_safe(sm, next_sm, list, list) {
        if (sm) {
            if(sm->watchdog) {
                ecat_free(sm->watchdog);
                sm->watchdog = NULL;
            }
            list_del(&sm->list);
            eni_slave_pdo_indices* pdo = NULL;
            eni_slave_pdo_indices* next_pdo = NULL;
            list_for_each_entry_safe(pdo, next_pdo, &sm->pdo_list, list) {
                if (pdo) {
                    list_del(&pdo->list);
                    ecat_free(pdo);
                    pdo = NULL;
                }
            }
            INIT_LIST_HEAD(&sm->pdo_list);
            ecat_free(sm);
            sm = NULL;
        }
    }
    INIT_LIST_HEAD(list);
}

static void ecat_eni_free_txpdo_list(struct list_head* list)
{
    if (!list) {
        return;
    }
    eni_slave_processdata_pdo* pdo = NULL;
    eni_slave_processdata_pdo* next = NULL;
    list_for_each_entry_safe(pdo, next, list, list) {
        if (pdo) {
            eni_name_type* type;
            list_del(&pdo->list);
            eni_entry_type* entry = NULL;
            eni_entry_type* nextentry = NULL;
            list_for_each_entry_safe(entry, nextentry, &pdo->pdo_type.entry_list, list) {
                if (entry) {
                    list_del(&entry->list);
                    type = &entry->name;
                    if (type->name) {
                        ecat_free(type->name);
                        type->name = NULL;
                    }
                    ecat_free(entry);
                    entry = NULL;
                }
            }
            INIT_LIST_HEAD(&pdo->pdo_type.entry_list);
            type = &pdo->pdo_type.name;
            if (type->name) {
                ecat_free(type->name);
                type->name = NULL;
            }
            ecat_free(pdo);
            pdo = NULL;
        }
    }
    INIT_LIST_HEAD(list);
}

static void ecat_eni_free_rxpdo_list(struct list_head* list)
{
    if (!list) {
        return;
    }
    eni_slave_processdata_pdo* pdo = NULL;
    eni_slave_processdata_pdo* next = NULL;
    list_for_each_entry_safe(pdo, next, list, list) {
        if (pdo) {
            eni_name_type* type;
            list_del(&pdo->list);
            eni_entry_type* entry = NULL;
            eni_entry_type* nextentry = NULL;
            list_for_each_entry_safe(entry, nextentry, &pdo->pdo_type.entry_list, list) {
                if (entry) {
                    list_del(&entry->list);
                    type = &entry->name;
                    if (type->name) {
                        ecat_free(type->name);
                        type->name = NULL;
                    }
                    ecat_free(entry);
                    entry = NULL;
                }
            }
            INIT_LIST_HEAD(&pdo->pdo_type.entry_list);
            type = &pdo->pdo_type.name;
            if (type->name) {
                ecat_free(type->name);
                type->name = NULL;
            }
            ecat_free(pdo);
            pdo = NULL;
        }
    }
    INIT_LIST_HEAD(list);
}

void ecat_eni_free_slave_processdata(eni_slave_processdata* processdata)
{
    if (!processdata) {
        return;
    }
    ecat_eni_free_send_list(&processdata->send_list);
    ecat_eni_free_recv_list(&processdata->recv_list);
    ecat_eni_free_sm_list(&processdata->sm_list);
    ecat_eni_free_txpdo_list(&processdata->txpdo_list);
    ecat_eni_free_rxpdo_list(&processdata->rxpdo_list);
    ecat_free(processdata);
    processdata = NULL;
}
