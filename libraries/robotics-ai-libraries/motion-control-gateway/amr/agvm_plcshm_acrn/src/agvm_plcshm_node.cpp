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
#include <nav_msgs/msg/odometry.hpp>
#include <tf2_ros/transform_broadcaster.h>
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
#include <assert.h>
#include <bits/stdc++.h>
#ifdef ENABLE_SHM_RINGBUF
#include <shmringbuf.h>
#endif
#ifdef ENABLE_SHM_ACRN
#include "agvm_plcshm_acrn/acrn_shm.hpp"
#endif

static const rclcpp::Logger LOGGER = rclcpp::get_logger("agvm_plcshm_node");

/* Shm related data types
 * s_buf, handle_s: data sent from RT domain, AMR state info
 * c_buf, handle_c: data sent to RT domain, AMR commands
 */
#define MSG_LEN 512
static char s_buf[MSG_LEN];
static char c_buf[MSG_LEN];
#ifdef ENABLE_SHM_RINGBUF
static shm_handle_t handle_s, handle_c;
#endif

typedef struct
{
    uint8_t mEnable;
    uint8_t mEmergStop;
    float mTransH;
    float mTransV;
    float mTwist;
    uint8_t mRelMove;
    uint8_t mCancelRelMove;
    float mRelX;
    float mRelY;
    float mRelRZ;
}PLCShmCtrlType;

typedef struct
{
    float mPosX;
    float mPosY;
    float mPosRZ;
    float mVelX;
    float mVelY;
    float mVelRZ;
    uint8_t mError;
    uint8_t mRelMoveBusy;
}PLCShmAgvmInfoType;

static PLCShmCtrlType* ctrl;
static PLCShmAgvmInfoType* agvmInfo;

class AgvmPlcShmNode : public rclcpp::Node
{
public:
    AgvmPlcShmNode();
    ~AgvmPlcShmNode()
    {
        delete ctrl;
        delete agvmInfo;
    }
    void getParameters(void);
    void init(void);

private:
    void cmdVelCallback(const geometry_msgs::msg::Twist::SharedPtr cmdVel);
    void agvmEmergCallback(const std_msgs::msg::Bool::SharedPtr enable);
    void relPoseCallback(const geometry_msgs::msg::Pose::SharedPtr pose);
    void timerCallback(void);
    
private:
    int mCtrlAddr;
    int mAgvmInfoAddr;
    int mPubRate;
    bool mEnableAcrnShm = true;
    std::string mOdomFrame;
    std::string mBaseFrame;
    double mPosRZPriv = 0;
    nav_msgs::msg::Odometry mOdom;
    int mFreqDivider = 0;
    std_msgs::msg::Bool mServoError;
    std_msgs::msg::Bool mRelMoveBusy;
    
    rclcpp::Subscription<geometry_msgs::msg::Twist>::SharedPtr mCmdVelSub;
    rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr mAgvmEmergSub;
    rclcpp::Subscription<geometry_msgs::msg::Pose>::SharedPtr mRelPoseSub;

    rclcpp::Publisher<nav_msgs::msg::Odometry>::SharedPtr mAgvmOdomPub;
    rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr mServoErrorPub;
    rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr mRelMoveBusyPub;
    rclcpp::TimerBase::SharedPtr mTimer;
    std::shared_ptr<tf2_ros::TransformBroadcaster> mTFBroadcaster;

#ifdef ENABLE_SHM_ACRN
    std::shared_ptr<cross_vm_messenger::AcrnSharedMemory> acrn_shm_;
#endif // ENABLE_SHM_ACRN
};

AgvmPlcShmNode::AgvmPlcShmNode() : 
    rclcpp::Node("agvm_plcshm_node")
{
    getParameters();
    init();
#ifdef ENABLE_SHM_ACRN
    if(mEnableAcrnShm) {
      acrn_shm_ = std::make_shared<cross_vm_messenger::AcrnSharedMemory>(0, 8192);
      acrn_shm_->assign("amr_state", MSG_LEN);
      acrn_shm_->assign("amr_cmd", MSG_LEN);
    }
#endif
}

void AgvmPlcShmNode::getParameters(void)
{
    declare_parameter("agvm_plcshm_publish_rate", 100);
    get_parameter("agvm_plcshm_publish_rate", mPubRate);

    declare_parameter("agvm_odom_frame", "odom");
    get_parameter("agvm_odom_frame", mOdomFrame);

    declare_parameter("agvm_base_frame", "base_footprint");
    get_parameter("agvm_base_frame", mBaseFrame);

    declare_parameter("enable_acrn_shm", true);
    get_parameter("enable_acrn_shm", mEnableAcrnShm);
}

