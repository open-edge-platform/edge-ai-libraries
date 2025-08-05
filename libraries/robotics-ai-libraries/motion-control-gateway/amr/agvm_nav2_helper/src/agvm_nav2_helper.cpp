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
#include <rclcpp/client.hpp>
#include <std_srvs/srv/empty.hpp>
#include <std_msgs/msg/bool.hpp>
#include <std_msgs/msg/int32.hpp>
#include <geometry_msgs/msg/pose_with_covariance_stamped.hpp>
#include <tf2_ros/transform_listener.h>
#include <tf2_ros/buffer_interface.h>
#include <tf2/time.h>
#include <tf2/LinearMath/Quaternion.h>
#include <tf2_eigen/tf2_eigen.h>
#include <string>
#include <functional>
#include <chrono>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>

class AgvmNav2Helper : public rclcpp::Node
{
class AgvmAmclSrvCaller : public rclcpp::Node
{
public:
	AgvmAmclSrvCaller();
	void callSrv(void);
	
	rclcpp::Client<std_srvs::srv::Empty>::SharedPtr request_nonmotion_update_client_;
};
	
public:
    AgvmNav2Helper();
    void getParameters(void);
    void init(void);
    
private:
	void setMapPose(void);
	void navGoalCallback(const geometry_msgs::msg::PoseStamped::SharedPtr goal);
	void initPoseCallback(const geometry_msgs::msg::PoseWithCovarianceStamped::SharedPtr pose);
	void agvmErrorCallback(const std_msgs::msg::Bool::SharedPtr error);
	void agvmMoveBusyCallback(const std_msgs::msg::Bool::SharedPtr busy);
	void navStatCallback(const std_msgs::msg::Int32::SharedPtr stat);
	
	void agvmEmergStop(bool emerg);

	std::shared_ptr<AgvmAmclSrvCaller> srv_caller_;
	std::mutex srv_caller_mutex_;
	std::thread* srv_caller_thread_ = nullptr;
	geometry_msgs::msg::PoseStamped last_goal_;
	std::string map_frame_;
	std::string base_frame_;
	
	rclcpp::Publisher<geometry_msgs::msg::Pose>::SharedPtr agvm_rel_pose_pub_;
	rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr emerg_pub_;
	//rclcpp::Publisher<geometry_msgs::msg::PoseWithCovarianceStamped>::SharedPtr init_pose_pub_;
	rclcpp::Publisher<std_msgs::msg::Int32>::SharedPtr nav_stat_pub_;
	rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr nav_cancel_pub_;
	
	rclcpp::Subscription<geometry_msgs::msg::PoseStamped>::SharedPtr nav_goal_sub_;
	rclcpp::Subscription<geometry_msgs::msg::PoseWithCovarianceStamped>::SharedPtr init_pose_sub_;
	rclcpp::Subscription<std_msgs::msg::Int32>::SharedPtr nav_stat_sub_; //modify src of bt_navigator to achieve this feature
	rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr error_sub_;
	rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr move_busy_sub_;
	
	std::shared_ptr<tf2_ros::TransformListener> tf_listener_;
	std::shared_ptr<tf2_ros::Buffer> buffer_;
	bool agvm_error_ = true;
	bool agvm_move_busy_ = false;
};

AgvmNav2Helper::AgvmAmclSrvCaller::AgvmAmclSrvCaller() : 
    rclcpp::Node("agvm_amcl_srv_caller")
{
    request_nonmotion_update_client_ = 
		create_client<std_srvs::srv::Empty>("/request_nomotion_update");
}

