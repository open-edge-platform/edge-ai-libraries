// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#include <mqueue.h>
#include <pthread.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/ipc.h>
#include <sys/mman.h>
#include <sys/time.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>
#include <getopt.h>
#include <sys/stat.h>

#include "ectask/ectask.h"
#include "rl_inference/rl_stand_inference.h"
#include "JointState.h"
#include "ImuState.h"
#include "inference_config.h"

#define SERVO_ENCODER_ACCURACY (262144) // 1<<18

enum {
    LEFT_ARM_JOINTS = 0,
    RIGHT_ARM_JOINTS = 1,
    LEG_JOINTS = 2
};

static char* config_file = nullptr;
static unsigned int cycle_us = 1000;
static int run = 1;
static unsigned int node_id = 0;
static servo_master* masters = nullptr;
static bool virtual_servo = false;

std::string model_file;
std::string model_config;
std::string pkldata_csv;
std::string inference_device;

static inference::RlStandInference* rl_policy = nullptr;
static joint_state* pJoints_state;
static joint_state* joints_cmd;

#define MSG_LEN 150000
#define JOINT_NUM 7
#define POINT_NUM 100

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

struct TrajStat
{
    TrajCmd traj_cmd;
    bool start;
    unsigned int index;
    struct timespec start_time;
};
static TrajStat left_arm_traj_cmd;
static TrajStat right_arm_traj_cmd;

struct JointState
{
  double joint_pos[JOINT_NUM] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
  double joint_vel[JOINT_NUM] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
  double joint_acc[JOINT_NUM] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
  double joint_toq[JOINT_NUM] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
  bool traj_done = false;
  bool error = false;
};
static JointState left_arm_joint_state;
static JointState right_arm_joint_state;

static const float axis_dir_with_servo[JOINT_NUM] = {1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0};

static const float left_arm_axis_home_pos_radian[JOINT_NUM] = {-0.044342, -1.430245, 0.00743, 0.000288, 0.020517, -0.044581, -0.006184}; // left robot arm
static const float right_arm_axis_home_pos_radian[JOINT_NUM] = {0.04288, 1.444243, -0.005177, -0.020014, -0.007382, -0.0005, 0.019798}; // right robot arm
static const float left_leg_axis_home_pos_radian[JOINT_NUM] = {0, -0.10985, 0.094004, 0.156538, -0.00453, -0.04043, 0.043143}; // left robot leg
static const float right_leg_axis_home_pos_radian[JOINT_NUM] = {0, 0.01335, 0.026533, 0.212528, 0.063684, 0.084513, 0.025502}; // right robot leg

static void getOptions(int argc, char** argv)
{
    int index;
    static struct option long_options[] = {
        // name		 has_arg				flag	val
        { "config", required_argument, nullptr, 'c' },
        { "interval", required_argument, nullptr, 'i' },
        { "node", required_argument, nullptr, 'm' },
        { "cpu_affinity", required_argument, nullptr, 'a' },
        { "virtual_servo", no_argument, nullptr, 's' },
        { "help", no_argument, nullptr, 'h' },
        {}
    };
    do
    {
        index = getopt_long(argc, argv, "c:m:i:sh", long_options, nullptr);
        switch (index)
        {
        case 'c':
            if (config_file) {
                free(config_file);
                config_file = nullptr;
            }
            config_file = static_cast<char*>(malloc(strlen(optarg) + 1));
            if (config_file) {
                memset(config_file, 0, strlen(optarg) + 1);
                memmove(config_file, optarg, strlen(optarg) + 1);
                printf("Using %s\n", config_file);
            }
            break;
        case 'm':
            node_id = (unsigned int)atoi(optarg);
            printf("Node: ID is %d\n", node_id);
            break;
        case 'i':
            cycle_us = (unsigned int)atof(optarg);
            printf("Time: Set running interval to %d us\n", cycle_us);
            break;
        case 's':
            virtual_servo = true;
            printf("Virtual-servo: use virtual servo instead of real servo.\n");
            break;
        case 'h':
            printf("Global options:\n");
            printf("    --config       -c  Specify Config file(Yaml)\n");
            printf("    --node      -m  Specify node id\n");
            printf("    --interval     -i  Specify RT cycle time(us).\n");
            printf("    --virtual-servo   -s  User virtual servo instead of real "
               "servo.\n");
            printf("    --help      -h  Show this help.\n");
            exit(0);
            break;
        }
    } while (index != -1);
}

