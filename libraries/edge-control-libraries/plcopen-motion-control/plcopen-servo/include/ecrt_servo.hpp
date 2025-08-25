// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

#pragma once

#include <cstddef>
#include <cstdint>
#include <ecrt_config.hpp>
#include <motionentry.h>

#include <fb/common/include/global.hpp>
#include <fb/common/include/servo.hpp>
using namespace RTmotion;

#define EPSILON 0.00001

typedef enum
{
  MC_POWERED_OFF      = 0,
  MC_ENABLE_POWER_ON  = 100,
  MC_POWERED_ON       = 101,
  MC_ENABLE_POWER_OFF = 200,
  MC_POWERING_OFF     = 201,
  MC_POWER_ERROR      = 300
} POWER_OPERATION_MODE;

#pragma pack(push)
#pragma pack(4)

class EcrtServo : public Servo
{
public:
  EcrtServo();
  ~EcrtServo() override;

  MC_SERVO_ERROR_CODE setPower(mcBOOL powerStatus, mcBOOL& isDone) override;
  MC_SERVO_ERROR_CODE resetError(mcBOOL& isDone) override;
  MC_SERVO_ERROR_CODE setPos(mcDINT pos) override;
  MC_SERVO_ERROR_CODE setVel(mcDINT vel) override;
  mcDINT acc() override;
  mcDINT vel() override;
  mcDINT pos() override;
  mcLREAL torque() override;
  mcSINT mode() override;
  void runCycle(mcLREAL freq) override;

  MC_SERVO_ERROR_CODE setTorque(mcLREAL torque) override;
  MC_SERVO_ERROR_CODE setMaxProfileVel(mcDWORD vel) override;
  MC_SERVO_ERROR_CODE setMode(mcSINT mode) override;
  MC_SERVO_ERROR_CODE setHomeEnable(mcBOOL enable) override;
  mcBOOL getHomeState() override;

  mcBOOL initialize(mcUINT alias, mcUINT position);
  void setMaster(servo_master* master)
  {
    master_ = master;
  }
  void setDomain(mcUSINT* domain)
  {
    domain1_ = domain;
  }
  MC_SERVO_ERROR_CODE checkMasterState();
  mcBOOL readVal(mcUINT index, mcUSINT sub_index, mcUSINT data_length,
                 mcUDINT& value) override;
  mcBOOL writeVal(mcUINT index, mcUSINT sub_index, mcUSINT data_length,
                  mcUDINT value) override;

  mcBOOL getCommunicationReady() override;
  mcBOOL getReadyForPowerOn() override;

private:
  class ServoImpl;
  ServoImpl* mImpl_;

  mcSINT control_mode_;  // PDO 0x6060
  mcBOOL pdo_check_ok_;  // Boolean to indicate whether ENI includes required
                         // PDOs

  mcBOOL servo_on_;      // Servo CiA402 state switched to Operation Enabled
  mcBOOL power_enable_;  // Flag to trigger power on/off
  POWER_OPERATION_MODE power_operate_code_;  // Used for operation switch change

  mcUINT status_word_;   // PDO 0x6041
  mcUINT control_word_;  // PDO 0x6040

  mcUSINT* domain1_;      // Pointer to EtherCAT domain data
  servo_master* master_;  // Pointer to EtherCAT master
  servo_master_state_t master_state_;

  mcDINT target_pos_;               // PDO 0x607A
  mcDINT target_vel_;               // PDO 0x60FF
  mcINT target_toq_;                // PDO 0x6071
  mcUDINT target_max_profile_vel_;  // PDO 0x607F

  mcUDINT control_word_offset_;  // EtherCAT domain offset of PDO 0x6040
  mcUDINT target_pos_offset_;    // EtherCAT domain offset of PDO 0x607a
  mcUDINT status_word_offset_;   // EtherCAT domain offset of PDO 0x6041
  mcUDINT actual_mode_offset_;   // EtherCAT domain offset of PDO 0x6061
  mcUDINT actual_pos_offset_;    // EtherCAT domain offset of PDO 0x6064
  mcUDINT actual_vel_offset_;    // EtherCAT domain offset of PDO 0x606c
  mcUDINT actual_toq_offset_;    // EtherCAT domain offset of PDO 0x6077
  mcUDINT mode_sel_offset_;      // EtherCAT domain offset of PDO 0x6060
  mcUDINT target_vel_offset_;    // EtherCAT domain offset of PDO 0x60FF
  mcUDINT target_toq_offset_;    // EtherCAT domain offset of PDO 0x6071
  mcUDINT target_max_profile_vel_offset_;  // EtherCAT domain offset of PDO
                                           // 0x607F only works if the servo
                                           // support this PDO 0x607F

  mcUINT alias_;                     // EtherCAT client alias
  mcUINT position_;                  // EtherCAT client position
  MC_SERVO_ERROR_CODE servo_error_;  // Servo error code
  double cur_vel_tmp_;
};

#pragma pack(pop)
