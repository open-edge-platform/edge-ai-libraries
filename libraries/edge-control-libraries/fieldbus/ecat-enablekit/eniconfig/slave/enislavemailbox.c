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
 * @file enislavemailbox.c
 * 
 */

#include "enislavemailbox.h"

#define ENI_SLAVE_MAILBOX_LOG "ENI_SLAVE_MAILBOX"

/**
*@brief This function is responsible for parsing EtherCAT ENI slave mailbox send
*@param ptr is used to point at certain row of ENI file for parsing
*@param send is pointing at ENI slave mailbox send object to collect parsing results
*/

static void ecat_eni_parse_slavemailbox_sendinginfo(xmlNodePtr ptr, eni_mailboxSendingInfoType* send)
{
    if (!send) {
        return;
    }
    while (ptr != NULL) {
        if (!xmlStrcmp(ptr->name, BAD_CAST"Start")) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                send->start = atoi((const char*)key);
                xmlFree(key);
            }
        }
        if (!xmlStrcmp(ptr->name, BAD_CAST"Length")) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                send->length = atoi((const char*)key);
                xmlFree(key);
            }
        }
        ptr = ptr->next;
    }
}

/**
*@brief This function is responsible for parsing EtherCAT ENI slave mailbox receive
*@param ptr is used to point at certain row of ENI file for parsing
*@param recv is pointing at ENI slave mailbox receive object to collect parsing results
*/

static void ecat_eni_parse_slavemailbox_recvinfo(xmlNodePtr ptr, eni_mailboxRecvInfoType* recv)
{
    if (!recv) {
        return;
    }
    while (ptr != NULL) {
        if (!xmlStrcmp(ptr->name, BAD_CAST"Start")) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                recv->start = atoi((const char*)key);
                xmlFree(key);
            }
        }
        if (!xmlStrcmp(ptr->name, BAD_CAST"Length")) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                recv->length = atoi((const char*)key);
                xmlFree(key);
            }
        }
        if (!xmlStrcmp(ptr->name, BAD_CAST"PollTime")) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                if (!recv->pollTime) {
                    recv->pollTime = (uint32_t*)ecat_malloc(sizeof(uint32_t));
                }
                if (recv->pollTime) {
                    *recv->pollTime = atoi((const char*)key);
                }
                xmlFree(key);
            }
        }
        ptr = ptr->next;
    }
}

/**
*@brief This function is responsible for parsing EtherCAT ENI slave mailbox bootstrap
*@param ptr is used to point at certain row of ENI file for parsing
*@param bootstrap is pointing at ENI slave mailbox bootstrap object to collect parsing results
*/

static void ecat_eni_parse_slavemailbox_bootstrap(xmlNodePtr ptr, eni_mailboxBootstrap* bootstrap)
{
    if (!bootstrap) {
        return;
    }
    while (ptr != NULL) {
        if (!xmlStrcmp(ptr->name, BAD_CAST"Send")) {
            xmlNodePtr node = ptr->xmlChildrenNode;
            ecat_eni_parse_slavemailbox_sendinginfo(node, &bootstrap->send);
        }
        if (!xmlStrcmp(ptr->name, BAD_CAST"Recv")) {
            xmlNodePtr node = ptr->xmlChildrenNode;
            ecat_eni_parse_slavemailbox_recvinfo(node, &bootstrap->recv);
        }
        ptr = ptr->next;
    }
}

/**
*@brief This function is responsible for parsing EtherCAT ENI slave mailbox protocol
*@param ptr is used to point at certain row of ENI file for parsing
*@param protocol is used to representing the protocols supported by the slave device
*/

