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
 * @file eniconfig.c
 * 
 */

#include "eniconfig.h"

#define ENI_CONFIG_LOG "ENI_CONFIG"

uint32_t ecat_eni_get_cycletime(eni_config* config)
{
    if (!config) {
        return 0;
    }
    return ecat_eni_get_cyclic_cycletime(config->cyclic);
}

/**
 * @brief the function is used to parse eni file, copying master, slave, cyclic and process image information into struct
 * @param ptr is used to point at certain row of ENI file for parsing
 * @param conifg is pointing at ENI config object to collect parsing results
*/
static void ecat_eni_parse_config(xmlNodePtr ptr, eni_config* config)
{
    if (!config) {
        return;
    }
    INIT_LIST_HEAD(&config->slave_list);
    while (ptr != NULL) {
        if ((!xmlStrcmp(ptr->name, BAD_CAST"Master"))) {
            xmlNodePtr nodePtr = ptr->xmlChildrenNode;
            ecat_eni_parse_masterconfig(nodePtr, &config->master);
        }
        if ((!xmlStrcmp(ptr->name, BAD_CAST"Slave"))) {
            xmlNodePtr nodePtr = ptr->xmlChildrenNode;
            ecat_eni_parse_slaveconfig(nodePtr, &config->slave_list);
        }
        if ((!xmlStrcmp(ptr->name, BAD_CAST"Cyclic"))) {
            xmlNodePtr nodePtr = ptr->xmlChildrenNode;
            if (!config->cyclic) {
                config->cyclic = (eni_config_cyclic*)ecat_malloc(sizeof(eni_config_cyclic));
                if (config->cyclic) {
                    memset(config->cyclic, 0, sizeof(eni_config_cyclic));
                }
            }
            ecat_eni_parse_cyclic(nodePtr, config->cyclic);
        }
        if ((!xmlStrcmp(ptr->name, BAD_CAST"ProcessImage"))) {
            xmlNodePtr nodePtr = ptr->xmlChildrenNode;
            if (!config->processimage) {
                config->processimage = (eni_config_processimage*)ecat_malloc(sizeof(eni_config_processimage));
                if (config->processimage) {
                    memset(config->processimage, 0, sizeof(eni_config_processimage));
                }
            }
            ecat_eni_parse_processimage(nodePtr, config->processimage);
        }
        ptr = ptr->next;
    }
}

static void ecat_init_eni(ecat_eni* eni)
{
    if (!eni) {
        return;
    }
    memset(eni, 0, sizeof(ecat_eni));
}

ecat_eni* ecat_load_eni(char* name)
{
    ecat_eni* eni;
    xmlDocPtr doc;
    xmlNodePtr cur;

    if (!name) {
        MOTION_CONSOLE_ERR(ENI_CONFIG_LOG "xml configuration name is Null!\n");
        return NULL;
    }

    doc = xmlParseFile(name);
    if (!doc) {
        MOTION_CONSOLE_ERR(ENI_CONFIG_LOG "Failed to parse xml file(%s)!\n", name);
        goto FAILED;
    }
    cur = xmlDocGetRootElement(doc);
    if (!cur) {
        MOTION_CONSOLE_ERR(ENI_CONFIG_LOG "Root is empty\n");
        goto FAILED;
    }

    if ((xmlStrcmp(cur->name, BAD_CAST"EtherCATConfig"))) {
        MOTION_CONSOLE_ERR(ENI_CONFIG_LOG "The root is not EtherCATConfig\n");
        goto FAILED;
    }

    cur = cur->xmlChildrenNode;
    if (!cur) {
        MOTION_CONSOLE_ERR(ENI_CONFIG_LOG "The format of eni is not correct\n");
        goto FAILED;
    }

    eni = (ecat_eni*)ecat_malloc(sizeof(ecat_eni));
    if (!eni) {
        MOTION_CONSOLE_ERR(ENI_CONFIG_LOG "eni config alloc failed\n");
        goto FAILED;
    }

    ecat_init_eni(eni);
    while (cur != NULL) {
        if ((!xmlStrcmp(cur->name, BAD_CAST"Config"))) {
            xmlNodePtr nodePtr = cur->xmlChildrenNode;
            ecat_eni_parse_config(nodePtr, &eni->config);
        }
        cur = cur->next;
    }

    xmlFreeDoc(doc);
    doc = NULL;
    return eni;
FAILED:
    if (doc) {
        xmlFreeDoc(doc);
        doc = NULL;
    }
    return NULL;
}

