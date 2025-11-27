#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/joint_state.hpp>
#include <chrono>
#include <cmath>
#include <std_msgs/msg/bool.hpp>
#include <shmringbuf.h>

#include <trajectory_msgs/msg/joint_trajectory.hpp>



/* TI5 robot joint name and initial joint values */
static const std::vector<std::string> arm_joint_names = {"joint_1", "joint_2",
                                                     "joint_3", "joint_4",
                                                     "joint_5", "joint_6", "joint_7"};
static const std::vector<double> joint_init_values = {0.0, 0.0, 0.0, 0.0, -1.57, 0.0, 0.0};

/* Task flag */
typedef enum
{
  WaitTrajectory     = 0,
  StartTrajectory    = 1,
  WaitTrajectoryDone = 2,
  DoneTrajectory     = 3
} TaskState;

#define NSEC_PER_SEC (1000000000L)

/* Shm related data types
 * s_buf, handle_s: data sent from RT domain
 * r_buf, handle_r: data sent to RT domain
 */

#define MSG_LEN 150000
#define JOINT_NUM 7
#define POINT_NUM 500
static char left_arm_s_buf[MSG_LEN];
static char left_arm_r_buf[MSG_LEN];
static char right_arm_s_buf[MSG_LEN];
static char right_arm_r_buf[MSG_LEN];
static shm_handle_t left_arm_handle_s, left_arm_handle_r;
static shm_handle_t right_arm_handle_s, right_arm_handle_r;

struct TrajPoint
{
  double positions[JOINT_NUM] = {};
  double velocities[JOINT_NUM] = {};
  double accelerations[JOINT_NUM] = {};
  double effort[JOINT_NUM] = {};
  double time_from_start;
};

struct TrajCmd
{
  uint32_t point_num = 0;
  TrajPoint points[POINT_NUM]= {};
};

struct JointState
{
  double joint_pos[JOINT_NUM] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
  double joint_vel[JOINT_NUM] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
  double joint_acc[JOINT_NUM] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
  double joint_toq[JOINT_NUM] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
  bool traj_done = false;
  bool error = false;
};

static TrajCmd left_arm_traj_cmd;
static TrajCmd right_arm_traj_cmd;
static JointState left_arm_j_state;
static JointState right_arm_j_state;

static const rclcpp::Logger LOGGER = rclcpp::get_logger("robot_arm_shm_node");

