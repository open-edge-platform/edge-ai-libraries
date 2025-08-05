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
 * @file enislavedc.h
 * 
 */

#ifndef __ENI_SLAVE_DC_H__
#define __ENI_SLAVE_DC_H__

#include "../enicommon.h"
#include "../enitypes.h"

/**
* @brief eni_slave_dc represents what slave dc is composed
*/

typedef struct {
    uint8_t potentialReferenceClock; //boolean, determines whether the device can be used as a reference clock or not
    uint8_t referenceClock;          //boolean, determines if the device is the reference clock or not
    uint32_t* cycleTime0;            //Cycle time for Sync0 event in ns
    uint32_t* cycleTime1;            //Calculated value in ns CycleTime1 = Cycle time if Sync1 event - Cycle time of Sync0 event + Shift time of Sync0 event
    uint32_t* shiftTime;             //Shift time of Sync0 event in ns
}eni_slave_dc;

void ecat_eni_parse_slavedc(xmlNodePtr ptr, eni_slave_dc* dc);
void ecat_eni_free_slave_dc(eni_slave_dc* dc);
#endif