static void ecat_eni_free_config(eni_config* config)
{
    if (!config) {
        return;
    }
    ecat_eni_free_masterconfig(&config->master);
    ecat_eni_free_slave(&config->slave_list);
    ecat_eni_free_cyclic(config->cyclic);
    ecat_eni_free_processimage(config->processimage);
}

void eni_config_free(ecat_eni* info)
{
    if (!info) {
        return;
    }
    ecat_eni_free_config(&info->config);
    ecat_free(info);
    info = NULL;
}

static void test_master(eni_config_master* master)
{
    if (!master) {
        printf("test master is NULL\n");
        return;
    }
    printf("Master:\n");
    if (master->states) {
        printf("|%15s|%12s\n","states","pass");
    } else {
        printf("|%15s|%12s\n","states","N/A");
    }
    if (master->eoe) {
        printf("|%15s|%12s\n","eoe","pass");
    } else {
        printf("|%15s|%12s\n","eoe","N/A");
    }
    if (master->initcmds) {
        printf("|%15s|%12s\n","initcmds","pass");
    } else {
        printf("|%15s|%12s\n","initcmds","N/A");
    }
}

static void test_slave(struct list_head* list)
{
    uint32_t size = 0;
    if (!list)
        return;
    eni_config_slave* slave = NULL;
    if (list_empty(list)) {
        size = 0;
    } else {
        list_for_each_entry(slave, list, list) {
            size++;
        }
    }

    printf("Slave found: %d\n", size);
    size = 0;
    list_for_each_entry(slave, list, list) {
        printf("Slave index: %d\n", size++);
        if (slave->processdata) {
            printf("|%15s|%12s\n","processdata","pass");
        } else {
            printf("|%15s|%12s\n","processdata","N/A");
        }
        if (slave->mailbox) {
            printf("|%15s|%12s\n","mailbox","pass");
        } else {
            printf("|%15s|%12s\n","mailbox","N/A");
        }
        if (slave->initcmds) {
            printf("|%15s|%12s\n","initcmds","pass");
        } else {
            printf("|%15s|%12s\n","initcmds","N/A");
        }
        if (slave->dc) {
            printf("|%15s|%12s\n","DC","pass");
        } else {
            printf("|%15s|%12s\n","DC","N/A");
        }
    }
}

static void test_cyclic(eni_config_cyclic* cyclic)
{
    printf("Cyclic:\n");
    if (cyclic) {
        printf("|%15s|%12s\n","cyclic","pass");
    } else {
        printf("|%15s|%12s\n","cyclic","N/A");
    }
}

static void test_processimage(eni_config_processimage* process)
{
    printf("Processimage:\n");
    if (process) {
        printf("|%15s|%12s\n","processimage","pass");
    } else {
        printf("|%15s|%12s\n","processimage","N/A");
    }
}

void test_eniconfig(char* name)
{
    ecat_eni* eni;
    eni=ecat_load_eni(name);
    if (eni) {
        test_master(&eni->config.master);
        test_slave(&eni->config.slave_list);
        test_cyclic(eni->config.cyclic);
        test_processimage(eni->config.processimage);
        eni_config_free(eni);
        MOTION_CONSOLE_ERR("*****$$$ ENI/XML TEST PASS $$$*****\n");
    } else {
        MOTION_CONSOLE_ERR("*****$$$ ENI/XML TEST FAIL $$$*****\n");
    }
}

