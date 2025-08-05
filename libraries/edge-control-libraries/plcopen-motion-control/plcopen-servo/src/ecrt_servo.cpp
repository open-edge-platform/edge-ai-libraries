// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

#include <ecrt_servo.hpp>

#include <stdio.h>
#include <string.h>

// cia402 state switch
// status_word & 0x4F == 0x00  : Not ready to Switch on
// status_word & 0x4F == 0x40  : Switch on Disabled
// status_word & 0x6F == 0x21  : Ready to Switch on
// status_word & 0x6F == 0x23  : Switch on
// status_word & 0x6F == 0x27  : Operation enabled
// status_word & 0x6F == 0x07  : Quick stop active
// status_word & 0x4F == 0x0F  : Fault reaction active
// status_word & 0x4F == 0x08  : Fault

// #define DEBUG_PRINT_ENABLE

class EcrtServo::ServoImpl
{
public:
  mcDINT mSubmitPos  = 0;
  mcDINT mPos        = 0;
  mcLREAL mVel       = 0;
  mcLREAL mAcc       = 0;
  mcINT mToq         = 0;
  mcSINT mMode       = 0;
  mcBOOL mHomeEnable = mcFALSE;
  mcBOOL mHomeState  = mcFALSE;
};

EcrtServo::EcrtServo()
  : mImpl_(nullptr)
  , control_mode_(MODE_CSP)
  , pdo_check_ok_(mcFALSE)
  , servo_on_(mcFALSE)
  , power_enable_(mcFALSE)
  , power_operate_code_(MC_POWERED_OFF)
  , status_word_(0)
  , control_word_(0)
  , domain1_(nullptr)
  , master_(nullptr)
  , target_pos_(0)
  , target_vel_(0)
  , target_toq_(0)
  , target_max_profile_vel_(PER_CIRCLE_ENCODER)
  , control_word_offset_(0)
  , target_pos_offset_(0)
  , status_word_offset_(0)
  , actual_mode_offset_(0)
  , actual_pos_offset_(0)
  , actual_vel_offset_(0)
  , actual_toq_offset_(0)
  , mode_sel_offset_(0)
  , target_vel_offset_(0)
  , target_toq_offset_(0)
  , target_max_profile_vel_offset_(0)
  , alias_(0)
  , position_(0)
  , servo_error_(mcServoNoError)
  , cur_vel_tmp_(0)
{
  mImpl_                                  = new ServoImpl();
  master_state_.m_state.slaves_responding = 0;
  master_state_.m_state.al_states         = 0;
  master_state_.m_state.link_up           = 0;
}

EcrtServo::~EcrtServo()
{
  delete mImpl_;
}

MC_SERVO_ERROR_CODE EcrtServo::setMode(mcSINT mode)
{
  if (pdo_check_ok_ != mcTRUE)
  {
    perror("Please run EcrtServo::initialize(uint16_t alias, uint16_t "
           "position) before hand. \n");
    return mcServoFieldbusInitError;
  }

  switch (mode)
  {
    case MODE_CSP: {
      motion_servo_set_mode(master_, alias_, position_, MODE_CSP);
      control_mode_ = mode;
    }
    break;
    case MODE_CSV: {
      motion_servo_set_mode(master_, alias_, position_, MODE_CSV);
      control_mode_ = mode;
    }
    break;
    case MODE_CST: {
      motion_servo_set_mode(master_, alias_, position_, MODE_CST);
      control_mode_ = mode;
    }
    break;
    case MODE_HM: {
      motion_servo_set_mode(master_, alias_, position_, MODE_HM);
      control_mode_ = mode;
    }
    break;
    default:
      break;
  }

  if (control_mode_ != mode)
    return mcServoFieldbusInitError;

  return mcServoNoError;
}

