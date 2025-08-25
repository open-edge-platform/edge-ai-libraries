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
 * @file enislaveinitcmds.h
 * 
 */

#ifndef __ENI_SLAVE_INITCMDS_H__
#define __ENI_SLAVE_INITCMDS_H__

#include "../enicommon.h"
#include "../enitypes.h"

/**
 * @brief Init commands are EtherCAT commands that shall be sent by the master to each slave during the specified state transitions
 */
typedef struct {
    struct list_head initcmds_list;
}eni_slave_initcmds;

void ecat_eni_parse_slaveinitcmds(xmlNodePtr ptr, eni_slave_initcmds* initcmds);
void ecat_eni_free_slave_initcmds(eni_slave_initcmds* initcmds);
#endif
