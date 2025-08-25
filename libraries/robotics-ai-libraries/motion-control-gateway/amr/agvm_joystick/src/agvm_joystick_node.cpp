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

#include <rclcpp/rclcpp.hpp>
#include <geometry_msgs/msg/twist.hpp>
#include <std_msgs/msg/bool.hpp>
#include <tf2_ros/buffer_interface.h>
#include <tf2/time.h>
#include <string>
#include <functional>
#include <chrono>
#include <linux/joystick.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <signal.h>
#include <unistd.h>

static std::string gs_devpath;
static double gs_maxlinvel;
static double gs_maxrotvel;
static double gs_safevelrate;
static int gs_devfd;
static rclcpp::Node* gs_jsNode;

static bool devInit(void)
{
    gs_devfd = open(gs_devpath.c_str(), O_RDONLY);
    if(gs_devfd < 0) {
        RCLCPP_ERROR(gs_jsNode->get_logger(), "Cannot open %s %d!", gs_devpath.c_str(), gs_devfd);
        return false;
    }
    
    return true;
}

static bool processJSEvent(
    struct js_event* event, 
    bool* emerg, 
    bool* emergChanged,
    bool* turboMode, 
    double* transV, 
    double* transH, 
    double* twist)
{
    if(read(gs_devfd, event, sizeof(struct js_event)) < 0) {
        //RCLCPP_ERROR(gs_jsNode->get_logger(), "read value failed!");
        return false;
    }
    
    //RCLCPP_ERROR(gs_jsNode->get_logger(), "%d %d %d", event->type, event->number, event->value);
    if(event->type == JS_EVENT_AXIS) {
        switch(event->number) {
            case 0: //左水平摇杆，左右移动用
                *transH = -event->value / 32767.0;
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
            case 1: //右摇杆向右，顺时针旋转
                if(event->value) {
                    *twist = -1.0;
				}
                else{
                    *twist = 0.0;
                }
                break;
            case 3: //右摇杆向左，逆时针旋转
                if(event->value) {
                    *twist = 1.0;
				}
                else{
                    *twist = 0.0;
                }
                break;            
            case 7: //R2键，退出急停用
                if(event->value) {
                    *emerg = false;
                    *emergChanged = true;
				}
                break;
            case 5: //R1键，急停用
                if(event->value) {
                    *emerg = true;
                    *emergChanged = true;
				}
                break;
            case 4: //L1键，按住全速
                *turboMode = !!event->value;
                break;
        }
    }
        
    return true;
}

static void exitHandler(int sig)
{
	(void)sig;
	rclcpp::shutdown();
	close(gs_devfd);
    exit(0);
}

int main(int argc, char * argv[])
{
    rclcpp::init(argc, argv);
    gs_jsNode = new rclcpp::Node("agvm_joystick_node");
    
    gs_devpath = gs_jsNode->declare_parameter("agvm_joystick_devpath", "/dev/input/js0");
    
    gs_maxlinvel = gs_jsNode->declare_parameter("agvm_joystick_maxlinvel", 0.5);
    
    gs_maxrotvel = gs_jsNode->declare_parameter("agvm_joystick_maxrotvel", 2.0);
    
    gs_safevelrate = gs_jsNode->declare_parameter("agvm_joystick_safevelrate", 0.3);
    
    auto cmdVelPub = gs_jsNode->create_publisher<geometry_msgs::msg::Twist>(
		"/cmd_vel", rclcpp::SystemDefaultsQoS());
    
    auto emergPub = gs_jsNode->create_publisher<std_msgs::msg::Bool>(
		"/agvm_plcshm/emergstop", rclcpp::SystemDefaultsQoS());
		
    //signal(SIGINT, exitHandler);
    
    //rclcpp::spin(gs_jsNode->get_node_base_interface());
    
    struct js_event e;
    bool emerg = false;
    bool turboMode = false;
    double transV = 0;
    double transH = 0;
    double twist = 0;
    geometry_msgs::msg::Twist cmdVelMsg;
    std_msgs::msg::Bool emergMsg;
    
START:
	if(!rclcpp::ok()) {
		goto EXIT;
	}
	
    if(!devInit()) {
        rclcpp::sleep_for(std::chrono::seconds(2));
        goto START;
    }
    
    while(rclcpp::ok()) {
		bool emergChanged = false;
        if(!processJSEvent(&e, &emerg, &emergChanged, &turboMode, &transV, &transH, &twist)) {
            close(gs_devfd);
            goto START;
        }
        
        if(!emerg) {
            cmdVelMsg.linear.x = transV * gs_maxlinvel;
            cmdVelMsg.linear.y = transH * gs_maxlinvel;
            cmdVelMsg.angular.z = twist * gs_maxrotvel;
            if(!turboMode) {
                cmdVelMsg.linear.x *= gs_safevelrate;
                cmdVelMsg.linear.y *= gs_safevelrate;
                cmdVelMsg.angular.z *= gs_safevelrate;
            }
        } else {
            cmdVelMsg.linear.x = 0;
            cmdVelMsg.linear.y = 0;
            cmdVelMsg.angular.z = 0;
        }
        
        //RCLCPP_DEBUG(gs_jsNode->get_logger(), "%d %lf %lf %lf", emerg, cmdVelMsg.linear.y, cmdVelMsg.linear.x, cmdVelMsg.angular.z);
        cmdVelPub->publish(cmdVelMsg);
        
        if(emergChanged) {
			emergMsg.data = emerg;
			emergPub->publish(emergMsg);
		}
    }
    
EXIT:
    rclcpp::shutdown();
    delete gs_jsNode;
    return 0;
}