mcBOOL EcrtServo::initialize(mcUINT alias, mcUINT position)
{
  position_ = position;
  alias_    = alias;

  status_word_offset_ = motion_servo_get_domain_offset(master_->master, alias_,
                                                       position_, 0x6041, 0x00);
  if (status_word_offset_ == DOMAIN_INVAILD_OFFSET)
  {
    pdo_check_ok_ = mcFALSE;
    return mcFALSE;
  }

  actual_mode_offset_ = motion_servo_get_domain_offset(master_->master, alias_,
                                                       position_, 0x6061, 0x00);
  if (actual_mode_offset_ == DOMAIN_INVAILD_OFFSET)
  {
    pdo_check_ok_ = mcFALSE;
    return mcFALSE;
  }

  actual_pos_offset_ = motion_servo_get_domain_offset(master_->master, alias_,
                                                      position_, 0x6064, 0x00);
  if (actual_pos_offset_ == DOMAIN_INVAILD_OFFSET)
  {
    pdo_check_ok_ = mcFALSE;
    return mcFALSE;
  }

  actual_vel_offset_ = motion_servo_get_domain_offset(master_->master, alias_,
                                                      position_, 0x606c, 0x00);
  if (actual_vel_offset_ == DOMAIN_INVAILD_OFFSET)
  {
    pdo_check_ok_ = mcFALSE;
    return mcFALSE;
  }

  actual_toq_offset_ = motion_servo_get_domain_offset(master_->master, alias_,
                                                      position_, 0x6077, 0x00);
  if (actual_toq_offset_ == DOMAIN_INVAILD_OFFSET)
  {
    pdo_check_ok_ = mcFALSE;
    return mcFALSE;
  }

  control_word_offset_ = motion_servo_get_domain_offset(
      master_->master, alias_, position_, 0x6040, 0x00);
  if (control_word_offset_ == DOMAIN_INVAILD_OFFSET)
  {
    pdo_check_ok_ = mcFALSE;
    return mcFALSE;
  }

  target_pos_offset_ = motion_servo_get_domain_offset(master_->master, alias_,
                                                      position_, 0x607a, 0x00);
  if (target_pos_offset_ == DOMAIN_INVAILD_OFFSET)
  {
    pdo_check_ok_ = mcFALSE;
    return mcFALSE;
  }

  mode_sel_offset_ = motion_servo_get_domain_offset(master_->master, alias_,
                                                    position_, 0x6060, 0x00);
  if (mode_sel_offset_ == DOMAIN_INVAILD_OFFSET)
  {
    pdo_check_ok_ = mcFALSE;
    return mcFALSE;
  }

  target_vel_offset_ = motion_servo_get_domain_offset(master_->master, alias_,
                                                      position_, 0x60FF, 0x00);
  if (target_vel_offset_ == DOMAIN_INVAILD_OFFSET)
  {
    pdo_check_ok_ = mcFALSE;
    return mcFALSE;
  }

  target_toq_offset_ = motion_servo_get_domain_offset(master_->master, alias_,
                                                      position_, 0x6071, 0x00);
  if (target_toq_offset_ == DOMAIN_INVAILD_OFFSET)
  {
    pdo_check_ok_ = mcFALSE;
    return mcFALSE;
  }

  target_max_profile_vel_offset_ = motion_servo_get_domain_offset(
      master_->master, alias_, position_, 0x607F, 0x00);
  if (target_max_profile_vel_offset_ == DOMAIN_INVAILD_OFFSET)
  {
    pdo_check_ok_ = mcFALSE;
    return mcFALSE;
  }

  pdo_check_ok_ = mcTRUE;
  return mcTRUE;
}

MC_SERVO_ERROR_CODE EcrtServo::checkMasterState()
{
  if (master_ && master_->master)
  {
    motion_servo_get_master_state(master_->master, &master_state_);
    if (!master_state_.m_state.slaves_responding)
    {
      control_word_ = 0x00;
      return mcServoErrorWhenPoweredOn;
    }
  }
  return mcServoNoError;
}

mcBOOL isServoError(mcUINT status)
{
  if ((status & 0x004F) == 0x000F || (status & 0x004F) == 0x0008)
    return mcTRUE;

  return mcFALSE;
}