static void ecat_eni_parse_slavemailbox_protocol(xmlNodePtr ptr, uint8_t* protocol)
{
    if (!protocol) {
        return;
    }
    if (ptr != NULL) {
        xmlChar* s = xmlNodeGetContent(ptr);
        if (s) {
            if (strcmp((const char*)s, "AoE")==0) {
                *protocol |= PROTOCOL_MAILBOX_AOE;
            } else if (strcmp((const char*)s, "EoE")==0) {
                *protocol |= PROTOCOL_MAILBOX_EOE;
            } else if (strcmp((const char*)s, "CoE")==0) {
                *protocol |= PROTOCOL_MAILBOX_COE;
            } else if (strcmp((const char*)s, "SoE")==0) {
                *protocol |= PROTOCOL_MAILBOX_SOE;
            } else if (strcmp((const char*)s, "FoE")==0) {
                *protocol |= PROTOCOL_MAILBOX_FOE;
            } else if (strcmp((const char*)s, "VoE")==0) {
                *protocol |= PROTOCOL_MAILBOX_VOE;
            }
            xmlFree(s);
        }
    }
}

/**
*@brief This function is responsible for parsing EtherCAT ENI slave mailbox coe
*@param ptr is used to point at certain row of ENI file for parsing
*@param initcmds_list is pointing at init command list supports CANopen over EtherCAT
*/

static void ecat_eni_parse_slavemailbox_coe_initcmd(xmlNodePtr ptr, struct list_head* initcmds_list)
{
    eni_slave_mailbox_coe_initcmd* initcmd;
    if (!initcmds_list) {
        MOTION_CONSOLE_ERR(ENI_SLAVE_MAILBOX_LOG "The list of initcmds is NULL!\n");
        return;
    }
    initcmd = (eni_slave_mailbox_coe_initcmd*)ecat_malloc(sizeof(eni_slave_mailbox_coe_initcmd));
    if (!initcmd) {
        MOTION_CONSOLE_ERR(ENI_SLAVE_MAILBOX_LOG "Failed to malloc for initcmd!\n");
        return;
    }
    memset(initcmd, 0, sizeof(eni_slave_mailbox_coe_initcmd));
    INIT_LIST_HEAD(&initcmd->list);
    /* get fixed value */
    if(ptr != NULL) {
        xmlNodePtr ptr_p = ptr->parent;
        if (ptr_p != NULL) {
            xmlChar* id;
            id = xmlGetProp(ptr_p, BAD_CAST"Fixed");
            if (id) {
                if (!xmlStrcmp(id, BAD_CAST"true"))
                    initcmd->fixed = 1;
                else
                    initcmd->fixed = 0;
                xmlFree(id);
            }
        }
    }
    while (ptr != NULL) {
        if (!xmlStrcmp(ptr->name, BAD_CAST"Transition")) {
            ecat_eni_parse_transitionType(ptr, &initcmd->transition);
        }
        if (!xmlStrcmp(ptr->name, BAD_CAST"Timeout")) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                initcmd->timeout = atoi((const char*)key);
                xmlFree(key);
            }
        }
        if (!xmlStrcmp(ptr->name, BAD_CAST"Ccs")) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                initcmd->ccs = atoi((const char*)key);
                xmlFree(key);
            }
        }
        if (!xmlStrcmp(ptr->name, BAD_CAST"Index")) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                initcmd->index = atoi((const char*)key);
                xmlFree(key);
            }
        }
        if (!xmlStrcmp(ptr->name, BAD_CAST"SubIndex")) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                initcmd->subindex = atoi((const char*)key);
                xmlFree(key);
            }
        }
        if (!xmlStrcmp(ptr->name, BAD_CAST"Data")) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                uint32_t len = strlen(key);
                if (len > 0) {
                    uint32_t size = len/8;
                    if (initcmd->data) {
                        ecat_free(initcmd->data);
                    }
                    if (len%8) {
                        size += 1;
                    }
                    initcmd->data = (uint32_t*)ecat_malloc(sizeof(uint32_t)*size);
                    if (initcmd->data) {
                        memset(initcmd->data, 0, size);
                        if (ecat_sscan_hexbinary(key, initcmd->data, size) != 0) {
                            ecat_free(initcmd->data);
                            initcmd->data = NULL;
                        }
                    }
                }
                xmlFree(key);
            }
        }
        if (!xmlStrcmp(ptr->name, BAD_CAST"Disabled")) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                initcmd->disabled = atoi((const char*)key);
                xmlFree(key);
            }
        }
        ptr = ptr->next;
    }
    list_add_tail(&initcmd->list, initcmds_list);
}