void AgvmPlcShmNode::init(void)
{
    using namespace std::placeholders;

    ctrl = new PLCShmCtrlType();
    agvmInfo = new PLCShmAgvmInfoType();
    
    mTFBroadcaster = std::make_shared<tf2_ros::TransformBroadcaster>(this);
    
    mCmdVelSub = create_subscription<geometry_msgs::msg::Twist>(
        "/cmd_vel", rclcpp::SystemDefaultsQoS(), 
        std::bind(&AgvmPlcShmNode::cmdVelCallback, this, _1));
        
    mAgvmEmergSub = create_subscription<std_msgs::msg::Bool>(
        "/agvm_plcshm/emergstop", rclcpp::SystemDefaultsQoS(), 
        std::bind(&AgvmPlcShmNode::agvmEmergCallback, this, _1));

    mRelPoseSub = create_subscription<geometry_msgs::msg::Pose>(
        "/agvm_plcshm/move_relative", rclcpp::SystemDefaultsQoS(), 
        std::bind(&AgvmPlcShmNode::relPoseCallback, this, _1));
        
    mAgvmOdomPub = create_publisher<nav_msgs::msg::Odometry>(
        "/odom", rclcpp::SystemDefaultsQoS());

    mServoErrorPub = create_publisher<std_msgs::msg::Bool>(
        "/agvm_plcshm/error", rclcpp::SystemDefaultsQoS());
        
    mRelMoveBusyPub = create_publisher<std_msgs::msg::Bool>(
        "/agvm_plcshm/move_relative_busy", rclcpp::SystemDefaultsQoS());
        
    mTimer = create_wall_timer(
        std::chrono::nanoseconds((int64_t)(1000000000.0 / mPubRate)), 
        std::bind(&AgvmPlcShmNode::timerCallback, this));

    RCLCPP_INFO(get_logger(), "AgvmPlcShmNode initial complete.");
}

void AgvmPlcShmNode::cmdVelCallback(const geometry_msgs::msg::Twist::SharedPtr cmdVel)
{
    RCLCPP_INFO(get_logger(), "Get cmdVel: %f %f %f\n", cmdVel->linear.x, cmdVel->linear.y, cmdVel->angular.z);
    ctrl->mTransH = cmdVel->linear.y;
    ctrl->mTransV = cmdVel->linear.x;
    ctrl->mTwist = cmdVel->angular.z;
}

void AgvmPlcShmNode::agvmEmergCallback(const std_msgs::msg::Bool::SharedPtr enable)
{
    ctrl->mEmergStop = enable->data;
    ctrl->mEnable = !enable->data;
    RCLCPP_INFO(get_logger(), "Enable AGV: %d\n", ctrl->mEnable);
}

void AgvmPlcShmNode::relPoseCallback(const geometry_msgs::msg::Pose::SharedPtr pose)
{
	ctrl->mRelX = pose->position.x;
	ctrl->mRelY = pose->position.y;
	Eigen::AngleAxisd tmpRot(Eigen::Quaterniond(
		pose->orientation.w,
		pose->orientation.x,
		pose->orientation.y,
		pose->orientation.z));
	
	//trust it sends a legal quat that rot axis is Z-Axis
	ctrl->mRelRZ = tmpRot.angle();
	
	if(tmpRot.axis()[2] < 0) { //CW
		ctrl->mRelRZ = -ctrl->mRelRZ;
	}
	
	RCLCPP_INFO(get_logger(), 
		"set relative pose %lf %lf %lf", 
		ctrl->mRelX, ctrl->mRelY, ctrl->mRelRZ);
		
	ctrl->mRelMove = true;
}

