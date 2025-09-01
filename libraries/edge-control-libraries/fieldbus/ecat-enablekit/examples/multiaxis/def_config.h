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

#ifndef __ETHERCAT_CONFIG_H__
#define __ETHERCAT_CONFIG_H__

//#define DEBUG_CONSOLE_FS

#define MEASURE_TIMING 
#define SHARE_MEM
#define MOTOR_CONTROL

//#define MOTOR_8AXIS
#define MOTOR_6AXIS
//#define MOTOR_2AXIS

#if defined(MOTOR_2AXIS)
    #define NUM_AXIS 2
#endif

#if defined(MOTOR_6AXIS)
    #define NUM_AXIS 6
#endif

#if defined(MOTOR_8AXIS)
    #define AXIS_OFFSET 2
    #define NUM_AXIS 8
#else 
    #define AXIS_OFFSET 0
#endif

#if (defined(MOTOR_8AXIS) && defined(MOTOR_6AXIS)) || \
    (defined(MOTOR_8AXIS) && defined(MOTOR_2AXIS)) || \
    (defined(MOTOR_6AXIS) && defined(MOTOR_2AXIS))
#error "MOTOR_*AXIS macro have multiply definition, only one is supported!"
#endif

#endif