/**
*@brief This function is responsible for parsing EtherCAT ENI slave mailbox soe
*@param ptr is used to point at certain row of ENI file for parsing
*@param initcmds_list is pointing at init command list supports serco over EtherCAT
*/

static void ecat_eni_parse_slavemailbox_soe_initcmd(xmlNodePtr ptr, struct list_head* initcmds_list)
{
    eni_slave_mailbox_soe_initcmd* initcmd;
    if (!initcmds_list) {
        MOTION_CONSOLE_ERR(ENI_SLAVE_MAILBOX_LOG "The list of initcmds is NULL!\n");
        return;
    }
    initcmd = (eni_slave_mailbox_soe_initcmd*)ecat_malloc(sizeof(eni_slave_mailbox_soe_initcmd));
    if (!initcmd) {
        MOTION_CONSOLE_ERR(ENI_SLAVE_MAILBOX_LOG "Failed to malloc for initcmd!\n");
        return;
    }
    memset(initcmd, 0, sizeof(eni_slave_mailbox_soe_initcmd));
    INIT_LIST_HEAD(&initcmd->list);
    while (ptr != NULL) {
        if (!xmlStrcmp(ptr->name, BAD_CAST"Transition")) {
            ecat_eni_parse_transitionType(ptr, &initcmd->transition);
        }

        if (!xmlStrcmp(ptr->name, BAD_CAST"Timeout")) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                initcmd->timeout = atoi((const char*)key);
                xmlFree(key);
            }
        }

	if (!xmlStrcmp(ptr->name, BAD_CAST"OpCode")) {
	    xmlChar* key;
	    key = xmlNodeGetContent(ptr);
	    if (key) {
	        initcmd->opcode = atoi((const char*)key);
		xmlFree(key);
	    }
	}

	if (!xmlStrcmp(ptr->name, BAD_CAST"DriveNo")) {
	    xmlChar* key;
	    key = xmlNodeGetContent(ptr);
	    if (key) {
	        initcmd->driveno = atoi((const char*)key);
		xmlFree(key);
	    }
	}

        if (!xmlStrcmp(ptr->name, BAD_CAST"IDN")) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                initcmd->idn = atoi((const char*)key);
                xmlFree(key);
            }
        }
        if (!xmlStrcmp(ptr->name, BAD_CAST"Data")) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                uint32_t len = strlen(key);
                if (len > 0) {
                    uint32_t size = len/8;
                    if (initcmd->data) {
                        ecat_free(initcmd->data);
                    }
                    if (len%8) {
                        size += 1;
                    }
                    initcmd->data = (uint8_t*)ecat_malloc(sizeof(uint8_t)*size);
                    if (initcmd->data) {
                        memset(initcmd->data, 0, size);
                        if (ecat_sscan_hexbinary(key, initcmd->data, size) != 0) {
                            ecat_free(initcmd->data);
                            initcmd->data = NULL;
                        }
                    }
                }
                xmlFree(key);
            }
        }
        if (!xmlStrcmp(ptr->name, BAD_CAST"Disabled")) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {
                initcmd->disabled = atoi((const char*)key);
                xmlFree(key);
            }
        }

        ptr = ptr->next;
    }
    list_add_tail(&initcmd->list, initcmds_list);
}


static void ecat_eni_parse_slavemailbox_coe_initcmds(xmlNodePtr ptr, eni_slave_mailbox_coe* coe)
{
    if (!coe) {
        MOTION_CONSOLE_ERR(ENI_SLAVE_MAILBOX_LOG "CoE is Null!\n");
        return;
    }
    INIT_LIST_HEAD(&coe->initcmds_list);
    while (ptr != NULL) {
        if (!xmlStrcmp(ptr->name, BAD_CAST"InitCmd")) {
            xmlNodePtr node = ptr->xmlChildrenNode;
            ecat_eni_parse_slavemailbox_coe_initcmd(node, &coe->initcmds_list);
        }
        ptr = ptr->next;
    }
}