void AgvmPlcShmNode::timerCallback(void)
{

    // Send commands
    memcpy(c_buf, ctrl, sizeof(*ctrl));
    int ret = 0;
#ifdef ENABLE_SHM_RINGBUF
    if (!shm_blkbuf_full(handle_c))
    {
      ret = shm_blkbuf_write(handle_c, c_buf, sizeof(c_buf));
      RCLCPP_DEBUG(LOGGER, "%s: sent %d bytes\n", __FUNCTION__, ret);
    }
#endif
#ifdef ENABLE_SHM_ACRN
    if(mEnableAcrnShm) {
        ret = acrn_shm_->write("amr_cmd", c_buf, sizeof(c_buf));
    }
#endif

    // Receive state
#ifdef ENABLE_SHM_RINGBUF
    ret = 0;
    if (!shm_blkbuf_empty(handle_s))
    {
      ret = shm_blkbuf_read(handle_s, s_buf, sizeof(s_buf));
    }
#endif
#ifdef ENABLE_SHM_ACRN
    if(mEnableAcrnShm) {
        ret = acrn_shm_->read("amr_state", s_buf, sizeof(c_buf));
    }
#endif

    if (ret)
    {
      memcpy(agvmInfo, s_buf, sizeof(*agvmInfo));
      RCLCPP_DEBUG(LOGGER, "%s: receive %d bytes\n", __FUNCTION__, ret);
    }

    // Publish ROS topics
    auto currentTime = tf2_ros::toMsg(tf2::get_now());
    geometry_msgs::msg::TransformStamped odomTrans;
    
    //odom
    mOdom.header.frame_id = mOdomFrame;
    mOdom.child_frame_id = mBaseFrame;
    mOdom.header.stamp = currentTime;
    
    mOdom.twist.twist.linear.x = (agvmInfo->mPosX - mOdom.pose.pose.position.x) * mPubRate;
    mOdom.twist.twist.linear.y = (agvmInfo->mPosY - mOdom.pose.pose.position.y) * mPubRate;
    mOdom.twist.twist.angular.z = (agvmInfo->mPosRZ - mPosRZPriv) * mPubRate;
    mOdom.pose.pose.position.x = agvmInfo->mPosX;
    mOdom.pose.pose.position.y = agvmInfo->mPosY;
    mOdom.pose.pose.position.z = 0;
    RCLCPP_INFO(get_logger(), "AGV cmd: %f %f %f", ctrl->mTransV, ctrl->mTransH, ctrl->mTwist);
    RCLCPP_INFO(get_logger(), "AGV pose: %f %f %f", agvmInfo->mPosX, agvmInfo->mPosY, agvmInfo->mPosRZ);
    RCLCPP_INFO(get_logger(), "AGV vel: %f %f %f", agvmInfo->mVelX, agvmInfo->mVelY, agvmInfo->mVelRZ);
    RCLCPP_INFO(get_logger(), "AGV mOdom: %f %f %f\n", mOdom.twist.twist.linear.x, mOdom.twist.twist.linear.y, mOdom.twist.twist.angular.z);

    tf2::Quaternion tmpQuet;
    tmpQuet.setRPY(0, 0, agvmInfo->mPosRZ);
    mOdom.pose.pose.orientation.x = tmpQuet.x();
    mOdom.pose.pose.orientation.y = tmpQuet.y();
    mOdom.pose.pose.orientation.z = tmpQuet.z();
    mOdom.pose.pose.orientation.w = tmpQuet.w();
    //odom.pose.pose.orientation = tf::createQuaternionMsgFromYaw(agvmInfo->mPosRZ);
    mPosRZPriv = agvmInfo->mPosRZ;
    //协方差有待研究
    //odom.pose.covariance = ?;
    //odom.twist.covariance = ?;
    
    //odom-tf
    odomTrans.header.stamp = currentTime;
    odomTrans.header.frame_id = mOdomFrame;
    odomTrans.child_frame_id = mBaseFrame;
    odomTrans.transform.translation.x = agvmInfo->mPosX;
    odomTrans.transform.translation.y = agvmInfo->mPosY;
    odomTrans.transform.translation.z = 0;
    odomTrans.transform.rotation = mOdom.pose.pose.orientation;
    
    mTFBroadcaster->sendTransform(odomTrans);
    mAgvmOdomPub->publish(mOdom);

	mServoError.data = agvmInfo->mError;
	mServoErrorPub->publish(mServoError);
	
	mRelMoveBusy.data = agvmInfo->mRelMoveBusy;
	mRelMoveBusyPub->publish(mRelMoveBusy);
}

int main(int argc, char * argv[]) 
{
    assert(CHAR_BIT * sizeof (float) == 32);
    rclcpp::init(argc, argv);

#ifdef ENABLE_SHM_RINGBUF
    handle_s = shm_blkbuf_open("amr_state");
    handle_c = shm_blkbuf_open("amr_cmd");
#endif
    rclcpp::spin(std::make_shared<AgvmPlcShmNode>());
    rclcpp::shutdown();
    return 0;
}
