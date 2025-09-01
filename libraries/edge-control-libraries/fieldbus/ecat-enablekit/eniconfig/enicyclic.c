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
 * @file enicyclic.c
 * 
 */
#include "enicyclic.h"

#define ENI_CYCLIC_LOG "ENI_CYCLIC"

/**
*@brief the function is used to parse eni file, copying framecmd information
*@param ptr is used to point at certain row of ENI file for parsing
*@param framecmd is pointing at ENI config object to collect parsing results
*/

static void ecat_eni_parse_cyclic_framecmd(xmlNodePtr ptr, eni_cyclic_framecmd* framecmd) {
    if (!framecmd) {
        return;
    }
    while (ptr != NULL) {
        if ((!xmlStrcmp(ptr->name, BAD_CAST"State"))) {
            xmlChar* s = xmlNodeGetContent(ptr);
            if (strcmp((const char*)s, "INIT")==0) {
                framecmd->state |= ENI_INIT_MASTER_STATE;
            } else if (strcmp((const char*)s, "PREOP")==0) {
                framecmd->state |= ENI_PREOP_MASTER_STATE;
            } else if (strcmp((const char*)s, "SAFEOP")==0) {
                framecmd->state |= ENI_SAFEOP_MASTER_STATE;
            } else if (strcmp((const char*)s, "OP")==0) {
                framecmd->state |= ENI_OP_MASTER_STATE;
            }
            xmlFree(s);
        }
        if ((!xmlStrcmp(ptr->name, BAD_CAST"Cmd"))) {
            xmlChar* id;
            id = xmlNodeGetContent(ptr);
            if (id) {
                framecmd->cmd = (uint32_t)atoi((const char*)id);
                xmlFree(id);
            }
        }
        if ((!xmlStrcmp(ptr->name, BAD_CAST"Adp"))) {
            xmlChar* id;
            id = xmlNodeGetContent(ptr);
            if (id) {
                if (!framecmd->adp) {
                    framecmd->adp = (uint32_t*)ecat_malloc(sizeof(uint32_t));
                }
                if (framecmd->adp) {
                    *framecmd->adp = (uint32_t)atoi((const char*)id);
                }
                xmlFree(id);
            }
        }
        if ((!xmlStrcmp(ptr->name, BAD_CAST"Ado"))) {
            xmlChar* id;
            id = xmlNodeGetContent(ptr);
            if (id) {
                framecmd->ado = (uint32_t)atoi((const char*)id);
                xmlFree(id);
            }
        }
        if ((!xmlStrcmp(ptr->name, BAD_CAST"Addr"))) {
            xmlChar* id;
            id = xmlNodeGetContent(ptr);
            if (id) {
                framecmd->addr = (uint32_t)atoi((const char*)id);
                xmlFree(id);
            }
        }
        if ((!xmlStrcmp(ptr->name, BAD_CAST"Data"))) {
            // Fixed in future
        }
        if ((!xmlStrcmp(ptr->name, BAD_CAST"DataLength"))) {
            xmlChar* id;
            id = xmlNodeGetContent(ptr);
            if (id) {
                framecmd->dataLength = (uint32_t)atoi((const char*)id);
                xmlFree(id);
            }
        }
        if ((!xmlStrcmp(ptr->name, BAD_CAST"Cnt"))) {
            xmlChar* id;
            id = xmlNodeGetContent(ptr);
            if (id) {
                if (!framecmd->cnt) {
                    framecmd->cnt = (uint32_t*)ecat_malloc(sizeof(uint32_t));
                }
                if (framecmd->cnt) {
                    *framecmd->cnt = (uint32_t)atoi((const char*)id);
                }
                xmlFree(id);
            }
        }
        if ((!xmlStrcmp(ptr->name, BAD_CAST"InputOffs"))) {
            xmlChar* id;
            id = xmlNodeGetContent(ptr);
            if (id) {
                framecmd->inputOffs = (uint32_t)atoi((const char*)id);
                xmlFree(id);
            }
        }
        if ((!xmlStrcmp(ptr->name, BAD_CAST"OutputOffs"))) {
            xmlChar* id;
            id = xmlNodeGetContent(ptr);
            if (id) {
                framecmd->outputOffs = (uint32_t)atoi((const char*)id);
                xmlFree(id);
            }
        }
        ptr = ptr->next;
    }
}

