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
 * @file enislaveinitcmds.c
 * 
 */

#include "enislaveinitcmds.h"

#define ENI_SLAVE_INITCMDS_LOG "ENI_SLAVE_INITCMDS"

/**
*@brief This function is responsible for parsing EtherCAT ENI slave init command
*@param ptr is used to point at certain row of ENI file for parsing
*@param initcmds is pointing at ENI slave init command object to collect parsing results
*/

void ecat_eni_parse_slaveinitcmds(xmlNodePtr ptr, eni_slave_initcmds* initcmds)
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

/**
*@brief This function is responsible for releasing EtherCAT ENI slave init command space
*@param initcmds is pointing at ENI slave init command object
*/

void ecat_eni_free_slave_initcmds(eni_slave_initcmds* initcmds)
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