bool update_arm_joints_state(EcTask* ectask, JointState* joints)
{
    uint32_t size;
    if((!ectask)||(!joints))
    {
        return false;
    }
    size = ectask->GetSlaveSize();
    for(uint32_t loop = 0; loop < size; loop++)
    {
        ectask->SlaveGetActJointState(loop, (mcLREAL*)&joints->joint_pos[loop], (mcLREAL*)&joints->joint_vel[loop], nullptr, (mcLREAL*)&joints->joint_toq);
    }
	return true;
}

static bool update_leg_joints_state(EcTask* ectask, joint_state* joints)
{
    uint32_t size;
    if((!ectask)||(!joints))
    {
        return false;
    }
	size = ectask->GetSlaveSize();
    if (!virtual_servo)
    {
        for(size_t loop = 0; loop < 7; loop++)
        {
            ectask->SlaveGetActJointState(loop, (mcLREAL*)&joints[loop].pos_, (mcLREAL*)&joints[loop].vel_, nullptr, &joints[loop].toq_);
        }
        for(size_t loop = 7; loop < size; loop++)
        {
            ectask->SlaveGetActJointState(loop, (mcLREAL*)&joints[loop].pos_, (mcLREAL*)&joints[loop].vel_, nullptr, &joints[loop].toq_);
        }
    }
    else
    {
        for(size_t loop = 0; loop < 3; loop++)
        {
            ectask->SlaveGetActJointState(2-loop, (mcLREAL*)&joints[loop].pos_, (mcLREAL*)&joints[loop].vel_, nullptr, &joints[loop].toq_);
        }
        for(size_t loop = 3; loop < size; loop++)
        {
            ectask->SlaveGetActJointState(loop, (mcLREAL*)&joints[loop].pos_, (mcLREAL*)&joints[loop].vel_, nullptr, &joints[loop].toq_);
        }
    }
    return true;
}

static void cyclic_left_arm_workload(void* parent, void* input, void* output)
{
    struct timespec  traj_current_time;
    EcTask* ectask = (EcTask*)parent;
    TrajStat* traj_cmd = (TrajStat*)input;
    if(traj_cmd == nullptr)
    {
        return;
    }
    clock_gettime(CLOCK_MONOTONIC, &traj_current_time);
    if(traj_cmd->start)
    {
        if(DIFF_NS(traj_cmd->start_time, traj_current_time) >= traj_cmd->traj_cmd.points[traj_cmd->index].time_from_start)
        {
            if(traj_cmd->index < traj_cmd->traj_cmd.point_num)
            {
                for(int loop = 0; loop < JOINT_NUM; loop++)
                {
                    ectask->setPositionBySlaveIdx(loop, traj_cmd->traj_cmd.points[traj_cmd->index].positions[loop]*axis_dir_with_servo[loop]);
                }
                traj_cmd->index++;
            }
        }
        else
        {
            if(ectask->is_trajalldone())
            {
                traj_cmd->start = false;
            }
        }
    }
}
static void cyclic_right_arm_workload(void* parent, void* input, void* output)
{
    struct timespec  traj_current_time;
    EcTask* ectask = (EcTask*)parent;
    TrajStat* traj_cmd = (TrajStat*)input;
    if(traj_cmd == nullptr)
    {
        return;
    }
    clock_gettime(CLOCK_MONOTONIC, &traj_current_time);
    if(traj_cmd->start)
    {
        if(DIFF_NS(traj_cmd->start_time, traj_current_time) >= traj_cmd->traj_cmd.points[traj_cmd->index].time_from_start)
        {
            if(traj_cmd->index < traj_cmd->traj_cmd.point_num)
            {
                for(int loop = 0; loop < JOINT_NUM; loop++)
                {
                    ectask->setPositionBySlaveIdx(loop, traj_cmd->traj_cmd.points[traj_cmd->index].positions[loop]*axis_dir_with_servo[loop]);
                }
                traj_cmd->index++;
            }
        }
        else
        {
            if(ectask->is_trajalldone())
            {
                traj_cmd->start = false;
            }
        }
    }
}