static void ecat_eni_parse_slavemailbox_soe_initcmds(xmlNodePtr ptr, eni_slave_mailbox_soe* soe)
{
    if (!soe) {
        MOTION_CONSOLE_ERR(ENI_SLAVE_MAILBOX_LOG "SoE is Null!\n");
        return;
    }
    INIT_LIST_HEAD(&soe->initcmds_list);
    while (ptr != NULL) {
        if (!xmlStrcmp(ptr->name, BAD_CAST"InitCmd")) {
            xmlNodePtr node = ptr->xmlChildrenNode;
            ecat_eni_parse_slavemailbox_soe_initcmd(node, &soe->initcmds_list);
        }
        ptr = ptr->next;
    }
}


static void ecat_eni_parse_slavemailbox_coe(xmlNodePtr ptr, eni_slave_mailbox_coe* coe)
{
    if (!coe) {
        return;
    }
    while (ptr != NULL) {
        if (!xmlStrcmp(ptr->name, BAD_CAST"InitCmds")) {
            xmlNodePtr node = ptr->xmlChildrenNode;
            ecat_eni_parse_slavemailbox_coe_initcmds(node, coe);
        }
        ptr = ptr->next;
    }
}

static void ecat_eni_parse_slavemailbox_soe(xmlNodePtr ptr, eni_slave_mailbox_soe* soe)
{
    if (!soe) {
        return;
    }
    while (ptr != NULL) {
        if (!xmlStrcmp(ptr->name, BAD_CAST"InitCmds")) {
            xmlNodePtr node = ptr->xmlChildrenNode;
            ecat_eni_parse_slavemailbox_soe_initcmds(node, soe);
        }
        ptr = ptr->next;
    }
}


/**
*@brief This function is responsible for parsing EtherCAT ENI slave mailbox
*@param ptr is used to point at certain row of ENI file for parsing
*@param mailbox is pointing at ENI slave mailbox object to collect parsing results
*/

void ecat_eni_parse_slavemailbox(xmlNodePtr ptr, eni_slave_mailbox* mailbox)
{
    if (!mailbox) {
        return;
    }
    while (ptr != NULL) {
        if (!xmlStrcmp(ptr->name, BAD_CAST"Send")) {
            xmlNodePtr node = ptr->xmlChildrenNode;
            ecat_eni_parse_slavemailbox_sendinginfo(node, &mailbox->send);
        }
        if (!xmlStrcmp(ptr->name, BAD_CAST"Recv")) {
            xmlNodePtr node = ptr->xmlChildrenNode;
            ecat_eni_parse_slavemailbox_recvinfo(node, &mailbox->recv);
        }
        if (!xmlStrcmp(ptr->name, BAD_CAST"BootStrap")) {
            xmlNodePtr node = ptr->xmlChildrenNode;
            if (!mailbox->bootstrap) {
                mailbox->bootstrap = (eni_mailboxBootstrap*)ecat_malloc(sizeof(eni_mailboxBootstrap));
            }
            if (mailbox->bootstrap) {
                memset(mailbox->bootstrap, 0, sizeof(eni_mailboxBootstrap));
            }
            ecat_eni_parse_slavemailbox_bootstrap(node, mailbox->bootstrap);
        }
        if (!xmlStrcmp(ptr->name, BAD_CAST"Protocol")) {
            ecat_eni_parse_slavemailbox_protocol(ptr, &mailbox->protocol);
        }
        if (!xmlStrcmp(ptr->name, BAD_CAST"CoE")) {
            xmlNodePtr node = ptr->xmlChildrenNode;
            if (!mailbox->coe) {
                mailbox->coe = (eni_slave_mailbox_coe*)ecat_malloc(sizeof(eni_slave_mailbox_coe));
            }
            if (mailbox->coe) {
                memset(mailbox->coe, 0, sizeof(eni_slave_mailbox_coe));
            }
            ecat_eni_parse_slavemailbox_coe(node, mailbox->coe);
        }
	if (!xmlStrcmp(ptr->name, BAD_CAST"SoE")) {
	    xmlNodePtr node = ptr->xmlChildrenNode;
	    if (!mailbox->soe) {
		mailbox->soe = (eni_slave_mailbox_soe*)ecat_malloc(sizeof(eni_slave_mailbox_soe));
	    }
	    if (mailbox->soe) {
	        memset(mailbox->soe, 0, sizeof(eni_slave_mailbox_soe));
	    }
	    ecat_eni_parse_slavemailbox_soe(node, mailbox->soe);
	}
        ptr = ptr->next;
    }
}

