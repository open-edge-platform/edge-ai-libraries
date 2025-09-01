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
 * @file enislavemailbox.h
 * 
 */

#ifndef __ENI_SLAVE_MAILBOX_H__
#define __ENI_SLAVE_MAILBOX_H__

#include "../enicommon.h"
#include "../enitypes.h"

typedef struct {
    uint32_t start;
    uint32_t length;
    uint32_t* pollTime;
    uint32_t* statusBitAddr;
} eni_mailboxRecvInfoType;

typedef struct {
    uint32_t start;
    uint32_t length;
    uint8_t shortSend;  //reserved for future use
} eni_mailboxSendingInfoType;

/**
* @brief eni_mailboxBootstrap represents what slave mailbox is composed
*/

typedef struct {
    eni_mailboxSendingInfoType send;    //output mailbox settings for bootstrap mode
    eni_mailboxRecvInfoType recv;       //input mailbox settings for bootstrap mode
} eni_mailboxBootstrap;

#define PROTOCOL_MAILBOX_AOE        (1<<0)
#define PROTOCOL_MAILBOX_EOE        (1<<1)
#define PROTOCOL_MAILBOX_COE        (1<<2)
#define PROTOCOL_MAILBOX_SOE        (1<<3)
#define PROTOCOL_MAILBOX_FOE        (1<<4)
#define PROTOCOL_MAILBOX_VOE        (1<<5)
#define PROTOCOL_MAILBOX_MASK       (0x3F)

/**
* @brief eni_mailbox_coe_initcmds represents what slave mailbox coe commands is composed
*/

typedef struct {
    struct list_head initcmds_list;
}eni_mailbox_coe_initcmds;

#define ENI_SLAVE_MAILBOX_CCS_UPLOAD_TYPE       1
#define ENI_SLAVE_MAILBOX_CCS_DOWNLOAD_TYPE     2

/**
* @brief eni_mailbox_coe_initcmd represents what a single slave mailbox coe command is composed
*/

typedef struct {
    struct list_head list;
    uint8_t fixed;                //True: vendor fixed command, false: user added init command
    eni_transitionType transition;//Init command will be sent at the defined transitions
    uint32_t timeout;             //Timeout in ms for this command
    uint8_t ccs;                  //command type
    uint32_t index;               //Index of the CANopen SDO
    uint32_t subindex;            //Subindex of the CANopen SDO
    uint32_t* data;               //SDO data
    uint8_t  disabled;            //boolean, determines whether InitCmd shall be sent
} eni_slave_mailbox_coe_initcmd;

/**
* @brief eni_mailbox_coe represents what slave mailbox coe is composed
*/

typedef struct {
    struct list_head initcmds_list;
} eni_slave_mailbox_coe;

/**
* @brief eni_mailbox_soe_initcmds represents what slave mailbox soe commands is composed
*/

typedef struct {
    struct list_head initcmds_list;
}eni_mailbox_soe_initcmds;

/**
* @brief eni_mailbox_soe_initcmd represents what a single slave mailbox soe command is composed
*/

typedef struct {
    struct list_head list;
    eni_transitionType transition;//Init command will be sent at the defined transitions
    uint32_t timeout;             //Timeout in ms for this command
    uint32_t opcode;          // SoE OpCode for this initcmd
    uint32_t driveno;         // Drive number
    uint32_t idn;             //IDN for this command
    uint8_t* data;               //Data of the IDN
    uint8_t  disabled;            //boolean, determines whether InitCmd shall be sent
} eni_slave_mailbox_soe_initcmd;


/**
* @brief eni_mailbox_soe represents what slave mailbox soe is composed
*/

typedef struct {
    struct list_head initcmds_list;
} eni_slave_mailbox_soe;

/**
* @brief eni_slave_mailbox represents what slave mailbox is composed
*/

typedef struct {
    eni_mailboxSendingInfoType send;    //output mailbox settings
    eni_mailboxRecvInfoType recv;       //input mailbox settings
    eni_mailboxBootstrap* bootstrap;    //mailbox settings for bootstrap mode
    uint8_t protocol;                   //The protocols that are supported by this slave device
    eni_slave_mailbox_coe* coe;         //Devices supports CANopen over EtherCAT
    eni_slave_mailbox_soe* soe;         //Devices supports Serco over EtherCAT
}eni_slave_mailbox;

void ecat_eni_parse_slavemailbox(xmlNodePtr ptr, eni_slave_mailbox* mailbox);
void ecat_eni_free_slave_mailbox(eni_slave_mailbox* mailbox);
#endif