static void cyclic_leg_workload(void* parent, void* input, void* output)
{
    static int skip = 0;
    EcTask* ectask = (EcTask*)parent;

    if ((!ectask)||(!rl_policy))
    {
        return;
    }
    if(update_leg_joints_state(ectask, pJoints_state))
    {
        pJoints_state[12].pos_ = left_arm_joint_state.joint_pos[0];
        pJoints_state[12].vel_ = left_arm_joint_state.joint_vel[0];
        pJoints_state[12].toq_ = left_arm_joint_state.joint_toq[0];
        pJoints_state[13].pos_ = left_arm_joint_state.joint_pos[1];
        pJoints_state[13].vel_ = left_arm_joint_state.joint_vel[1];
        pJoints_state[13].toq_ = left_arm_joint_state.joint_toq[1];
        pJoints_state[14].pos_ = right_arm_joint_state.joint_pos[0];
        pJoints_state[14].vel_ = right_arm_joint_state.joint_vel[0];
        pJoints_state[14].toq_ = right_arm_joint_state.joint_toq[0];
        pJoints_state[15].pos_ = right_arm_joint_state.joint_pos[1];
        pJoints_state[15].vel_ = right_arm_joint_state.joint_vel[1];
        pJoints_state[15].toq_ = right_arm_joint_state.joint_toq[1];
        //imu_read
        rl_policy->Update(pJoints_state, joints_cmd);
        int size = ectask->GetSlaveSize();
        for(int loop = 0; loop < 3; loop++)
        {
            ectask->setPositionBySlaveIdx(loop, joints_cmd[loop].pos_);
            ectask->setPositionBySlaveIdx(loop, joints_cmd[loop].vel_);
            ectask->setPositionBySlaveIdx(loop, joints_cmd[loop].toq_);
        }
        for(int loop = 3; loop < size; loop++)
        {
            ectask->setPositionBySlaveIdx(loop, joints_cmd[loop].pos_);
            ectask->setPositionBySlaveIdx(loop, joints_cmd[loop].vel_);
            ectask->setPositionBySlaveIdx(loop, joints_cmd[loop].toq_);
        }
	if (!skip) {
	    rl_policy->infer_stat.ResetInferenceStat();
	    skip = 1;
	}
    }
    //imu_trigger
}

static void cyclic_subscribe_process(void* parent, void* output, void* data)
{
    EcTask* ectask = (EcTask*)parent;
    TrajStat* traj_cmd = (TrajStat*)data;
    if(data == nullptr)
    {
        return;
    }
    clock_gettime(CLOCK_MONOTONIC, &traj_cmd->start_time);
    memcpy(&traj_cmd->traj_cmd, output, sizeof(TrajCmd));
    traj_cmd->start = true;
    traj_cmd->index = 0;
}

static void cyclic_publish_process(void* parent, void* output, void* data)
{
    EcTask* ectask = (EcTask*)parent;
    
    JointState* joints_state = (JointState*)data;
    if(joints_state == nullptr)
    {
        return;
    }
    update_arm_joints_state(ectask, joints_state);
    memcpy(output, joints_state, sizeof(JointState));
}

static void cyclic_leg_publish_process(void* parent, void* output, void* data)
{
    EcTask* ectask = (EcTask*)parent;
    
    joint_state* joints_state = (joint_state*)data;
    if(joints_state == nullptr)
    {
        return;
    }
    memcpy(output, joints_state, sizeof(joint_state)*ectask->GetSlaveSize());
}

static void* cyclic_arm_task(void* arg)
{
    struct timespec next_period;
    EcTask* ectask = (EcTask*) arg;
    float* home_radian;

    if (ectask == nullptr)
    {
        return nullptr;
    }
    /* Set CPU core affinity */
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    CPU_SET(ectask->GetCpuAffinity(), &cpuset);
    pthread_setaffinity_np(pthread_self(), sizeof(cpu_set_t), &cpuset);

    if (ectask->GetMasterid() == LEFT_ARM_JOINTS)
    {
        home_radian = (float*)&left_arm_axis_home_pos_radian[0];
    }
    else
    {
        home_radian = (float*)&right_arm_axis_home_pos_radian[0];
    }

    for (size_t loop = 0; loop < JOINT_NUM; loop++)
    {
        ectask->UpdateServoConfigByIdx(loop,  SERVO_ENCODER_ACCURACY, 1.0, cycle_us);
        ectask->SlaveSetHomePosRadianByIdx(loop, home_radian[loop]);
    }

    clock_gettime(CLOCK_MONOTONIC, &next_period);
    while (run)
    {
        next_period.tv_nsec += cycle_us * 1000;
        while (next_period.tv_nsec >= NSEC_PER_SEC)
        {
            next_period.tv_nsec -= NSEC_PER_SEC;
            next_period.tv_sec++;
        }
        clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &next_period, nullptr);
        //
        ectask->ExecCycle();
    }
    return nullptr;
}

