// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#include "ectask.h"
#include <sys/time.h>
#include <time.h>
#include <unistd.h>

EcTask::EcTask(unsigned long affinity)
{
    master = nullptr;
    servo = nullptr;
    sc_size = 0;

    callback = nullptr;
    inPtr = nullptr;
    outPtr = nullptr;

    shm_decode = nullptr;
    shm_encode = nullptr;
    shm_decode_data = nullptr;
    shm_encode_data = nullptr;

    send_handler = nullptr;
    recv_handler = nullptr;
    send_buf = nullptr;
    recv_buf = nullptr;
    send_size = 0;
    recv_size = 0;
    cpuset = affinity;
    master_id = 0;
    use_virtual_servo = false;
}

EcTask::~EcTask()
{
    if(send_handler)
    {
        shm_blkbuf_close(send_handler);
        send_handler = nullptr;
    }
    if(recv_handler)
    {
        shm_blkbuf_close(recv_handler);
        recv_handler = nullptr;
    }
    if(send_buf)
    {
        delete[] send_buf;
        send_buf = nullptr;
    }
    if(recv_buf)
    {
        delete[] recv_buf;
        recv_buf = nullptr;
    }
    if(master)
    {
        motion_servo_master_release(master);
        master = nullptr;
    }
}

unsigned long EcTask::GetCpuAffinity()
{
    return cpuset;
}

unsigned long EcTask::GetMasterid()
{
    return master_id;
}

void EcTask::RigisterShmHandler(char* name, unsigned long blks, unsigned long blk_size, unsigned char issend, std::function<void(void*, void*, void*)> cb, void* data)
{
    if (issend){
        if (send_handler)
        {
            std::cout << "shm send handler had been registered" << std::endl;
        }
        send_handler = shm_blkbuf_init(name, blks, blk_size);
        if (send_buf)
        {
            delete[] send_buf;
        }
        send_buf = new char[blk_size];
        send_size = blk_size;
        shm_encode = cb;
        shm_encode_data = data;
    }
    else
    {
        if (recv_handler)
        {
            std::cout << "shm recv handler had been registered" << std::endl;
        }
        recv_handler = shm_blkbuf_init(name, blks, blk_size);
        if (recv_buf)
        {
            delete[] recv_buf;
        }
        recv_buf = new char[blk_size];
        recv_size = blk_size;
        shm_decode = cb;
        shm_decode_data = data;
    }
}

void EcTask::ShmHandleUpdate()
{
    int ret;
    if (!recv_handler)
    {
        return;
    }
    if (!shm_blkbuf_empty(recv_handler))
    {
        ret = shm_blkbuf_read(recv_handler, recv_buf, recv_size);
        if ((ret)&&(shm_decode))
        {
            shm_decode(this, recv_buf, shm_decode_data);
        }
    }
}

void EcTask::ShmHandlePublish()
{
    if (!send_handler)
    {
        return;
    }
    if(shm_encode)
    {
        shm_encode(this, send_buf, shm_encode_data);
    }
    if (!shm_blkbuf_full(send_handler))
    {
        shm_blkbuf_write(send_handler, send_buf, send_size);
    }
}

void EcTask::RequestVirtualMaster(unsigned long slave_size, unsigned id)
{
    use_virtual_servo = true;
    master_id = id;
    sc_size = slave_size;
}

bool EcTask::RequestMaster(servo_master* masters, char* eni_file, unsigned id)
{
    struct timespec dc_period;
    if (eni_file == nullptr)
    {
        return false;
    }
    master = motion_servo_master_request(masters, eni_file, id);
    if (master == nullptr)
    {
        return false;
    }
    master_id = id;
    sleep(2);
    if(!motion_servo_driver_register_v2(master))
    {
        return false;
    }
    motion_servo_set_send_interval(master);
    motion_servo_register_dc(master);
    clock_gettime(CLOCK_MONOTONIC, &dc_period);
    motion_master_set_application_time(master, TIMESPEC2NS(dc_period));
    return true;
}

void EcTask::Init_Rtmotion()
{
    uint32_t loop;
    if(!use_virtual_servo)
    {
        sc_size = motion_servo_get_slave_size(master->master);
        if(sc_size == 0)
        {
            return;
        }
    }
    servo = new EcServo*[sc_size];
    for(loop=0; loop < sc_size; loop++)
    {
        servo[loop] = new EcServo(master, loop, use_virtual_servo);
    }
}

bool EcTask::ActivateMaster()
{
    if(!use_virtual_servo)
    {
        if(master == nullptr)
        {
            return false;
        }
        if(motion_servo_master_activate(master->master))
        {
            std::cout << "Fail to activate master" << std::endl;
            return false;
        }
    }
    Init_Rtmotion();
    return true;
}

void EcTask::ProcessAllRxFrames()
{
    for (size_t loop = 0; loop < sc_size; loop++)
    {
        if(servo[loop])
        {
            if(servo[loop]->SlaveGetEnable())
            {
                servo[loop]->processRxFrames();
            }
        }
    }
}

void EcTask::ProcessAllTxFrames()
{
    for (size_t loop = 0; loop < sc_size; loop++)
    {
        if(servo[loop])
        {
            if(servo[loop]->SlaveGetEnable())
            {
                servo[loop]->processTxFrames();
            }
        }
    }
}

bool EcTask::CheckAllSlavePowerOn()
{
    bool power_on = true;
    for (size_t loop = 0; loop < sc_size; loop++)
    {
        if(servo[loop])
        {
            if(servo[loop]->SlaveGetEnable())
            {
                power_on = (power_on == true) &&
                    (servo[loop]->SlavePowerGetStatus()) ?
                    true :
                    false;
            }
        }
    }
    return power_on;
}

