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
 * @file eniprocessimage.c
 * 
 */

#include "eniprocessimage.h"

#define ENI_PROCESSIMAGE_LOG "ENI_PROCESSIMAGE"

static void ecat_eni_parse_pi_inputs(xmlNodePtr ptr, eni_pi_inputs* inputs)
{
    if (!inputs) {
        return;
    }
    INIT_LIST_HEAD(&inputs->inputs_var);
}

static void ecat_eni_parse_pi_outputs(xmlNodePtr ptr, eni_pi_outputs* outputs)
{
    if (!outputs) {
        return;
    }
    INIT_LIST_HEAD(&outputs->outputs_var);
}

/**
*@brief the function is used to parse eni file, copying process image information out 
*@param ptr is used to point at certain row of ENI file for parsing
*@param processimage is pointing at ENI config object to collect parsing results
*/

void ecat_eni_parse_processimage(xmlNodePtr ptr, eni_config_processimage* processimage)
{
    if (!processimage) {
        return;
    }
    while (ptr != NULL) {
        if ((!xmlStrcmp(ptr->name, BAD_CAST"Inputs"))) {
            xmlNodePtr nodePtr = ptr->xmlChildrenNode;
            if (!processimage->inputs) {
                processimage->inputs = (eni_pi_inputs*)ecat_malloc(sizeof(eni_pi_inputs));
            }
            if (processimage->inputs) {
                memset(processimage->inputs, 0, sizeof(eni_pi_inputs));
                ecat_eni_parse_pi_inputs(nodePtr, processimage->inputs);
            }
        }

        if ((!xmlStrcmp(ptr->name, BAD_CAST"Outputs"))) {
            xmlNodePtr nodePtr = ptr->xmlChildrenNode;
            if (!processimage->outputs) {
                processimage->outputs = (eni_pi_outputs*)ecat_malloc(sizeof(eni_pi_outputs));
            }
            if (processimage->outputs) {
                memset(processimage->outputs, 0, sizeof(eni_pi_outputs));
                ecat_eni_parse_pi_outputs(nodePtr, processimage->outputs);
            }
        }
        
        ptr = ptr->next;
    }
}

static void ecat_eni_free_pi_input(eni_pi_inputs* inputs)
{
    if (!inputs) {
        return;
    }
    pi_inputs_var* var = NULL;
    pi_inputs_var* next = NULL;
    list_for_each_entry_safe(var, next, &inputs->inputs_var, in_var) {
        if (var) {
            eni_variable_type* type;
            list_del(&var->in_var);
            type = &var->in_type;
            if (type->name) {
                ecat_free(type->name);
                type->name = NULL;
            }
            if (type->comment) {
                ecat_free(type->comment);
                type->comment = NULL;
            }
            if (type->data_type) {
                ecat_free(type->data_type);
                type->data_type = NULL;
            }
            ecat_free(var);
            var = NULL;
        }
    }
    INIT_LIST_HEAD(&inputs->inputs_var);
    ecat_free(inputs);
    inputs = NULL;
}

static void ecat_eni_free_pi_output(eni_pi_outputs* outputs)
{
    if (!outputs) {
        return;
    }
    pi_outputs_var* var = NULL;
    pi_outputs_var* next = NULL;
    list_for_each_entry_safe(var, next, &outputs->outputs_var, out_var) {
        if (var) {
            eni_variable_type* type;
            list_del(&var->out_var);
            type = &var->out_type;
            if (type->name) {
                ecat_free(type->name);
                type->name = NULL;
            }
            if (type->comment) {
                ecat_free(type->comment);
                type->comment = NULL;
            }
            if (type->data_type) {
                ecat_free(type->data_type);
                type->data_type = NULL;
            }
            ecat_free(var);
            var = NULL;
        }
    }
    INIT_LIST_HEAD(&outputs->outputs_var);
    ecat_free(outputs);
    outputs = NULL;
}

void ecat_eni_free_processimage(eni_config_processimage* image)
{
    if (!image) {
        return;
    }
    if (image->inputs) {
        ecat_eni_free_pi_input(image->inputs);
    }
    if (image->outputs) {
        ecat_eni_free_pi_output(image->outputs);
    }
    ecat_free(image);
    image = NULL;
}