/**
*@brief the function is used to parse eni file, copying frame information
*@param ptr is used to point at certain row of ENI file for parsing
*@param frame is pointing at ENI config object to collect parsing results
*/

static void ecat_eni_parse_cyclic_frame(xmlNodePtr ptr, eni_cyclic_frame* frame) {
    if(!frame) {
        return;
    }
    INIT_LIST_HEAD(&frame->cmds);
    while (ptr != NULL) {
        if ((!xmlStrcmp(ptr->name, BAD_CAST"Cmd"))) {
            xmlNodePtr nodePtr = ptr->xmlChildrenNode;
            eni_cyclic_framecmd* framecmd = (eni_cyclic_framecmd*)ecat_malloc(sizeof(eni_cyclic_framecmd));
            if (framecmd) {
                memset(framecmd, 0, sizeof(eni_cyclic_framecmd));
                INIT_LIST_HEAD(&framecmd->cmdlist);
                ecat_eni_parse_cyclic_framecmd(nodePtr, framecmd);
                list_add_tail(&framecmd->cmdlist,&frame->cmds);
            }
        }
        ptr = ptr->next;
    }
}

uint32_t ecat_eni_get_cyclic_cycletime(eni_config_cyclic* cyclic)
{
    if (!cyclic) {
        return 0;
    }
    return cyclic->cycletime;
}

/**
*@brief the function is used to parse eni file, copying cyclic information
*@param ptr is used to point at certain row of ENI file for parsing
*@param cyclic is pointing at ENI config object to collect parsing results
*/

void ecat_eni_parse_cyclic(xmlNodePtr ptr, eni_config_cyclic* cyclic)
{
    if (!cyclic) {
        return;
    }
    while (ptr != NULL) {
        if ((!xmlStrcmp(ptr->name, BAD_CAST"CycleTime"))) {
            xmlChar* id;
            id = xmlNodeGetContent(ptr);
            if (id) {
                cyclic->cycletime = (uint32_t)atoi((const char*)id);
                xmlFree(id);
            }
        }

        if ((!xmlStrcmp(ptr->name, BAD_CAST"Frame"))) {
            xmlNodePtr nodePtr = ptr->xmlChildrenNode;
            if (!cyclic->frame) {
                cyclic->frame = (eni_cyclic_frame*)ecat_malloc(sizeof(eni_cyclic_frame));
            }
            if (cyclic->frame) {
                memset(cyclic->frame, 0, sizeof(eni_cyclic_frame));
                ecat_eni_parse_cyclic_frame(nodePtr, cyclic->frame);
            }
        }

        ptr = ptr->next;
    }
}

static void ecat_eni_free_cyclic_frame(eni_cyclic_frame* frame)
{
    if (!frame) {
        return;
    }

    eni_cyclic_framecmd* cmd = NULL;
    eni_cyclic_framecmd* next = NULL;
    list_for_each_entry_safe(cmd, next, &frame->cmds, cmdlist) {
        if (cmd) {
            list_del(&cmd->cmdlist);
            if (cmd->adp) {
                ecat_free(cmd->adp);
                cmd->adp = NULL;
            }
            if (cmd->data) {
                ecat_free(cmd->data);
                cmd->data = NULL;
            }
            if (cmd->cnt) {
                ecat_free(cmd->cnt);
                cmd->cnt = NULL;
            }
            ecat_free(cmd);
            cmd = NULL;
        }
    }
    INIT_LIST_HEAD(&frame->cmds);
    ecat_free(frame);
    frame = NULL;
}

void ecat_eni_free_cyclic(eni_config_cyclic* cyclic)
{
    if (!cyclic) {
        return;
    }
    ecat_eni_free_cyclic_frame(cyclic->frame);
    ecat_free(cyclic);
    cyclic = NULL;
}