static void* cyclic_leg_task(void* arg)
{
    struct timespec next_period;
    EcTask* ectask = (EcTask*) arg;

    if (ectask == nullptr)
    {
        return nullptr;
    }

    /* Set CPU core affinity */
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    CPU_SET(ectask->GetCpuAffinity(), &cpuset);
    pthread_setaffinity_np(pthread_self(), sizeof(cpu_set_t), &cpuset);

    if(!virtual_servo)
    {
        ectask->SetSlaveEnableByIdx(0, false);
        ectask->SetSlaveEnableByIdx(7, false);
        // left leg
        for (size_t loop = 1; loop < JOINT_NUM; loop++)
        {
            ectask->UpdateServoConfigByIdx(loop,  SERVO_ENCODER_ACCURACY, 1.0, cycle_us);
            ectask->SlaveSetHomePosRadianByIdx(loop, left_leg_axis_home_pos_radian[loop]);
        }
        // right leg
        for (size_t loop = 8; loop < JOINT_NUM*2; loop++)
        {
            ectask->UpdateServoConfigByIdx(loop,  SERVO_ENCODER_ACCURACY, 1.0, cycle_us);
            ectask->SlaveSetHomePosRadianByIdx(loop, right_leg_axis_home_pos_radian[loop-7]);
        }
    }
    else
    {
        // left leg
        for (size_t loop = 0; loop < 6; loop++)
        {
            ectask->UpdateServoConfigByIdx(loop,  SERVO_ENCODER_ACCURACY, 1.0, cycle_us);
            ectask->SlaveSetHomePosRadianByIdx(loop, left_leg_axis_home_pos_radian[loop+1]);
        }
        // right leg
        for (size_t loop = 6; loop < 12; loop++)
        {
            ectask->UpdateServoConfigByIdx(loop,  SERVO_ENCODER_ACCURACY, 1.0, cycle_us);
            ectask->SlaveSetHomePosRadianByIdx(loop, right_leg_axis_home_pos_radian[loop-5]);
        }
    }

    clock_gettime(CLOCK_MONOTONIC, &next_period);
    while (run)
    {
        next_period.tv_nsec += cycle_us * 1000;
        while (next_period.tv_nsec >= NSEC_PER_SEC)
        {
            next_period.tv_nsec -= NSEC_PER_SEC;
            next_period.tv_sec++;
        }
        clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &next_period, nullptr);
        //
        ectask->ExecCycle();
    }
    return nullptr;
}

int master_task(EcTask* ectask, pthread_t* cyclic_thread, typeof(void *(void *)) *task)
{
    struct sched_param p;
    pthread_attr_t thattr;
    pthread_attr_init(&thattr);
    pthread_attr_setdetachstate(&thattr, PTHREAD_CREATE_JOINABLE);
    pthread_attr_setinheritsched(&thattr, PTHREAD_EXPLICIT_SCHED);
    pthread_attr_setschedpolicy(&thattr, SCHED_FIFO);
    p.sched_priority = 99;
    pthread_attr_setschedparam(&thattr, &p);

    if (pthread_create(cyclic_thread, &thattr, task, ectask))
    {
        fprintf(stderr, "pthread_create cyclic task failed\n");
        return -1;
    }
    return 0;
}

