// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

#include <symg_servo.hpp>

ec_pdo_entry_info_t slave_pdo_entries[] = {
  { 0x2200, 0x01, 32 }, /* control */
  { 0x2200, 0x02, 32 }, /* speed1 */
  { 0x2200, 0x03, 32 }, /* speed2 */
  { 0x2200, 0x04, 32 }, /* speed3 */
  { 0x2200, 0x05, 32 }, /* speed4 */
  { 0x2200, 0x06, 32 }, /* pio_out */
  { 0x2100, 0x01, 32 }, /* Status */
  { 0x2100, 0x02, 32 }, /* enc1 */
  { 0x2100, 0x03, 32 }, /* enc2 */
  { 0x2100, 0x04, 32 }, /* enc3 */
  { 0x2100, 0x05, 32 }, /* enc4 */
  { 0x2100, 0x06, 32 }, /* pio_in */
};

ec_pdo_info_t slave_pdos[] = {
  { 0x1600, 6, slave_pdo_entries + 0 }, /* PEC_Outputs */
  { 0x1a00, 6, slave_pdo_entries + 6 }, /* PEC_Inputs */
};

ec_sync_info_t slave_syncs[] = {
  { 0, EC_DIR_OUTPUT, 0, nullptr, EC_WD_DISABLE },
  { 1, EC_DIR_INPUT, 0, nullptr, EC_WD_DISABLE },
  { 2, EC_DIR_OUTPUT, 1, slave_pdos + 0, EC_WD_ENABLE },
  { 3, EC_DIR_INPUT, 1, slave_pdos + 1, EC_WD_ENABLE },
  { 0xff }
};

class EcrtServo::ServoImpl
{
public:
  mcDINT mSubmitPos = 0;
  mcDINT mPos       = 0;
  mcLREAL mVel      = 0;
  mcLREAL mAcc      = 0;
};

EcrtServo::EcrtServo()
  : domain_pd_(nullptr)
  , ec_slave0_(nullptr)
  , ec_motor0_(nullptr)
  , id_(UL)
  , move_(mcFALSE)
  , vel_cmd_(0)
  , vel_scale_(0)
{
  mImpl_ = new ServoImpl();
}

EcrtServo::~EcrtServo()
{
  delete mImpl_;
}

MC_SERVO_ERROR_CODE EcrtServo::setPower(mcBOOL /*powerStatus*/, mcBOOL& isDone)
{
  EC_WRITE_U32(domain_pd_ + ec_slave0_->control, 0xff);

  if ((ec_motor0_->stat & 0xff) == 0x40)
  {
    isDone = mcTRUE;
    move_  = mcTRUE;
    printf("Enabled %dth axis\n", id_);
  }
  return mcServoNoError;
}

MC_SERVO_ERROR_CODE EcrtServo::setVel(mcDINT vel)
{
  vel_cmd_ = vel * vel_scale_;
  return mcServoNoError;
}

int32_t EcrtServo::vel()
{
  return mImpl_->mVel;
}

MC_SERVO_ERROR_CODE EcrtServo::resetError(mcBOOL& isDone)
{
  EC_WRITE_U32(domain_pd_ + ec_slave0_->control, 0x100);
  isDone = mcTRUE;
  return mcServoNoError;
}

void EcrtServo::runCycle(mcLREAL freq)
{
  mcDINT cur_pos = 0;
  if (move_ == mcTRUE)
  {
    switch (id_)
    {
      // printf("Send speed command to %dth axis\n", id_);
      case UL:
        EC_WRITE_S32(domain_pd_ + ec_slave0_->speed1, vel_cmd_);
        cur_pos = ec_motor0_->en1;
        break;
      case UR:
        EC_WRITE_S32(domain_pd_ + ec_slave0_->speed2, vel_cmd_);
        cur_pos = ec_motor0_->en2;
        break;
      case LL:
        EC_WRITE_S32(domain_pd_ + ec_slave0_->speed3, vel_cmd_);
        cur_pos = ec_motor0_->en3;
        break;
      case LR:
        EC_WRITE_S32(domain_pd_ + ec_slave0_->speed4, vel_cmd_);
        cur_pos = ec_motor0_->en4;
        break;
      default:
        break;
    }
  }

  mcDINT pos_diff = cur_pos - mImpl_->mPos;
  mcLREAL cur_vel = pos_diff * freq;
  mImpl_->mAcc    = (cur_vel - mImpl_->mVel) * freq;
  mImpl_->mVel    = cur_vel;
  mImpl_->mPos    = cur_pos;
}

void EcrtServo::emergStop()
{
  switch (id_)
  {
    case UL:
      EC_WRITE_U32(domain_pd_ + ec_slave0_->control, 0x01);
      break;
    case UR:
      EC_WRITE_U32(domain_pd_ + ec_slave0_->control, 0x02);
      break;
    case LL:
      EC_WRITE_U32(domain_pd_ + ec_slave0_->control, 0x04);
      break;
    case LR:
      EC_WRITE_U32(domain_pd_ + ec_slave0_->control, 0x08);
      break;
    default:
      break;
  }
}
