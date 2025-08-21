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
 * @file enislaveprocessdata.h
 * 
 */

#ifndef __ENI_SLAVE_PROCESSDATA_H__
#define __ENI_SLAVE_PROCESSDATA_H__

#include "../enicommon.h"
#include "../enitypes.h"

typedef struct {
    struct list_head list;
    int32_t bit_start;
    int32_t bit_len;
}eni_slave_processdata_send;

typedef struct {
    struct list_head list;
    int32_t bit_start;
    int32_t bit_len;
}eni_slave_processdata_recv;

typedef struct {
    struct list_head list;
    int32_t index;
} eni_slave_pdo_indices;

#define ENI_SM_INVAILD_TYPE     0
#define ENI_SM_OUTPUTS_TYPE     1
#define ENI_SM_INPUTS_TYPE      2

typedef struct {
    struct list_head list;
    uint8_t type;
    int32_t startAddress;
    int32_t controlByte;
    uint8_t enable;
    int32_t* watchdog;
    struct list_head pdo_list;
} eni_slave_processdata_sm;

typedef struct {
    struct list_head list;
    eni_pdo_type pdo_type;
}eni_slave_processdata_pdo;

/**
 * @brief This element describes the process data and contains info for logical addressing and SyncManager
 */

typedef struct {
    struct list_head send_list;    //Description of the output process data for one output sm
    struct list_head recv_list;    //Description of the output process data for one output sm
    struct list_head sm_list;      //Settings of SyncManager
    struct list_head txpdo_list;   //Output PDO send from Master to this slave
    struct list_head rxpdo_list;   //Input PDO send from this slve to the master
}eni_slave_processdata;

void ecat_eni_parse_slaveprocessdata(xmlNodePtr ptr, eni_slave_processdata* processdata);
uint8_t ecat_eni_slave_smlist_size(struct list_head* list);
uint32_t ecat_eni_slave_sm_pdolist_size(struct list_head* list);
uint32_t ecat_eni_slave_entry_size(struct list_head* list);
eni_slave_processdata_pdo* ecat_get_pdo_info_by_index(eni_slave_processdata* processdata, uint8_t sm_id, uint32_t index);
void ecat_eni_free_slave_processdata(eni_slave_processdata* processdata);
#endif
