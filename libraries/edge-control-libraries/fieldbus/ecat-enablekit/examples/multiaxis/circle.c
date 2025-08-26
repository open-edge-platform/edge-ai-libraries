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

#include <stdlib.h>
#include <stdio.h>
#include <math.h>
#include "circle.h"
#include "def_config.h"

#define Per_Circle  (2*3.1415926)

static double getLenBetweenAxis(axis_pos a, axis_pos b)
{
    double diff1,diff2;
    diff1 = a.x-b.x;
    diff2 = a.y-b.y;
    return sqrt(diff1*diff1+diff2*diff2);
}

void circle_init(circle_prop* prop)
{
    double diff,len;
    len = getLenBetweenAxis(prop->servo_pos1, prop->servo_pos2);
    if(prop->servo_len1 > prop->servo_len2){
        diff = (prop->servo_len1*prop->servo_len1 - prop->servo_len2*prop->servo_len2)/len;
        prop->current_pos.x = (len+diff)/2 + prop->servo_pos1.x;
        prop->current_pos.y = prop->servo_pos1.y - sqrt(prop->servo_len1*prop->servo_len1-(len+diff)*(len+diff)/4);
    }else{
        diff = (prop->servo_len2*prop->servo_len2 - prop->servo_len1*prop->servo_len1)/len;
        prop->current_pos.x = prop->servo_pos2.x - (len+diff)/2;
        prop->current_pos.y = prop->servo_pos2.y - sqrt(prop->servo_len2*prop->servo_len2-(len+diff)*(len+diff)/4);
    }
    prop->center_pos.x = prop->current_pos.x + prop->circle_radius;
    prop->center_pos.y = prop->current_pos.y;
    prop->current_angle = 0.0000;
}

void circle_CurPosAdjust(circle_prop* prop, double a_len, double b_len, int* position_x, int* position_y)
{
	double diff,len;
	float2int data_x,data_y;
	len = getLenBetweenAxis(prop->servo_pos1, prop->servo_pos2);
	if(a_len > b_len){
		diff = (a_len*a_len-b_len*b_len)/len;
		prop->current_pos.x = (len+diff)/2 + prop->servo_pos1.x;
		prop->current_pos.y = prop->servo_pos1.y - sqrt(a_len*a_len-(len+diff)*(len+diff)/4);
	}else{
		diff = (b_len*b_len-a_len*a_len)/len;
		prop->current_pos.x = prop->servo_pos2.x - (len+diff)/2;
		prop->current_pos.y = prop->servo_pos2.y - sqrt(b_len*b_len-(len+diff)*(len+diff)/4);
	}
	data_x.f = prop->current_pos.x;
	data_y.f = prop->current_pos.y;
	*position_x = data_x.i;
	*position_y = data_y.i;
}

void circle_TargetByStep(circle_prop* prop, double step, double* a_len, double* b_len)
{
	double target_angle;
	axis_pos target_pos;
	target_angle = prop->current_angle+step;
	target_pos.x = prop->center_pos.x - prop->circle_radius * cos(target_angle);
	target_pos.y = prop->center_pos.y + prop->circle_radius * sin(target_angle);
	*a_len = getLenBetweenAxis(target_pos, prop->servo_pos1);
	*b_len = getLenBetweenAxis(target_pos, prop->servo_pos2);
	prop->current_angle += step;
	if (prop->current_angle >= Per_Circle)
		prop->current_angle -= Per_Circle;
}

