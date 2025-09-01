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
 * @file enimaster.c
 * 
 */

#include "enimaster.h"

#define ENI_MASTER_LOG "ENI_MASTER"

/**
*@brief the function is used to parse eni file, copying name, destination, source and ethertype to struct
*@param ptr is used to point at certain row of ENI file for parsing
*@param info is pointing at ENI master info object to collect parsing results
*/

static void ecat_eni_parse_masterinfo(xmlNodePtr ptr, eni_master_info* info)
{
    if (!info) {
        return;
    }
    while (ptr != NULL) {
        if ((!xmlStrcmp(ptr->name, BAD_CAST"Name"))) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                char len = strlen((const char*)key);
                if (info->name) {
                    ecat_free(info->name);
                }
                info->name = ecat_malloc(len+1);
                if (info->name) {
                    memset(info->name, 0, len+1);
                    memcpy(info->name, (const char*)key, len);
                }
                xmlFree(key);
            }
        }

        if ((!xmlStrcmp(ptr->name, BAD_CAST"Destination"))) {

        }

        if ((!xmlStrcmp(ptr->name, BAD_CAST"Source"))) {
            
        }

        if ((!xmlStrcmp(ptr->name, BAD_CAST"EtherType"))) {
            
        }
        
        ptr = ptr->next;
    }
}

static void ecat_eni_parse_mastermailboxstates(xmlNodePtr ptr, eni_master_mailboxstates* states)
{
    if (!states) {
        return;
    }
    while (ptr != NULL) {
        if ((!xmlStrcmp(ptr->name, BAD_CAST"StartAddr"))) {
            
        }

        if ((!xmlStrcmp(ptr->name, BAD_CAST"Count"))) {
            
        }
        
        ptr = ptr->next;
    }
}

static void ecat_eni_parse_mastereoe(xmlNodePtr ptr, eni_master_eoe* eoe)
{
    if (!eoe) {
        return;
    }
    while (ptr != NULL) {
        if ((!xmlStrcmp(ptr->name, BAD_CAST"MaxPorts"))) {
            
        }

        if ((!xmlStrcmp(ptr->name, BAD_CAST"MaxFrames"))) {
            
        }

        if ((!xmlStrcmp(ptr->name, BAD_CAST"MaxMACs"))) {
            
        }
        
        ptr = ptr->next;
    }
}

static void ecat_eni_parse_masterinitcmds(xmlNodePtr ptr, eni_master_initcmds* initcmds)
{
    if (!initcmds) {
        return;
    }
    INIT_LIST_HEAD(&initcmds->initcmds_list);
    while (ptr != NULL) {
        if ((!xmlStrcmp(ptr->name, BAD_CAST"InitCmd"))) {
            xmlNodePtr nodePtr = ptr->xmlChildrenNode;
            ecat_eni_parse_initcmd(nodePtr, &initcmds->initcmds_list);
        }
        ptr = ptr->next;
    }
}

void ecat_eni_parse_masterconfig(xmlNodePtr ptr, eni_config_master* master)
{
    if (!master) {
        return;
    }
    while (ptr != NULL) {
        if ((!xmlStrcmp(ptr->name, BAD_CAST"Info"))) {
            xmlNodePtr nodePtr = ptr->xmlChildrenNode;
            ecat_eni_parse_masterinfo(nodePtr, &master->info);
        }

        if ((!xmlStrcmp(ptr->name, BAD_CAST"MailboxStates"))) {
            xmlNodePtr nodePtr = ptr->xmlChildrenNode;
            if (!master->states) {
                master->states = (eni_master_mailboxstates*)ecat_malloc(sizeof(eni_master_mailboxstates));
            }
            if (master->states) {
                memset(master->states, 0, sizeof(eni_master_mailboxstates));
                ecat_eni_parse_mastermailboxstates(nodePtr, master->states);
            }
        }

        if ((!xmlStrcmp(ptr->name, BAD_CAST"EoE"))) {
            xmlNodePtr nodePtr = ptr->xmlChildrenNode;
            if (!master->eoe) {
                master->eoe = (eni_master_eoe*)ecat_malloc(sizeof(eni_master_eoe));
            }
            if (master->eoe) {
                memset(master->eoe, 0, sizeof(eni_master_eoe));
                ecat_eni_parse_mastereoe(nodePtr, master->eoe);
            }
        }
        
        if ((!xmlStrcmp(ptr->name, BAD_CAST"InitCmds"))) {
            xmlNodePtr nodePtr = ptr->xmlChildrenNode;
            if (!master->initcmds) {
                master->initcmds = (eni_master_initcmds*)ecat_malloc(sizeof(eni_master_initcmds));
            }
            if (master->initcmds) {
                memset(master->initcmds, 0, sizeof(eni_master_initcmds));
                ecat_eni_parse_masterinitcmds(nodePtr, master->initcmds);
            }
        }
        
        ptr = ptr->next;
    }
    
}

static void ecat_eni_free_master_info(eni_master_info* info)
{
    if (!info) {
        return;
    }
    if (info->name) {
        ecat_free(info->name);
        info->name = NULL;
    }
    if (info->type) {
        ecat_free(info->type);
        info->type = NULL;
    }
}

static void ecat_eni_free_master_initcmds(eni_master_initcmds* initcmds)
{
    if (!initcmds) {
        return;
    }

    eni_initcmd* initcmd = NULL;
    eni_initcmd* next = NULL;
    list_for_each_entry_safe(initcmd, next, &initcmds->initcmds_list, initcmd_list) {
        if (initcmd) {
            list_del(&initcmd->initcmd_list);
            ecat_free(initcmd);
            initcmd = NULL;
        }
    }
    INIT_LIST_HEAD(&initcmds->initcmds_list);
    ecat_free(initcmds);
    initcmds = NULL;
}

static void ecat_eni_free_mailbox_states(eni_master_mailboxstates* states)
{
    if (!states) {
        return;
    }
    ecat_free(states);
    states = NULL;
}

static void ecat_eni_free_master_eoe(eni_master_eoe* eoe)
{
    if (!eoe) {
        return;
    }
    ecat_free(eoe);
    eoe = NULL;
}

void ecat_eni_free_masterconfig(eni_config_master* master)
{
    if (!master) {
        return;
    }
    ecat_eni_free_master_info(&master->info);
    ecat_eni_free_mailbox_states(master->states);
    ecat_eni_free_master_initcmds(master->initcmds);
    ecat_eni_free_master_eoe(master->eoe);
}
