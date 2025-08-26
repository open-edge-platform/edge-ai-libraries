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

#ifndef __CIRCLE_ALOG_H__
#define __CIRCLE_ALOG_H__

typedef union{
    float f;
    int i;
} float2int;

typedef struct {
    double x;
    double y;
} axis_pos;

typedef struct {
    axis_pos servo_pos1;
    axis_pos servo_pos2;
    double servo_len1;
    double servo_len2;
    unsigned long circle_radius;
	axis_pos center_pos;
	axis_pos current_pos;
	double current_angle;
} circle_prop;

void circle_init(circle_prop *prop);
void circle_CurPosAdjust(circle_prop *prop, double a_len, double b_len, int* position_x, int* position_y);
void circle_TargetByStep(circle_prop *prop, double step, double* a_len, double* b_len);

#endif

