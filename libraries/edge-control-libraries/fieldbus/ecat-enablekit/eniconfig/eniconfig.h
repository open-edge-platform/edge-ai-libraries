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
 * @file eniconfig.h
 * 
 */

#ifndef __ENI_CONFIG_H__
#define __ENI_CONFIG_H__

#include "enicommon.h"
#include "enimaster.h"
#include "enislave.h"
#include "enicyclic.h"
#include "eniprocessimage.h"
#include "enitypes.h"

/**
 *@brief the EtherCAT Config element is the root element of the EtherCAT Network description 
 */

typedef struct {
    eni_config_master master;              //General information about the EtherCAT master device
    struct list_head slave_list;           //Information about an individual EtherCAT slave device
    eni_config_cyclic* cyclic;             //All EtherCAT commands which have to be send cyclically are described
    eni_config_processimage* processimage; //Description of the process image of the master
}eni_config;

typedef struct {
    eni_config config;
}ecat_eni;

typedef struct {
    uint32_t index;
    uint32_t subindex;
    uint32_t bitlen;
} pdo_info;

/**
 * @brief Load ENI elements.
 * @param name The name of ENI .xml file.
 * @return Pointer to EtherCAT ENI information.
 */
ecat_eni* ecat_load_eni(char* name);

/**
 * @brief Get the cycle time of EtherCAT network.
 * @param config Pointer to EtherCAT ENI configuration.
 * @return Cycle time.
 */
uint32_t ecat_eni_get_cycletime(eni_config* config);

/**
 * @brief Test to parse ENI .xml file.
 * @param name The name of ENI .xml file.
 */
void test_eniconfig(char* name);

/**
 * @brief Free ENI configurations.
 * @param info Pointer to EtherCAT ENI information.
 */
void eni_config_free(ecat_eni* info);

struct list_head* eni_config_get_slave_pdo(ecat_eni* info, uint32_t id);
#endif

