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

#ifndef __ETHERCAT_6AIXS_MAIN_H__
#define __ETHERCAT_6AIXS_MAIN_H__

#include <stdio.h>
#include "ecrt.h"
#include "def_config.h"

#define CYCLE_US                250
#define PERIOD_NS               (CYCLE_US*1000)
#define NSEC_PER_SEC            (1000000000L)
#define TIMESPEC2NS(T)          ((uint64_t) (T).tv_sec * NSEC_PER_SEC + (T).tv_nsec)
#define DIFF_NS(A,B)            (((B).tv_sec - (A).tv_sec)*NSEC_PER_SEC + ((B).tv_nsec)-(A).tv_nsec)
#define CYCLE_COUNTER_PERSEC    (NSEC_PER_SEC/PERIOD_NS)

#define MAX_DECODER_COUNT        0x100000
#define MAX_VELOCITY_MOTOR        0x66665f92
#define SERVO_AXIS_SIZE            20.0

#if defined(MOTOR_8AXIS) || defined(MOTOR_2AXIS)
#define IS620N_Slave00_Pos      0, 0
#define IS620N_Slave01_Pos      0, 1
#endif
#if defined(MOTOR_8AXIS)
#define IS620N_Slave02_Pos      0, 2
#define IS620N_Slave03_Pos      0, 3
#define IS620N_Slave04_Pos      0, 4
#define IS620N_Slave05_Pos      0, 5
#define IS620N_Slave06_Pos      0, 6
#define IS620N_Slave07_Pos      0, 7
#endif
#if defined(MOTOR_6AXIS)
#define IS620N_Slave02_Pos      0, 0
#define IS620N_Slave03_Pos      0, 1
#define IS620N_Slave04_Pos      0, 2
#define IS620N_Slave05_Pos      0, 3
#define IS620N_Slave06_Pos      0, 4
#define IS620N_Slave07_Pos      0, 5
#endif


enum{
    MOTOR_START = 0,
    MOTOR_RUN,
    MOTOR_STOP
};

typedef enum{
    GO_HOME = 0,
    GO_MINIMUM,
    GO_HOME_FINISH
}go_home_t;

typedef struct{
    ec_slave_config_t *sc;
    unsigned int ctrl_word;
    unsigned int mode_sel;
    unsigned int tar_pos;
    unsigned int touch_probe_func;
    unsigned int error_code;
    unsigned int status_word;
    unsigned int mode_display;
    unsigned int pos_act;
    unsigned int touch_probe_status;
    unsigned int touch_probe1_pos;
    unsigned int touch_probe2_pos;
    unsigned int digital_input;
    unsigned int mode_cw;
    unsigned int vel_act;
    unsigned int err_pos;
}Slave_Data;

typedef struct{
    unsigned short statusword;
    unsigned short controlword;
    unsigned long prevpos;
    unsigned long actualpos;
    unsigned long targetpos;
    unsigned short cwmode;
    unsigned int leftinput;
    unsigned int homeinput;
    unsigned int rightinput;
    signed char selmode;
    signed int actualvel;
    signed int errpos;
    go_home_t gohome_history;
    signed int zeroposition;
    signed int minposition;
    signed int maxposition;
}Ctl_Data;


#endif