class RobotArmShmNode : public rclcpp::Node
{
public:
    RobotArmShmNode() : Node("robot_arm_shm_node")
    {
        // Create joint state publisher
        left_arm_joint_msg_ = std::make_unique<sensor_msgs::msg::JointState>();
        left_arm_joint_msg_->name = arm_joint_names;
        left_arm_joint_msg_->position = joint_init_values;

        right_arm_joint_msg_ = std::make_unique<sensor_msgs::msg::JointState>();
        right_arm_joint_msg_->name = arm_joint_names;
        right_arm_joint_msg_->position = joint_init_values;

        left_arm_traj_msg_ = std::make_shared<trajectory_msgs::msg::JointTrajectory>();
        right_arm_traj_msg_ = std::make_shared<trajectory_msgs::msg::JointTrajectory>();

        left_arm_joint_state_publisher_ = this->create_publisher<sensor_msgs::msg::JointState>("/left_arm_joint_states", 1);
        right_arm_joint_state_publisher_ = this->create_publisher<sensor_msgs::msg::JointState>("/right_arm_joint_states", 1);

        left_arm_trajectory_subscriber_ = this->create_subscription<trajectory_msgs::msg::JointTrajectory>(
            "/fake_joint_trajectory_controller/left_arm_joint_trajectory", rclcpp::SystemDefaultsQoS(), \
            std::bind(&RobotArmShmNode::LeftArmtrajectoryCB, this, std::placeholders::_1));
        right_arm_trajectory_subscriber_ = this->create_subscription<trajectory_msgs::msg::JointTrajectory>(
            "/fake_joint_trajectory_controller/right_arm_joint_trajectory", rclcpp::SystemDefaultsQoS(), \
            std::bind(&RobotArmShmNode::RightArmtrajectoryCB, this, std::placeholders::_1));
       
        // Create timer for publishing joint states
        timer_ = this->create_wall_timer(
            std::chrono::milliseconds(50),
            std::bind(&RobotArmShmNode::timerCB, this));
        
        RCLCPP_INFO(LOGGER, "Robot visualization node started");
    }

private:
    void timerCB(void)
    {
        // Send the trajectory to RT domain
        if (left_arm_task_ == StartTrajectory)
        {
            left_arm_task_ = WaitTrajectoryDone;
            left_arm_traj_done_flag_ = false;
            sendLeftJointCmdsToRT(left_arm_traj_msg_);
            RCLCPP_INFO(LOGGER, "Left arm trajectory start.");
        }

        // If trajectory is done, publish "done" message to MoveIt pipeline
        if (left_arm_task_ == WaitTrajectoryDone && left_arm_traj_done_flag_)
        {
            std_msgs::msg::Bool action_msgs;
            action_msgs.data = true;
            left_arm_task_ = WaitTrajectory;
            //action_publisher_->publish(action_msgs);
            RCLCPP_INFO(LOGGER, "Left Arm Trajectory done.");
        }

        // Send the trajectory to RT domain
        if (right_arm_task_ == StartTrajectory)
        {
            right_arm_task_ = WaitTrajectoryDone;
            right_arm_traj_done_flag_ = false;
            sendRightJointCmdsToRT(right_arm_traj_msg_);
            RCLCPP_INFO(LOGGER, "Right arm trajectory start.");
        }

        // If trajectory is done, publish "done" message to MoveIt pipeline
        if (right_arm_task_ == WaitTrajectoryDone && right_arm_traj_done_flag_)
        {
            std_msgs::msg::Bool action_msgs;
            action_msgs.data = true;
            right_arm_task_ = WaitTrajectory;
            //action_publisher_->publish(action_msgs);
            RCLCPP_INFO(LOGGER, "Right Arm Trajectory done.");
        }

        // Receive joint state message from RT domain
        receiveLeftArmJointStateFromRT(left_arm_joint_msg_->position);
        receiveRightArmJointStateFromRT(right_arm_joint_msg_->position);
        left_arm_joint_msg_->header.stamp = this->now();
        right_arm_joint_msg_->header.stamp = this->now();
        left_arm_joint_state_publisher_->publish(*left_arm_joint_msg_);
        right_arm_joint_state_publisher_->publish(*right_arm_joint_msg_);
    }

    void LeftArmtrajectoryCB(const trajectory_msgs::msg::JointTrajectory::SharedPtr msg)
    {
        RCLCPP_INFO(LOGGER, "Left arm Got trajectory msgs.");
        if (msg->joint_names.size() != arm_joint_names.size())
        {
            RCLCPP_INFO(LOGGER, " size:%ld | %ld ", msg->joint_names.size(), arm_joint_names.size());
            RCLCPP_ERROR(LOGGER, "Received trajectory has wrong number of joint names.");
            return;
        }

        //RCLCPP_INFO(LOGGER, "left msg: %f, %f, %f, %f ", msg->points[0].positions[0], msg->points[0].positions[1],  msg->points[0].positions[2], msg->points[0].positions[3]);
        left_arm_traj_msg_ = msg;
        left_arm_task_ = StartTrajectory;
    }