static void ecat_eni_free_slave_mailbox_recvinfo(eni_mailboxRecvInfoType* recv)
{
    if (!recv) {
        return;
    }
    if (recv->pollTime) {
        ecat_free(recv->pollTime);
        recv->pollTime = NULL;
    }
    if (recv->statusBitAddr) {
        ecat_free(recv->statusBitAddr);
        recv->statusBitAddr = NULL;
    }
}

static void ecat_eni_free_slave_mailbox_sendinfo(eni_mailboxSendingInfoType* send)
{
    if (!send) {
        return;
    }
}

static void ecat_eni_free_slave_mailbox_bootstrap(eni_mailboxBootstrap* bootstrap)
{
    if (!bootstrap) {
        return;
    }
    ecat_eni_free_slave_mailbox_recvinfo(&bootstrap->recv);
    ecat_eni_free_slave_mailbox_sendinfo(&bootstrap->send);
    ecat_free(bootstrap);
    bootstrap = NULL;
}

static void ecat_eni_free_slave_mailbox_coe(eni_slave_mailbox_coe* coe)
{
    eni_slave_mailbox_coe_initcmd* initcmd = NULL;
    eni_slave_mailbox_coe_initcmd* next = NULL;
    if (!coe) {
        return;
    }
    list_for_each_entry_safe(initcmd, next, &coe->initcmds_list, list) {
        if (initcmd) {
            list_del(&initcmd->list);
            if (initcmd->data) {
                ecat_free(initcmd->data);
                initcmd->data = NULL;
            }
            ecat_free(initcmd);
            initcmd = NULL;
        }
    }
    INIT_LIST_HEAD(&coe->initcmds_list);
    ecat_free(coe);
    coe = NULL;
}

static void ecat_eni_free_slave_mailbox_soe(eni_slave_mailbox_soe* soe)
{
    eni_slave_mailbox_soe_initcmd* initcmd = NULL;
    eni_slave_mailbox_soe_initcmd* next = NULL;
    if (!soe) {
        return;
    }
    list_for_each_entry_safe(initcmd, next, &soe->initcmds_list, list) {
        if (initcmd) {
            list_del(&initcmd->list);
            if (initcmd->data) {
                ecat_free(initcmd->data);
                initcmd->data = NULL;
            }
            ecat_free(initcmd);
            initcmd = NULL;
        }
    }
    INIT_LIST_HEAD(&soe->initcmds_list);
    ecat_free(soe);
    soe = NULL;
}


void ecat_eni_free_slave_mailbox(eni_slave_mailbox* mailbox)
{
    if (!mailbox) {
        return;
    }
    ecat_eni_free_slave_mailbox_recvinfo(&mailbox->recv);
    ecat_eni_free_slave_mailbox_sendinfo(&mailbox->send);
    ecat_eni_free_slave_mailbox_bootstrap(mailbox->bootstrap);
    ecat_eni_free_slave_mailbox_coe(mailbox->coe);
    ecat_eni_free_slave_mailbox_soe(mailbox->soe);
    ecat_free(mailbox);
    mailbox = NULL;
}