bool EcTask::CheckAllSlaveModeSwitch()
{
    bool switch_mode_done = true;
    for (size_t loop = 0; loop < sc_size; loop++)
    {
        if(servo[loop])
        {
            if(servo[loop]->SlaveGetEnable())
            {
                switch_mode_done = (switch_mode_done == true) &&
                    (servo[loop]->is_ControllerModeDone()) ?
                    true :
                    false;
            }
        }
    }
    return switch_mode_done;
}

bool EcTask::CheckAllSlavePositionSetDone()
{
    bool set_position_done = true;
    for (size_t loop = 0; loop < sc_size; loop++)
    {
        if(servo[loop])
        {
            if(servo[loop]->SlaveGetEnable())
            {
                set_position_done = (set_position_done == true) &&
                    (servo[loop]->is_SetPositionDone()) ?
                    true :
                    false;
            }
        }
    }
    return set_position_done;
}

void EcTask::EnableAllSlavePowerMode()
{
    for (size_t loop = 0; loop < sc_size; loop++)
    {
        if(servo[loop])
        {
            if(servo[loop]->SlaveGetEnable())
            {
                servo[loop]->EnableSlavePowerMode();
            }
        }
    }
}

bool EcTask::ExecCycle()
{
    struct timespec dc_period;
    uint8_t* domain;
    if(!use_virtual_servo)
    {
        domain = static_cast<uint8_t*>(motion_servo_get_domain_by_master(master->master));

        motion_servo_recv_process(master->master, domain);
    }
    /* EtherCAT workload process*/
    if (servo)
    {
        ProcessAllRxFrames();
        ShmHandleUpdate();
    }
    if (CheckAllSlavePowerOn())
    {
        EnableAllSlavePowerMode();
    }
    if(CheckAllSlaveModeSwitch())
    {
        for (size_t loop = 0; loop < sc_size; loop++)
        {
            if(servo[loop]->SlaveGetEnable())
            {
                if(!servo[loop]->is_SetPositionEnable())
                    servo[loop]->setPosition(servo[loop]->SlaveGetHomePosRadian() - servo[loop]->getHomePos());
            }
        }
    }
    if(CheckAllSlavePositionSetDone())
    {
        for (size_t loop = 0; loop < sc_size; loop++)
        {
            if(servo[loop]->SlaveGetEnable())
                servo[loop]->setMoveExecute(true);
        }
    }

    executeCallback();
    if (servo)
    {
        ShmHandlePublish();
        ProcessAllTxFrames();
    }

    if(!use_virtual_servo)
    {
        clock_gettime(CLOCK_MONOTONIC, &dc_period);
        motion_servo_sync_dc(master->master,
                           TIMESPEC2NS(dc_period));
        motion_servo_send_process(master->master, domain);
    }
    return true;
}

void EcTask::registerCallback(std::function<void(void*, void*, void*)> func, void* in, void* out)
{
    callback = func;
    inPtr = in;
    outPtr = out;
}

void EcTask::executeCallback()
{
    if (callback != nullptr)
    {
        callback(this, inPtr, outPtr);
    }
}

void EcTask::setPositionBySlaveIdx(unsigned int index, mcLREAL position)
{
    if(servo&&(index < sc_size))
    {
        if(servo[index])
        {
            if(servo[index]->SlaveGetEnable())
            {
                servo[index]->setAbsPosition(position);
            }
        }
    }
}

bool EcTask::SlaveGetActJointState(unsigned int index, mcLREAL* pos, mcLREAL* vel, mcLREAL* acc, mcLREAL* toq)
{
    if(servo&&(index < sc_size))
    {
        if(servo[index])
        {
            if(servo[index]->SlaveGetEnable())
            {
                if (pos)
                {
                    *pos = servo[index]->getActPos();
                }
                if (vel)
                {
                    *vel = servo[index]->getActVel();
                }
                if (acc)
                {
                    *acc = servo[index]->getActAcc();
                }
                if (toq)
                {
                    *toq = servo[index]->getActToq();
                }
                return true;
            }
        }
    }
    return false;
}

bool EcTask::is_trajalldone()
{
    if(!servo)
    {
        return false;
    }
    bool done = true;
    for (size_t loop = 0; loop < sc_size; loop++)
    {
        if(servo[loop])
        {
            if(servo[loop]->SlaveGetEnable())
            {
                done &= servo[loop]->is_TrajDone();
            }
        }
    }
    return done;
}

void EcTask::SlaveSetHomePosRadianByIdx(unsigned int index, mcLREAL radian)
{
    if(servo&&(index < sc_size))
    {
        if(servo[index])
        {
            if(servo[index]->SlaveGetEnable())
                servo[index]->SlaveSetHomePosRadian(radian);
        }
    }
}

void EcTask::UpdateServoConfigByIdx(unsigned int index,  unsigned long encode_accuracy, float gear_ratio, unsigned long cycle_us)
{
    if(servo&&(index < sc_size))
    {
        if(servo[index])
        {
            if(servo[index]->SlaveGetEnable())
                servo[index]->UpdateServoConfig(encode_accuracy, gear_ratio, cycle_us);
        }
    }
}

void EcTask::SetSlaveEnableByIdx(unsigned int index, bool enable)
{
    if(servo&&(index < sc_size))
    {
        if(servo[index])
        {
            servo[index]->SlaveSetEnable(enable);
        }
    }
}

uint32_t EcTask::GetSlaveSize()
{
    return sc_size;
}