    void RightArmtrajectoryCB(const trajectory_msgs::msg::JointTrajectory::SharedPtr msg)
    {
        RCLCPP_INFO(LOGGER, "Right arm Got trajectory msgs.");
        if (msg->joint_names.size() != arm_joint_names.size())
        {
            RCLCPP_INFO(LOGGER, " size:%ld | %ld ", msg->joint_names.size(), arm_joint_names.size());
            RCLCPP_ERROR(LOGGER, "Received trajectory has wrong number of joint names.");
            return;
        }

        //RCLCPP_INFO(LOGGER, "right msg: %f, %f, %f, %f ", msg->points[0].positions[0], msg->points[0].positions[1], msg->points[0].positions[2], msg->points[0].positions[3]);
        right_arm_traj_msg_ = msg;
        right_arm_task_ = StartTrajectory;
    }

    void sendLeftJointCmdsToRT(const trajectory_msgs::msg::JointTrajectory::SharedPtr msg)
    {
        left_arm_traj_cmd.point_num = msg->points.size();
        for (size_t i = 0; i < msg->points.size(); i++)
        {
            left_arm_traj_cmd.points[i].time_from_start = msg->points[i].time_from_start.sec * NSEC_PER_SEC + msg->points[i].time_from_start.nanosec;

            for (size_t j = 0; j < JOINT_NUM; j++)
            {
                left_arm_traj_cmd.points[i].positions[j] = msg->points[i].positions[j];
                left_arm_traj_cmd.points[i].velocities[j] = msg->points[i].velocities[j];
                left_arm_traj_cmd.points[i].accelerations[j] = msg->points[i].accelerations[j];
                // left_arm_traj_cmd.points[i].effort[j] = msg->points[i].effort[j];
                //RCLCPP_INFO(LOGGER, "%s:%i  %f \n", __FUNCTION__, j, left_arm_traj_cmd.points[i].positions[j]);
            }
        }

        // Send the joint commands to RT domain
        memcpy(left_arm_r_buf, &left_arm_traj_cmd, sizeof(left_arm_traj_cmd));
        if (!shm_blkbuf_full(left_arm_handle_r))
        {
            //RCLCPP_ERROR(LOGGER, "debug.");
            int ret = shm_blkbuf_write(left_arm_handle_r, left_arm_r_buf, sizeof(left_arm_r_buf));
            //RCLCPP_DEBUG(LOGGER, "%s: sent %d bytes\n", __FUNCTION__, ret);
        }
    }


    void sendRightJointCmdsToRT(const trajectory_msgs::msg::JointTrajectory::SharedPtr msg)
    {
        right_arm_traj_cmd.point_num = msg->points.size();
        for (size_t i = 0; i < msg->points.size(); i++)
        {
            right_arm_traj_cmd.points[i].time_from_start = msg->points[i].time_from_start.sec * NSEC_PER_SEC + msg->points[i].time_from_start.nanosec;

            for (size_t j = 0; j < JOINT_NUM; j++)
            {
                right_arm_traj_cmd.points[i].positions[j] = msg->points[i].positions[j];
                right_arm_traj_cmd.points[i].velocities[j] = msg->points[i].velocities[j];
                right_arm_traj_cmd.points[i].accelerations[j] = msg->points[i].accelerations[j];
                // right_arm_traj_cmd.points[i].effort[j] = msg->points[i].effort[j];
                //RCLCPP_INFO(LOGGER, "%s:%i  %f \n", __FUNCTION__, j, right_arm_traj_cmd.points[i].positions[j]);
            }
        }

        // Send the joint commands to RT domain
        memcpy(right_arm_r_buf, &right_arm_traj_cmd, sizeof(right_arm_traj_cmd));
        if (!shm_blkbuf_full(right_arm_handle_r))
        {
            //RCLCPP_ERROR(LOGGER, "debug.");
            int ret = shm_blkbuf_write(right_arm_handle_r, right_arm_r_buf, sizeof(right_arm_r_buf));
						//RCLCPP_DEBUG(LOGGER, "%s: sent %d bytes\n", __FUNCTION__, ret);
        }
    }

