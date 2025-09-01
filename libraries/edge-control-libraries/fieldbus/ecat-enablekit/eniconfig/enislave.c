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
 * @file enislave.c
 * 
 */

#include "enislave.h"

#define ENI_SLAVE_LOG "ENI_SLAVE"

void ecat_eni_parse_slaveconfig(xmlNodePtr ptr, struct list_head* list)
{
    if (!list) {
        return;
    }
    eni_config_slave* slave = (eni_config_slave*)ecat_malloc(sizeof(eni_config_slave));
    if (!slave) {
        return;
    }
    memset(slave, 0, sizeof(eni_config_slave));
    INIT_LIST_HEAD(&slave->list);
    while (ptr != NULL) {
        if ((!xmlStrcmp(ptr->name, BAD_CAST"Info"))) {
            xmlNodePtr nodePtr = ptr->xmlChildrenNode;
            ecat_eni_parse_slaveinfo(nodePtr, &slave->info);
        }

        if ((!xmlStrcmp(ptr->name, BAD_CAST"ProcessData"))) {
            xmlNodePtr nodePtr = ptr->xmlChildrenNode;
            if (!slave->processdata) {
                slave->processdata = (eni_slave_processdata*)ecat_malloc(sizeof(eni_slave_processdata));
            }
            if (slave->processdata) {
                memset(slave->processdata, 0, sizeof(eni_slave_processdata));
                ecat_eni_parse_slaveprocessdata(nodePtr, slave->processdata);
            }
        }

        if ((!xmlStrcmp(ptr->name, BAD_CAST"Mailbox"))) {
            xmlNodePtr nodePtr = ptr->xmlChildrenNode;
            if (!slave->mailbox) {
                slave->mailbox = (eni_slave_mailbox*)ecat_malloc(sizeof(eni_slave_mailbox));
            }
            if (slave->mailbox) {
                memset(slave->mailbox, 0, sizeof(eni_slave_mailbox));
                ecat_eni_parse_slavemailbox(nodePtr, slave->mailbox);
            }
        }
        
        if ((!xmlStrcmp(ptr->name, BAD_CAST"InitCmds"))) {
            xmlNodePtr nodePtr = ptr->xmlChildrenNode;
            if (!slave->initcmds) {
                slave->initcmds = (eni_slave_initcmds*)ecat_malloc(sizeof(eni_slave_initcmds));
            }
            if (slave->initcmds) {
                memset(slave->initcmds, 0, sizeof(eni_slave_initcmds));
                ecat_eni_parse_slaveinitcmds(nodePtr, slave->initcmds);
            }
        }

        if ((!xmlStrcmp(ptr->name, BAD_CAST"DC"))) {
            xmlNodePtr nodePtr = ptr->xmlChildrenNode;
            if (!slave->dc) {
                slave->dc = (eni_slave_dc*)ecat_malloc(sizeof(eni_slave_dc));
            }
            if (slave->dc) {
                memset(slave->dc, 0, sizeof(eni_slave_dc));
                ecat_eni_parse_slavedc(nodePtr, slave->dc);
            }
        }
        
        ptr = ptr->next;
    }
    list_add_tail(&slave->list, list);
}

void ecat_eni_free_slave(struct list_head* list)
{
    if (!list) {
        return;
    }
    
    eni_config_slave* slave = NULL;
    eni_config_slave* next = NULL;
    list_for_each_entry_safe(slave, next, list, list) {
        if (slave) {
            list_del(&slave->list);
            ecat_eni_free_slave_info(&slave->info);
            ecat_eni_free_slave_processdata(slave->processdata);
            ecat_eni_free_slave_mailbox(slave->mailbox);
            ecat_eni_free_slave_initcmds(slave->initcmds);
            ecat_eni_free_slave_dc(slave->dc);
            ecat_free(slave);
            slave = NULL;
        }
    }
    INIT_LIST_HEAD(list);
}
