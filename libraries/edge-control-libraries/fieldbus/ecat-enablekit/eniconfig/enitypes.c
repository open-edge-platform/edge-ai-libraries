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
 * @file enitypes.c
 * 
 */

#include "enitypes.h"

#define ENI_TYPES_LOG "ENI_TYPES"



void ecat_eni_parse_ecatcmdtype(xmlNodePtr ptr, eni_ecat_cmd_type* cmd_type)
{
    if (!cmd_type) {
        return;
    }
    while (ptr != NULL) {
        if ((!xmlStrcmp(ptr->name, BAD_CAST"Cmd"))) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                // FIXME add some error and validty checking. if node is set correctly and has the type
                cmd_type->cmd = atoi((const char*)key);
                xmlFree(key);
            }
        }

        if ((!xmlStrcmp(ptr->name, BAD_CAST"Ado"))) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                // FIXME add some error and validty checking. if node is set correctly and has the type
                cmd_type->ado = atoi((const char*)key);
                xmlFree(key);
            }
        }

        if ((!xmlStrcmp(ptr->name, BAD_CAST"Addr"))) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                // FIXME add some error and validty checking. if node is set correctly and has the type
                cmd_type->addr = atoi((const char*)key);
                xmlFree(key);
            }
        }
        
        ptr = ptr->next;
    }
}

void ecat_eni_parse_initcmd(xmlNodePtr ptr, struct list_head* list)
{
    if (!list) {
        return;
    }
    
    eni_initcmd* initcmd;
    initcmd = (eni_initcmd*)ecat_malloc(sizeof(eni_initcmd));
    if (!initcmd) {
        return;
    }
    memset(initcmd, 0, sizeof(eni_initcmd));
    INIT_LIST_HEAD(&initcmd->initcmd_list);
    while (ptr != NULL) {
        if ((!xmlStrcmp(ptr->name, BAD_CAST"ECatCmdType"))) {
            ecat_eni_parse_ecatcmdtype(ptr, &initcmd->ecat_cmd_type);
        }
        
        ptr = ptr->next;
    }
    
    list_add_tail(&initcmd->initcmd_list, list);
}


void ecat_eni_parse_variabletype(xmlNodePtr ptr, eni_variable_type* type)
{
    if (!type) {
        return;
    }
    while (ptr != NULL) {
        if ((!xmlStrcmp(ptr->name, BAD_CAST"Name"))) {
            
        }

        if ((!xmlStrcmp(ptr->name, BAD_CAST"Comment"))) {
            
        }

        if ((!xmlStrcmp(ptr->name, BAD_CAST"DataType"))) {
            
        }

        if ((!xmlStrcmp(ptr->name, BAD_CAST"BitSize"))) {
            
        }

        if ((!xmlStrcmp(ptr->name, BAD_CAST"BitOffs"))) {
            
        }
        
        ptr = ptr->next;
    }
}

void ecat_eni_parse_transitionType(xmlNodePtr ptr, eni_transitionType* transition)
{
    if (!transition) {
        return;
    }
    if (ptr != NULL) {
        xmlChar* s = xmlNodeGetContent(ptr);
        if (s) {
            if (strcmp((const char*)s, "IP")==0) {
                transition->type |= ENI_TRANSITION_IP_TYPE;
            } else if (strcmp((const char*)s, "PS")==0) {
                transition->type |= ENI_TRANSITION_PS_TYPE;
            } else if (strcmp((const char*)s, "PI")==0) {
                transition->type |= ENI_TRANSITION_PI_TYPE;
            } else if (strcmp((const char*)s, "SP")==0) {
                transition->type |= ENI_TRANSITION_SP_TYPE;
            } else if (strcmp((const char*)s, "SO")==0) {
                transition->type |= ENI_TRANSITION_SO_TYPE;
            } else if (strcmp((const char*)s, "SI")==0) {
                transition->type |= ENI_TRANSITION_SI_TYPE;
            } else if (strcmp((const char*)s, "OS")==0) {
                transition->type |= ENI_TRANSITION_OS_TYPE;
            } else if (strcmp((const char*)s, "OP")==0) {
                transition->type |= ENI_TRANSITION_OP_TYPE;
            } else if (strcmp((const char*)s, "OI")==0) {
                transition->type |= ENI_TRANSITION_OI_TYPE;
            } else if (strcmp((const char*)s, "IB")==0) {
                transition->type |= ENI_TRANSITION_IB_TYPE;
            } else if (strcmp((const char*)s, "BI")==0) {
                transition->type |= ENI_TRANSITION_BI_TYPE;
            } else if (strcmp((const char*)s, "II")==0) {
                transition->type |= ENI_TRANSITION_II_TYPE;
            } else if (strcmp((const char*)s, "PP")==0) {
                transition->type |= ENI_TRANSITION_PP_TYPE;
            } else if (strcmp((const char*)s, "SS")==0) {
                transition->type |= ENI_TRANSITION_SS_TYPE;
            }
            xmlFree(s);
        }
    }
}