    void receiveLeftArmJointStateFromRT(std::vector<double>& joint_state)
    {
        /* get the joint states */
        if (!shm_blkbuf_empty(left_arm_handle_s))
        {
            int ret = shm_blkbuf_read(left_arm_handle_s, left_arm_s_buf, sizeof(left_arm_s_buf));
            if (ret)
            {
                memcpy(&left_arm_j_state, left_arm_s_buf, sizeof(left_arm_j_state));

                if (!left_arm_traj_done_tmp_ && left_arm_j_state.traj_done) // Only done at the rising edge
                    left_arm_traj_done_flag_ = true;

                for (size_t i = 0; i < JOINT_NUM; i++)
                {
                    joint_state[i] = left_arm_j_state.joint_pos[i];
                    //RCLCPP_DEBUG(LOGGER, "\t %ldth joint: %f\n", i, left_arm_j_state.joint_pos[i]);
                }

                left_arm_traj_done_tmp_ = left_arm_j_state.traj_done;
            }
        }
    }

    void receiveRightArmJointStateFromRT(std::vector<double>& joint_state)
    {
        /* get the joint states */
        if (!shm_blkbuf_empty(right_arm_handle_s))
        {
            int ret = shm_blkbuf_read(right_arm_handle_s, right_arm_s_buf, sizeof(right_arm_s_buf));
            if (ret)
            {
                memcpy(&right_arm_j_state, right_arm_s_buf, sizeof(right_arm_j_state));

                if (!right_arm_traj_done_tmp_ && right_arm_j_state.traj_done) // Only done at the rising edge
                    right_arm_traj_done_flag_ = true;

                for (size_t i = 0; i < JOINT_NUM; i++)
                {
                    joint_state[i] = right_arm_j_state.joint_pos[i];
                    //RCLCPP_DEBUG(LOGGER, "\t %ldth joint: %f\n", i, right_arm_j_state.joint_pos[i]);
                }

                right_arm_traj_done_tmp_ = right_arm_j_state.traj_done;
            }
        }
    }
    
    std::unique_ptr<sensor_msgs::msg::JointState> left_arm_joint_msg_;
    std::unique_ptr<sensor_msgs::msg::JointState> right_arm_joint_msg_;
    std::shared_ptr<trajectory_msgs::msg::JointTrajectory> left_arm_traj_msg_;
    std::shared_ptr<trajectory_msgs::msg::JointTrajectory> right_arm_traj_msg_;
    rclcpp::Publisher<sensor_msgs::msg::JointState>::SharedPtr left_arm_joint_state_publisher_;
    rclcpp::Publisher<sensor_msgs::msg::JointState>::SharedPtr right_arm_joint_state_publisher_;
    rclcpp::Subscription<trajectory_msgs::msg::JointTrajectory>::SharedPtr left_arm_trajectory_subscriber_;
    rclcpp::Subscription<trajectory_msgs::msg::JointTrajectory>::SharedPtr right_arm_trajectory_subscriber_;
    //rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr action_publisher_;

    rclcpp::TimerBase::SharedPtr timer_;

    TaskState left_arm_task_;
    TaskState right_arm_task_;
    bool left_arm_traj_done_tmp_ = false;
    bool right_arm_traj_done_tmp_ = false;
    bool left_arm_traj_done_flag_ = false;
    bool right_arm_traj_done_flag_ = false;
};

int main(int argc, char * argv[])
{
    rclcpp::init(argc, argv);

    left_arm_handle_s = shm_blkbuf_open((char*)"left_arm_rtsend");
    left_arm_handle_r = shm_blkbuf_open((char*)"left_arm_rtread");
    right_arm_handle_s = shm_blkbuf_open((char*)"right_arm_rtsend");
    right_arm_handle_r = shm_blkbuf_open((char*)"right_arm_rtread");

    rclcpp::spin(std::make_shared<RobotArmShmNode>());
    rclcpp::shutdown();
    return 0;
}