void AgvmNav2Helper::AgvmAmclSrvCaller::callSrv()
{
	auto request = std::make_shared<std_srvs::srv::Empty::Request>();
	auto node = get_node_base_interface();
	if(!request_nonmotion_update_client_->wait_for_service(std::chrono::seconds(8))) {
		RCLCPP_ERROR(get_logger(), "wait service /request_nomotion_update timeout");
	}
	
	for(int i=0; i<20; ++i) {
		auto result_future = request_nonmotion_update_client_->async_send_request(request);
		
		if(rclcpp::spin_until_future_complete(node, result_future) !=
			rclcpp::executor::FutureReturnCode::SUCCESS) {
			RCLCPP_ERROR(get_logger(), "service call failed :(");
			return;
		}
		
		rclcpp::sleep_for(std::chrono::milliseconds(300));
	}
}

AgvmNav2Helper::AgvmNav2Helper() : 
    rclcpp::Node("agvm_nav2_helper")
{
    getParameters();
    init();
}

void AgvmNav2Helper::getParameters(void)
{
    base_frame_ = declare_parameter("base_frame", "base_link");
}

void AgvmNav2Helper::init(void)
{
	RCLCPP_ERROR(get_logger(), "init");
	
	srv_caller_ = std::make_shared<AgvmAmclSrvCaller>();
	
    agvm_rel_pose_pub_ = create_publisher<geometry_msgs::msg::Pose>(
        "/agvm_plcshm/move_relative", 
        rclcpp::SystemDefaultsQoS());
        
    emerg_pub_ = create_publisher<std_msgs::msg::Bool>(
        "/agvm_plcshm/emergstop", rclcpp::SystemDefaultsQoS());
        /*
    init_pose_pub_ = create_publisher<geometry_msgs::msg::PoseWithCovarianceStamped>(
        "/initialpose", 
        rclcpp::SystemDefaultsQoS());
        */
    nav_cancel_pub_ = create_publisher<std_msgs::msg::Bool>(
        "/move_base_simple/cancel", 
        rclcpp::SystemDefaultsQoS());
        
    nav_stat_pub_ = create_publisher<std_msgs::msg::Int32>(
        "/move_base_simple/nav_status", 
        rclcpp::SystemDefaultsQoS());
        
    nav_stat_sub_ = create_subscription<std_msgs::msg::Int32>(
        "/move_base_simple/nav_status", 
        rclcpp::SystemDefaultsQoS(), 
        std::bind(&AgvmNav2Helper::navStatCallback, this, std::placeholders::_1));
        
    nav_goal_sub_ = create_subscription<geometry_msgs::msg::PoseStamped>(
        "/move_base_simple/goal", 
        rclcpp::SystemDefaultsQoS(), 
        std::bind(&AgvmNav2Helper::navGoalCallback, this, std::placeholders::_1));
        
    init_pose_sub_ = create_subscription<geometry_msgs::msg::PoseWithCovarianceStamped>(
        "/initialpose", 
        rclcpp::SystemDefaultsQoS(), 
        std::bind(&AgvmNav2Helper::initPoseCallback, this, std::placeholders::_1));
        
    error_sub_ = create_subscription<std_msgs::msg::Bool>(
        "/agvm_plcshm/error", 
        rclcpp::SystemDefaultsQoS(), 
        std::bind(&AgvmNav2Helper::agvmErrorCallback, this, std::placeholders::_1));
        
    move_busy_sub_ = create_subscription<std_msgs::msg::Bool>(
        "/agvm_plcshm/move_relative_busy", 
        rclcpp::SystemDefaultsQoS(), 
        std::bind(&AgvmNav2Helper::agvmMoveBusyCallback, this, std::placeholders::_1));
        
    buffer_ = buffer_ = std::make_shared<tf2_ros::Buffer>(get_clock());
	tf_listener_ = std::make_shared<tf2_ros::TransformListener>(*buffer_, this, false);
}

void AgvmNav2Helper::navGoalCallback(const geometry_msgs::msg::PoseStamped::SharedPtr goal)
{
	agvmEmergStop(false);
	last_goal_ = *goal;
}

