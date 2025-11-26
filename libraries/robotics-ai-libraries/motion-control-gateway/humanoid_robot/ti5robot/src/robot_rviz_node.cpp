#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/joint_state.hpp>
#include <chrono>
#include <cmath>

class RobotRvizNode : public rclcpp::Node
{
public:
    RobotRvizNode() : Node("robot_rviz_node"), angle_(0.0)
    {
        // Create joint state publisher
        joint_pub_ = this->create_publisher<sensor_msgs::msg::JointState>(
            "joint_states", 10);
        
        // Create timer for publishing joint states
        timer_ = this->create_wall_timer(
            std::chrono::milliseconds(50),
            std::bind(&RobotRvizNode::publish_joint_states, this));
        
        RCLCPP_INFO(this->get_logger(), "Robot visualization node started");
    }

private:
    void publish_joint_states()
    {
        auto joint_state = sensor_msgs::msg::JointState();
        
        joint_state.header.stamp = this->now();
        joint_state.name = {"leg_l1_joint"};
        joint_state.position = {angle_};
        joint_state.velocity = {0.1};
        joint_state.effort = {0.0};
        
        joint_pub_->publish(joint_state);
        
        // Update angle for animation
        angle_ += 0.01;
        if (angle_ > 2 * M_PI) {
            angle_ = 0.0;
        }
    }
    
    rclcpp::Publisher<sensor_msgs::msg::JointState>::SharedPtr joint_pub_;
    rclcpp::TimerBase::SharedPtr timer_;
    double angle_;
};

int main(int argc, char * argv[])
{
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<RobotRvizNode>());
    rclcpp::shutdown();
    return 0;
}
