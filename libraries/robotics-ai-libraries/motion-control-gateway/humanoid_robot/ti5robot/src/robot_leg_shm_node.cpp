#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/joint_state.hpp>
#include <chrono>
#include <cmath>
#include <std_msgs/msg/bool.hpp>
#include <shmringbuf.h>

#include <trajectory_msgs/msg/joint_trajectory.hpp>



/* TI5 robot joint name and initial joint values */
static const std::vector<std::string> leg_joint_names = {"joint_1", "joint_2",
                                                     "joint_3", "joint_4",
                                                     "joint_5", "joint_6", "joint_7",
                                                     "joint_8", "joint_9", "joint_10",
                                                     "joint_11", "joint_12", "joint_13",
                                                     "joint_14"};
static const std::vector<double> joint_init_values = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
							0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0};

/* Shm related data types
 * s_buf, handle_s: data sent from RT domain
 * r_buf, handle_r: data sent to RT domain
 */

#define MSG_LEN 150000
#define JOINT_NUM 14
static char leg_s_buf[MSG_LEN];
static shm_handle_t leg_handle_s;

struct joint_state
{
    double pos_;  /* joint position */
    double vel_;  /* joint velocity */
    double acc_;  /* joint acceleration */
    double toq_;  /* joint torque */
};

static joint_state leg_joint_state[JOINT_NUM];

static const rclcpp::Logger LOGGER = rclcpp::get_logger("robot_leg_shm_node");

class RobotLegShmNode : public rclcpp::Node
{
public:
    RobotLegShmNode() : Node("robot_leg_shm_node")
    {
        // Create joint state publisher
        leg_joint_msg_ = std::make_unique<sensor_msgs::msg::JointState>();
        leg_joint_msg_->name = leg_joint_names;
        leg_joint_msg_->position = joint_init_values;

        leg_joint_state_publisher_ = this->create_publisher<sensor_msgs::msg::JointState>("/leg_joint_states", 1);

        // Create timer for publishing joint states
        timer_ = this->create_wall_timer(
            std::chrono::milliseconds(50),
            std::bind(&RobotLegShmNode::timerCB, this));
        
        RCLCPP_INFO(LOGGER, "Robot visualization node started");
    }

private:
    void timerCB(void)
    {
        // Receive joint state message from RT domain
        receiveLegJointStateFromRT(leg_joint_msg_->position);
        leg_joint_msg_->header.stamp = this->now();
        leg_joint_state_publisher_->publish(*leg_joint_msg_);
    }

    void receiveLegJointStateFromRT(std::vector<double>& state)
    {
        /* get the joint states */
        if (!shm_blkbuf_empty(leg_handle_s))
        {
            int ret = shm_blkbuf_read(leg_handle_s, leg_s_buf, sizeof(leg_s_buf));
            if (ret)
            {
                memcpy(&leg_joint_state[0], leg_s_buf, (sizeof(joint_state)*JOINT_NUM));

                for (size_t i = 0; i < JOINT_NUM; i++)
                {
                    state[i] = leg_joint_state[i].pos_;
                    //RCLCPP_INFO(LOGGER, "\t %ldth joint: %f\n", i, leg_joint_state[i].pos_);
                }
            }
        }
    }
    
    std::unique_ptr<sensor_msgs::msg::JointState> leg_joint_msg_;
    rclcpp::Publisher<sensor_msgs::msg::JointState>::SharedPtr leg_joint_state_publisher_;

    rclcpp::TimerBase::SharedPtr timer_;
};

int main(int argc, char * argv[])
{
    rclcpp::init(argc, argv);

    leg_handle_s = shm_blkbuf_open((char*)"leg_rtsend");

    rclcpp::spin(std::make_shared<RobotLegShmNode>());
    rclcpp::shutdown();
    return 0;
}
