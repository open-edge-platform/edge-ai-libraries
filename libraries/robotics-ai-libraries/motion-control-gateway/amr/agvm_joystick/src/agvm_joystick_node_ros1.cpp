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

#include <ros/ros.h>
#include <geometry_msgs/Twist.h>
#include <std_msgs/Bool.h>
#include <string>
#include <linux/joystick.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <signal.h>

static std::string gs_devpath;
static double gs_maxlinvel;
static double gs_maxrotvel;
static double gs_safevelrate;
static int gs_devfd;

static bool devInit(void)
{
    gs_devfd = open(gs_devpath.c_str(), O_RDONLY);
    if(gs_devfd < 0) {
        ROS_ERROR("Cannot open %s %d!\n", gs_devpath.c_str(), gs_devfd);
        return false;
    }
    
    return true;
}

static bool processJSEvent(
    struct js_event* event, 
    bool* enable, 
    bool* turboMode, 
    double* transV, 
    double* transH, 
    double* twist)
{
    if(read(gs_devfd, event, sizeof(struct js_event)) < 0) {
        ROS_ERROR("read value failed!\n");
        return false;
    }
    
    ROS_DEBUG("%d %d %d\n", event->type, event->number, event->value);
    if(event->type == JS_EVENT_AXIS) {
        switch(event->number) {
            case 0: //左水平摇杆，左右移动用
                *transH = event->value / 32767.0;
                break;
            case 1: //左垂直摇杆，前后移动用
                *transV = -event->value / 32767.0;
                break;
            case 2: //右水平摇杆，旋转用
                *twist = -event->value / 32767.0;
                break;
        }
    } else if(event->type == JS_EVENT_BUTTON) {
        switch(event->number) {
            case 0: //A键，使能用
                if(event->value)
                    *enable = true;
                break;
            case 3: //X键，急停用
                if(event->value)
                    *enable = false;
                break;
            case 6: //L1键，按住全速
                *turboMode = !!event->value;
                break;
        }
    }
        
    return true;
}

static void exitHandler(int sig)
{
	ros::shutdown();
    exit(0);
}

int main(int argc, char * argv[])
{
    ros::init(argc, argv, "agvm_joystick_node");
    ros::NodeHandle nh("~");
    nh.param("agvm_joystick_devpath", gs_devpath, std::string("/dev/input/js0"));
    nh.param("agvm_joystick_maxlinvel", gs_maxlinvel, 0.5);
    nh.param("agvm_joystick_maxrotvel", gs_maxrotvel, 2.0);
    nh.param("agvm_joystick_safevelrate", gs_safevelrate, 0.3);
    
    signal(SIGINT, exitHandler);
    
    ros::Publisher cmdVelPub = nh.advertise<geometry_msgs::Twist>("/cmd_vel", 2);
    ros::Publisher enablePub = nh.advertise<std_msgs::Bool>("/agvm_enable", 1);
    
    struct js_event e;
    bool enable0 = false;
    bool turboMode = false;
    double transV = 0;
    double transH = 0;
    double twist = 0;
    geometry_msgs::Twist cmdVel;
    std_msgs::Bool enable;
    
START:
    if(!devInit()) {
        if(!ros::ok())
            return -1;
        ros::Duration(3).sleep();
        goto START;
    }
    
    while(ros::ok()) {
        if(!processJSEvent(&e, &enable0, &turboMode, &transV, &transH, &twist)) {
            close(gs_devfd);
            ros::Duration(2).sleep();
            goto START;
        }
        
        enable.data = enable0;
        if(enable0) {
            cmdVel.linear.x = transV * gs_maxlinvel;
            cmdVel.linear.y = transH * gs_maxlinvel;
            cmdVel.angular.z = twist * gs_maxrotvel;
            if(!turboMode) {
                cmdVel.linear.x *= gs_safevelrate;
                cmdVel.linear.y *= gs_safevelrate;
                cmdVel.angular.z *= gs_safevelrate;
            }
        } else {
            cmdVel.linear.x = 0;
            cmdVel.linear.y = 0;
            cmdVel.angular.z = 0;
        }
        
        //ROS_DEBUG("%d %lf %lf %lf\n", enable0, cmdVel.linear.y, cmdVel.linear.x, cmdVel.angular.z);
        cmdVelPub.publish(cmdVel);
        enablePub.publish(enable);
    }
    
    return 0;
}