void AgvmNav2Helper::initPoseCallback(const geometry_msgs::msg::PoseWithCovarianceStamped::SharedPtr pose)
{
	(void)pose;
	
	srv_caller_mutex_.lock();
	if(srv_caller_thread_) {
		delete srv_caller_thread_;
		srv_caller_thread_ = nullptr;
	}
	srv_caller_mutex_.unlock();
	
	srv_caller_thread_ = new std::thread(&AgvmNav2Helper::AgvmAmclSrvCaller::callSrv, srv_caller_.get());
	srv_caller_thread_->join();
	
	srv_caller_mutex_.lock();
	if(srv_caller_thread_) {
		delete srv_caller_thread_;
		srv_caller_thread_ = nullptr;
	}
	srv_caller_mutex_.unlock();
}

void AgvmNav2Helper::agvmErrorCallback(const std_msgs::msg::Bool::SharedPtr error)
{
	if(error->data && !agvm_error_) {
		nav_cancel_pub_->publish(std_msgs::msg::Bool());
	}
	
	agvm_error_ = error->data;
}

void AgvmNav2Helper::agvmMoveBusyCallback(const std_msgs::msg::Bool::SharedPtr busy)
{
	if(!busy->data && agvm_move_busy_) {
		rclcpp::sleep_for(std::chrono::seconds(1)); //wait 1s let agv stops stably
		agvmEmergStop(true);
		std_msgs::msg::Int32 nav_stat_msg;
		nav_stat_msg.data = 2;
		nav_stat_pub_->publish(nav_stat_msg);
	}
	
	agvm_move_busy_ = busy->data;
}
	
void AgvmNav2Helper::navStatCallback(const std_msgs::msg::Int32::SharedPtr stat)
{
	if(stat->data == 1) {
		setMapPose();
	} else if(stat->data == -1) {
		agvmEmergStop(true);
	}
}

void AgvmNav2Helper::agvmEmergStop(bool emerg)
{
	if(agvm_error_ != emerg) {
		std_msgs::msg::Bool emerg_msg;
		emerg_msg.data = emerg;
		emerg_pub_->publish(emerg_msg);
	}
}

void AgvmNav2Helper::setMapPose(void)
{
    Eigen::Isometry3d pose;
    pose.setIdentity();
    pose.rotate(Eigen::Quaterniond(
		last_goal_.pose.orientation.w,
		last_goal_.pose.orientation.x,
		last_goal_.pose.orientation.y,
		last_goal_.pose.orientation.z));
		
	pose.pretranslate(Eigen::Vector3d(
		last_goal_.pose.position.x,
		last_goal_.pose.position.y,
		last_goal_.pose.position.z));
    
    Eigen::Isometry3d transMapBase;
    try {
		transMapBase = tf2::transformToEigen(buffer_->lookupTransform(
			last_goal_.header.frame_id, 
			base_frame_, 
			tf2::TimePointZero,
			tf2::durationFromSec(1)));
	} catch (tf2::TransformException & e) {
		RCLCPP_WARN(get_logger(), "%s", e.what());
		return;
	}
	
	Eigen::Isometry3d poseDiff = transMapBase.inverse() * pose;
	Eigen::Vector3d poseDiff_T(poseDiff.translation());
	Eigen::Quaterniond poseDiff_Q(poseDiff.rotation());
	geometry_msgs::msg::Pose poseMsg;
	poseMsg.position.x = poseDiff_T[0];
	poseMsg.position.y = poseDiff_T[1];
	poseMsg.position.z = poseDiff_T[2];
	poseMsg.orientation.x = poseDiff_Q.x();
	poseMsg.orientation.y = poseDiff_Q.y();
	poseMsg.orientation.z = poseDiff_Q.z();
	poseMsg.orientation.w = poseDiff_Q.w();
	agvm_rel_pose_pub_->publish(poseMsg);
}

int main(int argc, char * argv[]) 
{
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<AgvmNav2Helper>());
    rclcpp::shutdown();
    return 0;
}