MC_SERVO_ERROR_CODE EcrtServo::setPower(mcBOOL powerStatus, mcBOOL& isDone)
{
  servo_error_ = mcServoNoError;
  isDone       = mcFALSE;

  servo_error_ = checkMasterState();  // monitor master
  if (servo_error_ != mcServoNoError)
    return servo_error_;

  if (powerStatus == mcTRUE &&
      power_enable_ == mcFALSE)  // Enable Power On --> 100
  {
    if (pdo_check_ok_ == mcFALSE)
      return mcServoFieldbusInitError;

    power_operate_code_ = MC_ENABLE_POWER_ON;
#ifdef DEBUG_PRINT_ENABLE
    printf("drive:%d Enable Power On\n", position_);
#endif
  }
  else if (power_enable_ == mcTRUE &&
           powerStatus == mcFALSE)  // Enable Power Off --> 200
  {
    servo_on_           = mcFALSE;
    power_operate_code_ = MC_ENABLE_POWER_OFF;
#ifdef DEBUG_PRINT_ENABLE
    printf("drive:%d Enable Power Off\n", position_);
#endif
  }
  else
  {
    if (power_operate_code_ == MC_ENABLE_POWER_ON)  // When enable power on
    {
      if ((status_word_ & 0x007F) == 0x0037)  // Operation Enabled --> 101
      {
        isDone              = mcTRUE;
        servo_on_           = mcTRUE;
        power_operate_code_ = MC_POWERED_ON;
#ifdef DEBUG_PRINT_ENABLE
        printf("drive:%d Power up\n", position_);
#endif
      }
      else if ((status_word_ & 0x006F) ==
               0x0007)  // FSA State: Quick Stop Active
      {
        control_word_ = 0x00;
#ifdef DEBUG_PRINT_ENABLE
        printf("drive:%d Drive Quick Stop Active\n", position_);
#endif
      }
      else if ((status_word_ & 0x4F) ==
               0x0)  // FSA State: Not ready to Switch on
      {
        control_word_ = 0x80;
#ifdef DEBUG_PRINT_ENABLE
        printf("drive:%d Not ready to Switch on\n", position_);
#endif
      }
      else if ((status_word_ & 0x004F) ==
               0x0040)  // FSA State: Switch On Disabled
      {
        control_word_ = 0x06;
#ifdef DEBUG_PRINT_ENABLE
        printf("drive:%d Switch On Disabled\n", position_);
#endif
      }
      else if ((status_word_ & 0x007F) ==
               0x0031)  // FSA State: Ready to Switch On
      {
        control_word_ = 0x07;
#ifdef DEBUG_PRINT_ENABLE
        printf("drive:%d Ready to Switch On\n", position_);
#endif
      }
      else if ((status_word_ & 0x007B) == 0x0033)  // FSA State: Switched On
      {
        mImpl_->mPos = MOTION_DOMAIN_READ_S32(domain1_ + actual_pos_offset_);
        MOTION_DOMAIN_WRITE_S32(domain1_ + target_pos_offset_, mImpl_->mPos);
        MOTION_DOMAIN_WRITE_S8(domain1_ + mode_sel_offset_, MODE_CSP);
        control_word_ = 0x0F;
#ifdef DEBUG_PRINT_ENABLE
        printf("drive:%d Switch on\n", position_);
#endif
      }
      else if ((status_word_ & 0x4F) == 0x0F)  // Fault reaction active
      {
        control_word_ = 0x80;
#ifdef DEBUG_PRINT_ENABLE
        printf("drive:%d Fault reaction active\n", position_);
#endif
      }
      else if ((status_word_ & 0x4F) == 0x08)  // Fault
      {
        control_word_ = 0x80;
#ifdef DEBUG_PRINT_ENABLE
        printf("drive:%d Fault\n", position_);
#endif
      }
      else
      {
        servo_on_           = mcFALSE;
        isDone              = mcFALSE;
        power_operate_code_ = MC_POWER_ERROR;
        servo_error_        = mcServoPoweringOnError;
#ifdef DEBUG_PRINT_ENABLE
        printf("drive:%d Error, Power On statusword=0x%X\n", position_,
               status_word_);
#endif
      }
    }
    else if (power_operate_code_ == MC_POWERED_ON)  // When powered on
    {
      if (isServoError(status_word_) == mcTRUE)
      {
        control_word_       = 0x00;
        servo_on_           = mcFALSE;
        isDone              = mcFALSE;
        power_operate_code_ = MC_POWER_ERROR;
        servo_error_        = mcServoErrorWhenPoweredOn;
#ifdef DEBUG_PRINT_ENABLE
        printf("drive:%d Error, Powered On\n", position_);
#endif
      }
      else
      {
        isDone = mcTRUE;
      }
    }
    else if (power_operate_code_ ==
             MC_ENABLE_POWER_OFF)  // When enabled power off --> 201
    {
      control_word_       = 0x06;
      power_operate_code_ = MC_POWERING_OFF;
    }
    else if (power_operate_code_ ==
             MC_POWERING_OFF)  // After sending shut down message
    {
      control_word_ = 0x06;
      if (isServoError(status_word_) == mcTRUE)  // Shut down fail
      {
        servo_on_    = mcFALSE;
        isDone       = mcFALSE;
        servo_error_ = mcServoPoweringOffError;
#ifdef DEBUG_PRINT_ENABLE
        printf("drive:%d Drive Error, Power off\n", position_);
#endif
      }
      else
      {
        if ((status_word_ & 0x007F) ==
            0x0031)  // Shut down to: Ready to Switch On
        {
          servo_on_           = mcFALSE;
          isDone              = mcTRUE;
          power_operate_code_ = MC_POWERED_OFF;
#ifdef DEBUG_PRINT_ENABLE
          printf("drive:%d Drive, Power off\n", position_);
#endif
        }
      }
    }
  }

  power_enable_ = powerStatus;
  return servo_error_;
}

