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
 * @file eniprocessimage.h
 * 
 */

#ifndef __ENI_PROCESS_IMAGE_H__
#define __ENI_PROCESS_IMAGE_H__

#include "enicommon.h"
#include "enitypes.h"

typedef struct {
    struct list_head in_var;
    eni_variable_type in_type;
}pi_inputs_var;

typedef struct {
    struct list_head out_var;
    eni_variable_type out_type;
}pi_outputs_var;

typedef struct {
    uint32_t byte_size;             //Size of the input image in bytes
    struct list_head inputs_var;
}eni_pi_inputs;

typedef struct {
    uint32_t byte_size;             //Size of the output image in bytes
    struct list_head outputs_var;
}eni_pi_outputs;

/**
*@brief the EtherCAT process image defines the layout of the process inpiuts and outputs
*/

typedef struct {
    eni_pi_inputs *inputs;		//Input process image of the master
    eni_pi_outputs *outputs;	//Output process image of the master
}eni_config_processimage;

void ecat_eni_parse_processimage(xmlNodePtr ptr, eni_config_processimage* processimage);
void ecat_eni_free_processimage(eni_config_processimage* image);
#endif
