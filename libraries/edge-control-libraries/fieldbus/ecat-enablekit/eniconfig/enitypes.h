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
 * @file enitypes.h
 * 
 */

#ifndef __ENI_TYPES_H__
#define __ENI_TYPES_H__

#include "enicommon.h"

typedef struct {
    int32_t cmd;
    int32_t ado;
    int32_t addr;
    int32_t data;
    int32_t data_len;
}eni_ecat_cmd_type;

typedef struct {
    struct list_head initcmd_list;
    eni_ecat_cmd_type ecat_cmd_type;
}eni_initcmd;

typedef struct {
    uint8_t *name;
    uint8_t *comment;
    uint8_t *data_type;
    int32_t bit_size;
    int32_t bit_offs;
}eni_variable_type;

typedef struct {
    uint8_t* name;
} eni_name_type;

typedef struct {
    struct list_head list;
    uint32_t index;
    uint32_t subindex;
    uint32_t bitlen;
    eni_name_type name;
} eni_entry_type;

typedef struct {
    uint16_t index;
    eni_name_type name;
    struct list_head entry_list;
    uint8_t fixed;
    uint8_t mandatory;
    uint8_t sm;
} eni_pdo_type;

#define ENI_TRANSITION_IP_TYPE         (1<<0) //Init -> Pre-Operation
#define ENI_TRANSITION_PS_TYPE         (1<<1) //Pre-Operation -> Safe-Operational
#define ENI_TRANSITION_PI_TYPE         (1<<2) //Pre-Operation -> Init
#define ENI_TRANSITION_SP_TYPE         (1<<3) //Safe-Operational -> Pre-Operation
#define ENI_TRANSITION_SO_TYPE         (1<<4) //Safe-Operation -> Operational
#define ENI_TRANSITION_SI_TYPE         (1<<5) //Safe-Operation -> Init
#define ENI_TRANSITION_OS_TYPE         (1<<6) //Operation -> Safe-Operational
#define ENI_TRANSITION_OP_TYPE         (1<<7) //Operation -> Pre-Operational
#define ENI_TRANSITION_OI_TYPE         (1<<8) //Operation -> Init
#define ENI_TRANSITION_IB_TYPE         (1<<9) //Init -> Bootstrap
#define ENI_TRANSITION_BI_TYPE         (1<<10) //Bootstrap -> Init
#define ENI_TRANSITION_II_TYPE         (1<<11) //Init -> Init
#define ENI_TRANSITION_PP_TYPE         (1<<12) //Pre-Operation -> Pre-Operational
#define ENI_TRANSITION_SS_TYPE         (1<<13) //Safe-Operation -> Safe-Operational
#define ENI_TRANSITION_MASK_TYPE        (0x3FFF)
typedef struct {
    uint16_t type;
} eni_transitionType;

void ecat_eni_parse_ecatcmdtype(xmlNodePtr ptr, eni_ecat_cmd_type* cmd_type);

void ecat_eni_parse_initcmd(xmlNodePtr ptr, struct list_head* list);

void ecat_eni_parse_variabletype(xmlNodePtr ptr, eni_variable_type* type);
void ecat_eni_parse_transitionType(xmlNodePtr ptr, eni_transitionType* transition);
#endif