MC_SERVO_ERROR_CODE EcrtServo::resetError(mcBOOL& isDone)
{
  servo_error_ = mcServoNoError;
  isDone       = mcFALSE;

  // master exception
  servo_error_ = checkMasterState();
  if (servo_error_ != mcServoNoError)
    return servo_error_;

  //  printf("drive:%d *status_word_offset_: 0x%X, power_operate_code_: %d\n",
  //  position_, status, power_operate_code_);
  if (power_operate_code_ == MC_POWER_ERROR)
  {
    if (isServoError(status_word_) == mcTRUE)
    {
      control_word_ = 0x80;
    }
    else if ((status_word_ & 0x004F) == 0x0040)
    {
      power_operate_code_ = MC_POWERED_OFF;
      isDone              = mcTRUE;
    }
  }
  else
  {
    power_operate_code_ = MC_POWERED_OFF;
    isDone              = mcTRUE;
  }

  return servo_error_;
}

MC_SERVO_ERROR_CODE EcrtServo::setPos(mcDINT pos)
{
  mImpl_->mSubmitPos = pos;
  return mcServoNoError;
}

MC_SERVO_ERROR_CODE EcrtServo::setVel(mcDINT vel)
{
  target_vel_ = vel;
  return mcServoNoError;
}

MC_SERVO_ERROR_CODE EcrtServo::setTorque(mcLREAL torque)
{
  target_toq_ = torque;
  return mcServoNoError;
}

MC_SERVO_ERROR_CODE EcrtServo::setMaxProfileVel(mcDWORD vel)
{
  target_max_profile_vel_ = vel;
  return mcServoNoError;
}

MC_SERVO_ERROR_CODE EcrtServo::setHomeEnable(mcBOOL enable)
{
  mImpl_->mHomeEnable = enable;
  return mcServoNoError;
}

mcBOOL EcrtServo::getHomeState()
{
  // When the servo is in home mode,
  // bit 12 of the status word indicates the servo homing status
  if (((status_word_ >> 12) & 0x1) && (mImpl_->mMode == MODE_HM))
    mImpl_->mHomeState = mcTRUE;
  else
    mImpl_->mHomeState = mcFALSE;
  return mImpl_->mHomeState;
}

mcDINT EcrtServo::pos()
{
  return mImpl_->mPos;
}

mcDINT EcrtServo::vel()
{
  return mImpl_->mVel;
}

mcDINT EcrtServo::acc()
{
  return mImpl_->mAcc;
}

mcLREAL EcrtServo::torque()
{
  return mImpl_->mToq;
}

mcSINT EcrtServo::mode()
{
  return mImpl_->mMode;
}

