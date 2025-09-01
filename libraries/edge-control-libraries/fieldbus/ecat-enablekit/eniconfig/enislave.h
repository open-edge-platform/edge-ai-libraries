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
 * @file enislave.h
 * 
 */

#ifndef __ENI_SLAVE_H__
#define __ENI_SLAVE_H__

#include "enicommon.h"
#include "enitypes.h"
#include "slave/enislaveinfo.h"
#include "slave/enislaveprocessdata.h"
#include "slave/enislavemailbox.h"
#include "slave/enislaveinitcmds.h"
#include "slave/enislavepreviousport.h"
#include "slave/enislavehotconnect.h"
#include "slave/enislavedc.h"

/**
 *@brief the Slave element describes the identity of each slave device, init commands, process data, mailbox and synchronization attributes
 */

typedef struct {
    struct list_head list;
    eni_slave_info info;                   ///identity of the EtherCAT slave device
    eni_slave_processdata* processdata;    ///Description of the process data of this slave
    eni_slave_mailbox* mailbox;            ///mailbox  settings of the slave device
    eni_slave_initcmds* initcmds;          ///Initialization commands that are necessary for the slave device to start up 
    eni_slave_dc* dc;                      ///Description odf Distributed Clocks settings
} eni_config_slave;

/**
 * @brief The function is used to parse eni file, copying info, process data, mail box, init cmd and DC to slave.
 * @param ptr Point at certain position of ENI file for parsing.
 * @param list List of ENI slaves.
*/
void ecat_eni_parse_slaveconfig(xmlNodePtr ptr, struct list_head* list);

/**
 * @brief Free ENI element slave.
 * @param list List of ENI slaves.
 */
void ecat_eni_free_slave(struct list_head* list);
#endif
