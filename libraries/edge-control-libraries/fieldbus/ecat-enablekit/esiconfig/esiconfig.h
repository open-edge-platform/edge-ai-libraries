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

#ifndef __ESI_CONFIG_H__
#define __ESI_CONFIG_H__

#include <stdint.h>
#include <stdlib.h>

#include <ecrt.h>

#include "../include/list.h"

#include "esidescription.h"
#include "esivendor.h"

#define ECAT_SLAVE_VENDOR_NAME_SIZE        (32)
#define ECAT_SLAVE_MODEL_NAME_SIZE         (32)
#define ECAT_SLAVE_VERSION_NAME_SIZE       (64)

#define ECAT_SLAVE_PDO_NAME_SIZE           (32)

/**
 *@brief EtherCAT slave information description 
 */
typedef struct {
    esi_VendorType* vendor;                 ///Vendor type of EtherCAT slave device
    esi_descriptions_info* descriptions;    ///Description of EtherCAT slave information
}ecat_slave_esi;

/**
 * @brief Get PDO size by sm_id.
 * @param device EtherCAT slave device.
 * @param sm_id SyncManager ID.
 * @return Pdo size.
 */
uint16_t ecat_esi_get_pdo_size_by_sm_id(esi_device_info* device, uint16_t sm_id);

/**
 * @brief Get SyncManager size of EtherCAT slave device.
 * @param device EtherCAT slave device.
 * @return SyncManager size.
 */
uint16_t ecat_esi_get_sm_size(esi_device_info* device);

/**
 * @brief Load slave profile.
 * @param name The name of ESI .xml file.
 * @return The pointer to EtherCAT slave infortmation.
 */
ecat_slave_esi* ecat_load_slave_profile(char* name);

/**
 * @brief Free the pointer to ESI profile.
 * @param esi The pointer to EtherCAT slave infortmation.
 */
void ecat_free_esi_profile(ecat_slave_esi* esi);

/**
 * @brief Test to parse ESI configurations.
 * @param name The Name of ESI .xml file.
 */
void test_esiconfig(char* name);
#endif
