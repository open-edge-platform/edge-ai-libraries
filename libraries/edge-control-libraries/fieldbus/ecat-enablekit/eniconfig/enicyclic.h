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
 * @file enicyclic.h
 * 
 */

#ifndef __ENI_CYCLIC_H__
#define __ENI_CYCLIC_H__

#include "enicommon.h"
#include "enitypes.h"

#define ENI_INIT_MASTER_STATE       (1<<0)
#define ENI_PREOP_MASTER_STATE      (1<<1)
#define ENI_SAFEOP_MASTER_STATE     (1<<2)
#define ENI_OP_MASTER_STATE         (1<<3)
#define ENI_MASTER_STATE_MASK       (0x0F)

/**
*@brief description of 1 to n commands
*/

typedef struct {
    struct list_head cmdlist;
    uint8_t state;				//Master state the command should be sent in
    uint32_t cmd;				//EtherCAT command type
    uint32_t* adp;				//Device address
    uint32_t ado;				//Address in DPRAM of the EtherCAT slave controller
    uint32_t addr;				//Logical address in the process image of the master
    uint8_t* data;				//Data sent with this datagram
    uint32_t dataLength;		//Length of the data that should be sent
    uint32_t* cnt;				//Expected working counter of this datagram
    uint32_t inputOffs;			//Byte offset of this command in the input process image
    uint32_t outputOffs;		//Byte offset of this command in the output process image
} eni_cyclic_framecmd;

/**
*@brief description how the frames which are sent in this cycle are composed
*/

typedef struct {
    struct list_head cmds;  //description of 1 to n EtherCAT commands
} eni_cyclic_frame;

/**
*@brief the EtherCAT commands are listed that shall be sent cyclically to the slaves
*/

typedef struct {
    uint32_t cycletime;	//cycle time in us of the task sending the frames
    eni_cyclic_frame* frame;//description how the frames are sent in the cycle are composed
} eni_config_cyclic;

void ecat_eni_parse_cyclic(xmlNodePtr ptr, eni_config_cyclic* cyclic);
uint32_t ecat_eni_get_cyclic_cycletime(eni_config_cyclic* cyclic);
void ecat_eni_free_cyclic(eni_config_cyclic* cyclic);
#endif