mcBOOL EcrtServo::readVal(mcUINT /*index*/, mcUSINT /*sub_index*/,
                          mcUSINT /*data_length*/, mcUDINT& /*value*/)
{
  return mcTRUE;
}

mcBOOL EcrtServo::writeVal(mcUINT index, mcUSINT sub_index, mcUSINT data_length,
                           mcUDINT value)
{
  switch (data_length)
  {
    case 1:
      motion_servo_slave_config_sdo8(master_, alias_, position_, index,
                                     sub_index, value);
      break;
    case 2:
      motion_servo_slave_config_sdo16(master_, alias_, position_, index,
                                      sub_index, value);
      break;
    case 4:
      motion_servo_slave_config_sdo32(master_, alias_, position_, index,
                                      sub_index, value);
      break;
    default:
      return mcFALSE;
      break;
  }
  return mcTRUE;
}

mcBOOL EcrtServo::getCommunicationReady()
{
  if (status_word_ & 0x1)
    return mcTRUE;
  else
    return mcFALSE;
}

mcBOOL EcrtServo::getReadyForPowerOn()
{
  if ((status_word_ >> 1) & 0x1)
    return mcTRUE;
  else
    return mcFALSE;
}

void EcrtServo::runCycle(mcLREAL freq)
{
  status_word_ = MOTION_DOMAIN_READ_U16(domain1_ + status_word_offset_);
#ifdef DEBUG_PRINT_ENABLE
  printf("drive:%d *status_word_offset_: 0x%X, power_operate_code_: %d\n",
         position_, status_word_, power_operate_code_);
#endif
  if (pdo_check_ok_ == mcTRUE)
  {
    target_pos_   = MOTION_DOMAIN_READ_S32(domain1_ + actual_pos_offset_);
    cur_vel_tmp_  = (target_pos_ - mImpl_->mPos) * freq;
    mImpl_->mToq  = MOTION_DOMAIN_READ_S16(domain1_ + actual_toq_offset_);
    mImpl_->mMode = MOTION_DOMAIN_READ_S8(domain1_ + actual_mode_offset_);
    mImpl_->mAcc  = (cur_vel_tmp_ - mImpl_->mVel) * freq;
    mImpl_->mVel  = cur_vel_tmp_;
    mImpl_->mPos  = target_pos_;
    // printf("drive:%d mImpl_->mSubmitPos=%d\n", position_,
    // mImpl_->mSubmitPos); printf("drive:%d coe_cia402_statemachine
    // status=0x%X\n", position_, *status_word_offset_);
    if (servo_on_ == mcTRUE)
    {
      switch (control_mode_)
      {
        case MODE_CSP: {
          target_pos_ = mImpl_->mSubmitPos;
          MOTION_DOMAIN_WRITE_S32(domain1_ + target_pos_offset_, target_pos_);
          MOTION_DOMAIN_WRITE_S8(domain1_ + mode_sel_offset_, MODE_CSP);
          control_word_ &= 0xEF;
          break;
        }
        case MODE_CSV: {
          MOTION_DOMAIN_WRITE_S32(domain1_ + target_vel_offset_, target_vel_);
          MOTION_DOMAIN_WRITE_S8(domain1_ + mode_sel_offset_, MODE_CSV);
          control_word_ &= 0xEF;
          break;
        }
        case MODE_CST: {
          MOTION_DOMAIN_WRITE_S16(domain1_ + target_toq_offset_, target_toq_);
          MOTION_DOMAIN_WRITE_S8(domain1_ + mode_sel_offset_, MODE_CST);
          break;
        }
        case MODE_HM: {
          MOTION_DOMAIN_WRITE_S8(domain1_ + mode_sel_offset_, MODE_HM);
          if ((mImpl_->mHomeEnable == mcTRUE) && (mImpl_->mMode == MODE_HM))
            control_word_ |= 0x10;
          else
            control_word_ &= 0xEF;
          break;
        }
        default:
          break;
      }
      MOTION_DOMAIN_WRITE_U32(domain1_ + target_max_profile_vel_offset_,
                              target_max_profile_vel_);
    }
  }
  MOTION_DOMAIN_WRITE_U16(domain1_ + control_word_offset_, control_word_);
}