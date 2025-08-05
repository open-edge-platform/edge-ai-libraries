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
 * @file enimaster.h
 * 
 */

#ifndef __ENI_MASTER_H__
#define __ENI_MASTER_H__

#include "enicommon.h"
#include "enitypes.h"


typedef struct {
    uint8_t *name;
    uint32_t dest;
    uint32_t src;
    uint32_t *type;
}eni_master_info;

typedef struct {
    uint32_t start_addr;
    uint32_t cnt;
}eni_master_mailboxstates;

typedef struct {
    uint32_t max_ports;
    uint32_t max_frames;
    uint32_t max_macs;
}eni_master_eoe;

typedef struct {
    struct list_head initcmds_list;
}eni_master_initcmds;

/**
 * @brief the EtherCAT Master element describes the identity of the master and configuration settings that applies to all slave devices
 */

typedef struct {
    eni_master_info info;                ///identification of the master and values needed for ethernet frame assembly
    eni_master_mailboxstates *states;    ///if one or more slaves support mailbox communication the master checks  the mailbox of one or more slaves for new messages during the cyclic processdata communication
    eni_master_eoe *eoe;                 ///Ethernet over EtherCAT describes the mapping of the IP-Protocol to EtherCAT data-link layer.
    eni_master_initcmds *initcmds;       ///Initialization commands that applies to all slaves
}eni_config_master;

/**
 * @brief The function is used to parse eni master information.
 * @param ptr Point at certain position of ENI file for parsing.
 * @param master Pointer to ENI master configuration.
 */
void ecat_eni_parse_masterconfig(xmlNodePtr ptr, eni_config_master* master);

/**
 * @brief Free ENI element slave.
 * @param master Pointer to ENI master configuration.
 */
void ecat_eni_free_masterconfig(eni_config_master* master);
#endif
