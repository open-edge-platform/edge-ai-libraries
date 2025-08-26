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
 * @file enislaveinfo.h
 * 
 */

#ifndef __ENI_SLAVE_INFO_H__
#define __ENI_SLAVE_INFO_H__

#include "../enicommon.h"
#include "../enitypes.h"

/**
* @brief eni_slave_info represents what slave info is composed
*/

typedef struct {
    uint8_t *name;                ///Name of the EtherCAT slave device
    uint32_t physAddr;            ///Configured Station Address of the EtherCAT slave device
    uint32_t autoIncAddr;        ///Auto Increment Address of the slave device
    uint8_t *identification;    ///Identification information for this device
    uint32_t physics;            ///Physics at the infividual ports of the slave
    uint32_t vendorId;            ///EtherCAT Vendor ID assigned by the EtherCAT Technology Group
    uint32_t productCode;        ///Product Code of the slave device
    uint32_t revisionNo;        ///Revision Number of the slave device
    uint32_t serialNo;            ///Serial Number of the slave device
    uint32_t *productRevision;    ///Product Revision Number of the slave device
}eni_slave_info;

void ecat_eni_parse_slaveinfo(xmlNodePtr ptr, eni_slave_info* info);
void ecat_eni_free_slave_info(eni_slave_info* info);
#endif