int main(int argc, char* argv[])
{
    // define ethercat master variable
    static EcTask* leg_ectask = nullptr;
    static EcTask* leftarm_ectask = nullptr;
    static EcTask* rightarm_ectask = nullptr;
    static pthread_t cyclic_leg_thread;
    static pthread_t cyclic_leftarm_thread;
    static pthread_t cyclic_rightarm_thread;
    std::string ConfigPath;

    std::string eni_file;
    int cpu_id;

    auto signal_handler = [](int) { run = 0; };
    signal(SIGTERM, signal_handler);
    signal(SIGINT, signal_handler);
    mlockall(MCL_CURRENT | MCL_FUTURE);

    getOptions(argc, argv);
    
    /* Create master by ENI*/
    if (!config_file)
    {
        printf("Error: Unspecify config file\n");
        exit(0);
    }
    mlockall(MCL_CURRENT | MCL_FUTURE);

    inference::InferenceConfig* rlconfig_ = new inference::InferenceConfig();
    if(rlconfig_)
    {
        std::string name;
        rlconfig_->LoadFile(config_file);
        rlconfig_->getParam("/robot_rl/model_path", ConfigPath);
        std::cout << "ConfigPath:" << ConfigPath<< std::endl;
        rlconfig_->getParam("/robot_rl/model_file", name);
        model_file = ConfigPath + name;
        rlconfig_->getParam("/robot_rl/model_config", name);
        model_config = ConfigPath + name;
        rlconfig_->getParam("/robot_rl/pkldata_csv", name);
        pkldata_csv = ConfigPath + name;
        rlconfig_->getParam("/robot_rl/inference_device", inference_device);
        std::cout << "model_file:" << model_file<< std::endl;
        std::cout << "model_config:" << model_config<< std::endl;
        std::cout << "pkldata_csv:" << pkldata_csv<< std::endl;
        std::cout << "inference device:" << inference_device << std::endl;
    }

    if(!virtual_servo)
    {
        masters = motion_servo_master_create_v2(node_id);
        if (masters == nullptr)
        {
            printf("Error: Master node%d cannot be found\n", node_id);
            exit(0);
        }
    }

    /* Initial ectask for left arm */
    if(rlconfig_)
    {
        rlconfig_->getParam("/ec_task/leftarm/eni_file", eni_file);
        rlconfig_->getParam("/ec_task/leftarm/cpu_affinity", cpu_id);
        printf("left arm: cpu(%d) ENI - %s\n", cpu_id, eni_file.c_str());
    }
    leftarm_ectask = new EcTask(cpu_id);
    if (leftarm_ectask == nullptr)
    {
        printf("Error: new leftarm_ectask fail\n");
        exit(0);
    }
    if(!virtual_servo)
    {
        if (!leftarm_ectask->RequestMaster(masters, (char*)eni_file.c_str(), LEFT_ARM_JOINTS))
        {
            delete leftarm_ectask;
            leftarm_ectask = nullptr;
            motion_servo_master_release(masters);
            exit(0);
        }
    }
    else
    {
        leftarm_ectask->RequestVirtualMaster(JOINT_NUM, LEFT_ARM_JOINTS);
    }
    leftarm_ectask->RigisterShmHandler("left_arm_rtsend", 16, MSG_LEN, 1, cyclic_publish_process, &left_arm_joint_state);
    leftarm_ectask->RigisterShmHandler("left_arm_rtread", 16, MSG_LEN, 0, cyclic_subscribe_process, &left_arm_traj_cmd);
    chmod("/dev/shm/left_arm_rtsend", 0666);
    chmod("/dev/shm/left_arm_rtread", 0666);

    leftarm_ectask->ActivateMaster();

    leftarm_ectask->registerCallback(cyclic_left_arm_workload, &left_arm_traj_cmd, &left_arm_joint_state);
    master_task(leftarm_ectask, &cyclic_leftarm_thread, cyclic_arm_task);

    /* Initial ectask for left arm */
    if(rlconfig_)
    {
        rlconfig_->getParam("/ec_task/rightarm/eni_file", eni_file);
        rlconfig_->getParam("/ec_task/rightarm/cpu_affinity", cpu_id);
        printf("right arm: cpu(%d) ENI - %s\n", cpu_id, eni_file.c_str());
    }
    rightarm_ectask = new EcTask(cpu_id);
    if (rightarm_ectask == nullptr)
    {
        printf("Error: new rightarm_ectask fail\n");
        exit(0);
    }
    if(!virtual_servo)
    {
        if (!rightarm_ectask->RequestMaster(masters, (char*)eni_file.c_str(), RIGHT_ARM_JOINTS))
        {
            delete rightarm_ectask;
            rightarm_ectask = nullptr;
            delete leftarm_ectask;
            leftarm_ectask = nullptr;
            motion_servo_master_release(masters);
            exit(0);
        }
    }
    else
    {
        rightarm_ectask->RequestVirtualMaster(JOINT_NUM, RIGHT_ARM_JOINTS);
    }
    rightarm_ectask->RigisterShmHandler("right_arm_rtsend", 16, MSG_LEN, 1, cyclic_publish_process, &right_arm_joint_state);
    rightarm_ectask->RigisterShmHandler("right_arm_rtread", 16, MSG_LEN, 0, cyclic_subscribe_process, &right_arm_traj_cmd);
    chmod("/dev/shm/right_arm_rtsend", 0666);
    chmod("/dev/shm/right_arm_rtread", 0666);

    rightarm_ectask->ActivateMaster();

    rightarm_ectask->registerCallback(cyclic_right_arm_workload, &right_arm_traj_cmd, &right_arm_joint_state);
    master_task(rightarm_ectask, &cyclic_rightarm_thread, cyclic_arm_task);

    /* Initial ectask for leg */
    if(rlconfig_)
    {
        rlconfig_->getParam("/ec_task/leg/eni_file", eni_file);
        rlconfig_->getParam("/ec_task/leg/cpu_affinity", cpu_id);
        printf("leg: cpu(%d) ENI - %s\n", cpu_id, eni_file.c_str());
    }
    leg_ectask = new EcTask(cpu_id);
    if (leg_ectask == nullptr)
    {
        printf("Error: new leg_ectask fail\n");
        exit(0);
    }
	rl_policy = new inference::RlStandInference();
    if (rl_policy)
    {
        rl_policy->Init(model_file, model_config, pkldata_csv, inference_device);
        pJoints_state = new joint_state[rl_policy->GetJointDim()];
        joints_cmd = new joint_state[rl_policy->GetJointDim()];
    }

    if(!virtual_servo)
    {
        if (!leg_ectask->RequestMaster(masters, (char*)eni_file.c_str(), LEG_JOINTS))
        {
            delete leg_ectask;
            leg_ectask = nullptr;
            delete rightarm_ectask;
            rightarm_ectask = nullptr;
            delete leftarm_ectask;
            leftarm_ectask = nullptr;
            motion_servo_master_release(masters);
            exit(0);
        }
    }
    else
    {
        leg_ectask->RequestVirtualMaster(12, LEG_JOINTS);
    }
    leg_ectask->RigisterShmHandler("leg_rtsend", 16, MSG_LEN, 1, cyclic_leg_publish_process, pJoints_state);
    chmod("/dev/shm/leg_rtsend", 0666);
    leg_ectask->ActivateMaster();

    leg_ectask->registerCallback(cyclic_leg_workload, nullptr, nullptr);
    master_task(leg_ectask, &cyclic_leg_thread, cyclic_leg_task);

    while(run)
    {
        sleep(1);
        std::cout << "Inference Stat: <Total,min(ms),max(ms),avg(ms)> " \
                << rl_policy->infer_stat.stat.count << " " \
                << rl_policy->infer_stat.stat.min << " " \
                << rl_policy->infer_stat.stat.max << " " \
                << rl_policy->infer_stat.stat.avg << std::endl;
    }
    pthread_cancel(cyclic_leg_thread);
    pthread_join(cyclic_leg_thread, nullptr);
    pthread_cancel(cyclic_rightarm_thread);
    pthread_join(cyclic_rightarm_thread, nullptr);
    pthread_cancel(cyclic_leftarm_thread);
    pthread_join(cyclic_leftarm_thread, nullptr);
    if (leg_ectask)
    {
        delete leg_ectask;
        leg_ectask = nullptr;
    }
    if (rightarm_ectask)
    {
        delete rightarm_ectask;
        rightarm_ectask = nullptr;
    }
    if (leftarm_ectask)
    {
        delete leftarm_ectask;
        leftarm_ectask = nullptr;
    }

    shm_unlink("/left_arm_rtsend");
    shm_unlink("/left_arm_rtread");
    shm_unlink("/right_arm_rtsend");
    shm_unlink("/right_arm_rtread");
    shm_unlink("/leg_rtsead");

    if(!virtual_servo)
    {
        motion_servo_master_release(masters);
    }
    if (config_file) {
        free(config_file);
        config_file = nullptr;
    }
    return 0;
}
