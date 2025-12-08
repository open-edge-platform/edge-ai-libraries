#include <rclcpp/rclcpp.hpp>
#include <string>
#include <functional>
#include <chrono>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <assert.h>
#include <bits/stdc++.h>
#include <std_msgs/msg/float32.hpp>
#include <std_msgs/msg/float32_multi_array.hpp>
#include <sensor_msgs/msg/joint_state.hpp>

static const rclcpp::Logger LOGGER = rclcpp::get_logger("Robot_joint_state_aggregator_node");

class RobotJointStateAggregatorNode : public rclcpp::Node
{
public:
    RobotJointStateAggregatorNode();
    ~RobotJointStateAggregatorNode(){};
    void getParameters(void);
    void init(void);

private:
    void timerCallback(void);
    void LeftArmPosCB(const sensor_msgs::msg::JointState::SharedPtr msg);
    void RightArmPosCB(const sensor_msgs::msg::JointState::SharedPtr msg);
    void LegPosCB(const sensor_msgs::msg::JointState::SharedPtr msg);
    int mPubRate;

    float mLegJointAngles[14] = {0.0};
    float mLeftArmJointAngles[7] = {0.0};
    float mRightArmJointAngles[7] = {0.0};
    float mWaistAngles = 0.0;

    rclcpp::Subscription<sensor_msgs::msg::JointState>::SharedPtr mRobotLeftArmJointStateSub;
    rclcpp::Subscription<sensor_msgs::msg::JointState>::SharedPtr mRobotRightArmJointStateSub;
    rclcpp::Subscription<sensor_msgs::msg::JointState>::SharedPtr mRobotLegJointStateSub;

    rclcpp::Publisher<sensor_msgs::msg::JointState>::SharedPtr mRobotJointStatePub;
    rclcpp::TimerBase::SharedPtr mTimer;
};

RobotJointStateAggregatorNode::RobotJointStateAggregatorNode() :
    rclcpp::Node("Robot_joint_state_aggregator_node")
{
    getParameters();
    init();
}

void RobotJointStateAggregatorNode::getParameters(void)
{
    declare_parameter("publish_rate", 100);
    get_parameter("publish_rate", mPubRate);
}

void RobotJointStateAggregatorNode::init(void)
{
    using namespace std::placeholders;

    mRobotJointStatePub = create_publisher<sensor_msgs::msg::JointState>(
        "/joint_states", rclcpp::SystemDefaultsQoS());

    mRobotLeftArmJointStateSub = this->create_subscription<sensor_msgs::msg::JointState>(
            "/left_arm_joint_states", rclcpp::SystemDefaultsQoS(), \
            std::bind(&RobotJointStateAggregatorNode::LeftArmPosCB, this, std::placeholders::_1));
    mRobotRightArmJointStateSub = this->create_subscription<sensor_msgs::msg::JointState>(
            "/right_arm_joint_states", rclcpp::SystemDefaultsQoS(), \
            std::bind(&RobotJointStateAggregatorNode::RightArmPosCB, this, std::placeholders::_1));
    mRobotLegJointStateSub = this->create_subscription<sensor_msgs::msg::JointState>(
            "/leg_joint_states", rclcpp::SystemDefaultsQoS(), \
            std::bind(&RobotJointStateAggregatorNode::LegPosCB, this, std::placeholders::_1));

    mTimer = create_wall_timer(
        std::chrono::nanoseconds((int64_t)(1000000000.0 / mPubRate)),
        std::bind(&RobotJointStateAggregatorNode::timerCallback, this));
}

void RobotJointStateAggregatorNode::LeftArmPosCB(const sensor_msgs::msg::JointState::SharedPtr msg)
{
		//RCLCPP_INFO(LOGGER, "Joint Name - %s ", msg->name[0].c_str());
    for (size_t i = 0; i < msg->position.size(); ++i)
    {
        mLeftArmJointAngles[i] =  msg->position[i];
    }

		//RCLCPP_INFO(LOGGER, "left msg: %f, %f, %f, %f ", msg->position[0], msg->position[1],  msg->position[2], msg->position[3]);
}

void RobotJointStateAggregatorNode::RightArmPosCB(const sensor_msgs::msg::JointState::SharedPtr msg)
{
    for (size_t i = 0; i < msg->position.size(); ++i)
    {
        mRightArmJointAngles[i] =  msg->position[i];
    }
		//RCLCPP_INFO(LOGGER, "right msg: %f, %f, %f, %f ", msg->position[0], msg->position[1],  msg->position[2], msg->position[3]);
}

void RobotJointStateAggregatorNode::LegPosCB(const sensor_msgs::msg::JointState::SharedPtr msg)
{
    double joint_factor[12] = {1,1,1,1,1,1,
	    			1,1,1,1,1,1};
    for (size_t i = 0; i < msg->position.size(); ++i)
    {
        mLegJointAngles[i] =  msg->position[i]* joint_factor[i];
    }
}

void RobotJointStateAggregatorNode::timerCallback(void)
{
    double dt = 1.0 / mPubRate;
    auto joint_state_msg = sensor_msgs::msg::JointState();
		joint_state_msg.name = {
        "l_arm_joint1",
        "l_arm_joint2",
        "r_arm_joint1",
        "r_arm_joint2",
        "leg_l1_joint",
        "leg_l2_joint",
        "leg_l3_joint",
        "leg_l4_joint",
        "leg_l5_joint",
        "leg_l6_joint",
        "leg_r1_joint",
        "leg_r2_joint",
        "leg_r3_joint",
        "leg_r4_joint",
        "leg_r5_joint",
        "leg_r6_joint",
        "WAIST_R",
        "WAIST_Y",
        "WAIST_P",
        "L_SHOULDER_R",
        "L_SHOULDER_Y",
        "R_SHOULDER_R",
        "R_SHOULDER_Y",
	"base_imu_joint"
    };
    joint_state_msg.position = {
        mLeftArmJointAngles[0],
        mLeftArmJointAngles[1]*(-1),
        mRightArmJointAngles[0],
        mRightArmJointAngles[1]*(-1),
        mLegJointAngles[2],
        mLegJointAngles[1],
        mLegJointAngles[0],
        mLegJointAngles[3],
        mLegJointAngles[4],
        mLegJointAngles[5],
        mLegJointAngles[8],
        mLegJointAngles[7],
        mLegJointAngles[6],
        mLegJointAngles[9],
        mLegJointAngles[10],
        mLegJointAngles[11],
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
				0.0
    };
    joint_state_msg.header.stamp = this->now();
    mRobotJointStatePub->publish(joint_state_msg);
}

int main(int argc, char * argv[])
{
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<RobotJointStateAggregatorNode>());
    rclcpp::shutdown();

    return 0;
}
