// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2026 Intel Corporation

/**
 * @file mc_stop_blending_test.cpp
 *
 * MC_Stop interrupting the PLCopen Part 1 V2.0 Appendix A Example 4
 * ('BlendingLow', Figure 60) motion sequence.
 *
 * Appendix A only defines the blending sequence itself; it has no example of
 * MC_Stop aborting a blended sequence. The expected behaviour is therefore
 * derived from:
 *  - Section 3.3 / Figure 15: MC_Stop ramps the axis down with the given
 *    'Deceleration' and 'Jerk', sets 'Done' once 'Velocity' zero is reached,
 *    keeps the axis in 'Stopping' while 'Execute' is TRUE and moves it to
 *    'Standstill' once 'Done' is set and 'Execute' is FALSE.
 *  - Section 2.4.2: MC_Stop cannot be buffered (it is always 'Aborting') and in
 *    'Aborting' mode "the buffer is cleared", so the active FB and every
 *    pending blended FB report 'CommandAborted'.
 *
 * Every scenario runs at several axis frequencies. The commanded deceleration
 * must stay jerk limited at every cycle rate, not only at 1 kHz.
 */

#include <cmath>
#include <string>
#include <tuple>
#include "gtest/gtest.h"
#include <fb/common/include/axis.hpp>
#include <fb/common/include/global.hpp>
#include <fb/public/include/fb_move_absolute.hpp>
#include <fb/public/include/fb_power.hpp>
#include <fb/public/include/fb_stop.hpp>
#include <fb/private/include/fb_set_position.hpp>

#ifdef PLOT
#include "test_plot.hpp"
#include <tool/fb_debug_tool.hpp>
#endif

using namespace RTmotion;

namespace
{
// MC_Stop dynamics used to interrupt the blending sequence.
constexpr double STOP_DECELERATION = 100;
constexpr double STOP_JERK         = 1000;

// The point of the Example 4 sequence at which MC_Stop is triggered.
enum class StopPoint
{
  kNone,         // Plain Example 4 sequence, no MC_Stop
  kMove1Cruise,  // FB1 cruising at 100, FB2 buffered (BlendingLow)
  kBlendEntry,   // FB1 blending 100 -> 50 towards 1000, FB2 buffered
  kMove2Cruise,  // FB2 cruising at 50, FB3 buffered (BlendingLow)
  kMove3Accel,   // FB3 accelerating 50 -> 100
};

std::string stopPointName(StopPoint point)
{
  switch (point)
  {
    case StopPoint::kNone:
      return "NoStop";
    case StopPoint::kMove1Cruise:
      return "StopInMove1Cruise";
    case StopPoint::kBlendEntry:
      return "StopInBlendEntry";
    case StopPoint::kMove2Cruise:
      return "StopInMove2Cruise";
    case StopPoint::kMove3Accel:
      return "StopInMove3Accel";
  }
  return "Unknown";
}

#ifdef PLOT
std::string plotSuffix(StopPoint point)
{
  switch (point)
  {
    case StopPoint::kNone:
      return "no_stop";
    case StopPoint::kMove1Cruise:
      return "stop_move1_cruise";
    case StopPoint::kBlendEntry:
      return "stop_blend_entry";
    case StopPoint::kMove2Cruise:
      return "stop_move2_cruise";
    case StopPoint::kMove3Accel:
      return "stop_move3_accel";
  }
  return "unknown";
}
#endif
}  // namespace

class MCStopBlendingTest
  : public ::testing::TestWithParam<std::tuple<StopPoint, double>>
{
protected:
  void SetUp() override
  {
    std::tie(stop_point_, frequency_) = GetParam();
    dt_                               = 1.0 / frequency_;

    config_.frequency_ = frequency_;
    axis_              = new Axis();
    axis_->setAxisId(1);
    axis_->setNodeQueueSize(3);
    axis_->setAxisConfig(&config_);
    servo_ = new Servo();
    axis_->setServo(servo_);

    fb_power_.setAxis(axis_);
    fb_power_.setEnable(mcTRUE);
    fb_power_.setEnablePositive(mcTRUE);
    fb_power_.setEnableNegative(mcTRUE);

    set_position_.setAxis(axis_);
    set_position_.setMode(mcSetPositionModeAbsolute);
    set_position_.setPosition(0);
    set_position_.setEnable(mcFALSE);

    // Figure 60 parameters
    move_1_.setAxis(axis_);
    move_1_.setPosition(1000);
    move_1_.setVelocity(100);
    move_1_.setAcceleration(100);
    move_1_.setDeceleration(100);
    move_1_.setBufferMode(mcAborting);

    move_2_.setAxis(axis_);
    move_2_.setPosition(2000);
    move_2_.setVelocity(50);
    move_2_.setAcceleration(50);
    move_2_.setDeceleration(50);
    move_2_.setBufferMode(mcBlendingLow);

    move_3_.setAxis(axis_);
    move_3_.setPosition(3000);
    move_3_.setVelocity(100);
    move_3_.setAcceleration(100);
    move_3_.setDeceleration(100);
    move_3_.setBufferMode(mcBlendingLow);

    stop_.setAxis(axis_);
    stop_.setDeceleration(STOP_DECELERATION);
    stop_.setJerk(STOP_JERK);

#ifdef PLOT
    fb_profile_.addFB("move_1");
    fb_profile_.addFB("move_2");
    fb_profile_.addFB("move_3");
    fb_profile_.addFB("stop");
    fb_profile_.addFB("axis");
    for (const char* fb : { "move_1", "move_2", "move_3" })
    {
      fb_profile_.addItemName(std::string(fb) + ".execute");
      fb_profile_.addItemName(std::string(fb) + ".busy");
      fb_profile_.addItemName(std::string(fb) + ".done");
      fb_profile_.addItemName(std::string(fb) + ".command_aborted");
      fb_profile_.addItemName(std::string(fb) + ".active");
    }
    fb_profile_.addItemName("stop.execute");
    fb_profile_.addItemName("stop.busy");
    fb_profile_.addItemName("stop.done");
    fb_profile_.addItemName("stop.command_aborted");
    fb_profile_.addItemName("axis.stopping");
    fb_profile_.addItemName("axis.standstill");
#endif
  }

  void TearDown() override
  {
    delete servo_;
    delete axis_;
  }

  // Runs one control cycle of the axis and every FB, then records plot data.
  void runCycle()
  {
    axis_->runCycle();
    fb_power_.runCycle();
    set_position_.runCycle();
    move_1_.runCycle();
    move_2_.runCycle();
    move_3_.runCycle();
    stop_.runCycle();

#ifdef PLOT
    axis_profile_.addState(axis_->toUserPos(), axis_->toUserVel(),
                           axis_->toUserAccCmd(), time_);
    addFBStates("move_1", move_1_);
    addFBStates("move_2", move_2_);
    addFBStates("move_3", move_3_);
    fb_profile_.addState("stop.execute", stop_.isEnabled() == mcTRUE);
    fb_profile_.addState("stop.busy", stop_.isBusy() == mcTRUE);
    fb_profile_.addState("stop.done", stop_.isDone() == mcTRUE);
    fb_profile_.addState("stop.command_aborted", stop_.isAborted() == mcTRUE);
    fb_profile_.addState("axis.stopping", axis_->getAxisState() == mcStopping);
    fb_profile_.addState("axis.standstill",
                         axis_->getAxisState() == mcStandstill);
    fb_profile_.addTime(time_);
#endif
  }

#ifdef PLOT
  void addFBStates(const std::string& name, FbMoveAbsolute& fb)
  {
    fb_profile_.addState(name + ".execute", fb.isEnabled() == mcTRUE);
    fb_profile_.addState(name + ".busy", fb.isBusy() == mcTRUE);
    fb_profile_.addState(name + ".done", fb.isDone() == mcTRUE);
    fb_profile_.addState(name + ".command_aborted", fb.isAborted() == mcTRUE);
    fb_profile_.addState(name + ".active", fb.isActive() == mcTRUE);
  }
#endif

  // Drives the Figure 60 'Execute' pulses (0.5 s each).
  void driveExecuteSignals()
  {
    if (!set_position_started_ && fb_power_.getPowerStatus() == mcTRUE)
    {
      set_position_.setEnable(mcTRUE);
      set_position_started_ = true;
    }

    if (!move_1_started_ && set_position_.isEnabled() == mcTRUE)
    {
      move_1_.setExecute(mcTRUE);
      move_1_started_    = true;
      move_1_start_time_ = time_;
    }
    else if (move_1_started_ && time_ - move_1_start_time_ >= 0.5)
      move_1_.setExecute(mcFALSE);

    if (!stop_triggered_ && !move_2_started_ && axis_->toUserPos() >= 500)
    {
      move_2_.setExecute(mcTRUE);
      move_2_started_    = true;
      move_2_start_time_ = time_;
    }
    else if (move_2_started_ && time_ - move_2_start_time_ >= 0.5)
      move_2_.setExecute(mcFALSE);

    if (!stop_triggered_ && !move_3_started_ && axis_->toUserPos() >= 1500 &&
        move_2_.isActive() == mcTRUE)
    {
      move_3_.setExecute(mcTRUE);
      move_3_started_    = true;
      move_3_start_time_ = time_;
    }
    else if (move_3_started_ && time_ - move_3_start_time_ >= 0.5)
      move_3_.setExecute(mcFALSE);
  }

  bool stopConditionReached(double velocity, double previous_velocity)
  {
    switch (stop_point_)
    {
      case StopPoint::kNone:
        return false;
      case StopPoint::kMove1Cruise:
        return move_1_.isActive() == mcTRUE && move_2_.isBusy() == mcTRUE &&
               axis_->toUserPos() >= 700;
      case StopPoint::kBlendEntry:
        return move_1_.isActive() == mcTRUE && move_2_.isBusy() == mcTRUE &&
               axis_->toUserPos() > 900 && velocity <= 75 &&
               velocity < previous_velocity;
      case StopPoint::kMove2Cruise:
        return move_2_.isActive() == mcTRUE && move_3_.isBusy() == mcTRUE &&
               axis_->toUserPos() >= 1600;
      case StopPoint::kMove3Accel:
        return move_3_.isActive() == mcTRUE && velocity >= 75 &&
               velocity > previous_velocity;
    }
    return false;
  }

  StopPoint stop_point_ = StopPoint::kNone;
  double frequency_     = 1000;
  double dt_            = 0.001;
  double time_          = 0;

  AxisConfig config_;
  AXIS_REF axis_ = nullptr;
  Servo* servo_  = nullptr;
  FbPower fb_power_;
  FbSetPosition set_position_;
  FbMoveAbsolute move_1_;
  FbMoveAbsolute move_2_;
  FbMoveAbsolute move_3_;
  FbStop stop_;

  bool set_position_started_ = false;
  bool move_1_started_       = false;
  bool move_2_started_       = false;
  bool move_3_started_       = false;
  bool stop_triggered_       = false;
  double move_1_start_time_  = 0;
  double move_2_start_time_  = 0;
  double move_3_start_time_  = 0;

#ifdef PLOT
  AxisProfile axis_profile_;
  FBDigitalProfile fb_profile_;
#endif
};

class BlendingLowSequenceTest : public MCStopBlendingTest
{
};

class MCStopAbortTest : public MCStopBlendingTest
{
};

// Example 4 without MC_Stop: the blended sequence must complete at every
// cycle rate with the Figure 60 velocity levels (100 -> 50 -> 100 -> 0).
TEST_P(BlendingLowSequenceTest, CompletesAtCycleRate)
{
  double previous_velocity     = 0;
  double max_velocity_step     = 0;
  double max_velocity_step_t   = 0;
  double velocity_move_2_entry = NAN;
  double velocity_move_3_entry = NAN;
  double move_2_cruise_time    = 0;
  bool move_3_done             = false;

  // Ideal duration is ~41 s (see plcopen_example4_blending_low_motion.png).
  while (time_ < 70.0)
  {
    runCycle();
    driveExecuteSignals();

    const double velocity = axis_->toUserVel();
    if (fabs(velocity - previous_velocity) > max_velocity_step)
    {
      max_velocity_step   = fabs(velocity - previous_velocity);
      max_velocity_step_t = time_;
    }
    previous_velocity = velocity;

    if (std::isnan(velocity_move_2_entry) && move_2_.isActive() == mcTRUE)
      velocity_move_2_entry = velocity;
    if (std::isnan(velocity_move_3_entry) && move_3_.isActive() == mcTRUE)
      velocity_move_3_entry = velocity;
    if (move_2_.isActive() == mcTRUE && fabs(velocity - 50) <= 1.0)
      move_2_cruise_time += dt_;

    if (move_3_.isDone() == mcTRUE)
    {
      move_3_done = true;
      break;
    }
    time_ += dt_;
  }

#ifdef PLOT
  const std::string name = "plcopen_example4_blending_low_" +
                           std::to_string(static_cast<int>(frequency_)) + "hz";
  const auto signals_file = test_plot::TestPlot::filename(
      "_" + name + "_signals", "mc_stop_blending_test");
  fb_profile_.plot(signals_file, "FB", 1280, 2400);
  plt::close();
  test_plot::TestPlot::recordFile(signals_file);
  const auto motion_file = test_plot::TestPlot::filename(
      "_" + name + "_motion", "mc_stop_blending_test");
  axis_profile_.plot(motion_file);
  plt::close();
  test_plot::TestPlot::recordFile(motion_file);
#endif

  EXPECT_TRUE(move_3_done) << "sequence did not finish within 70 s";
  // Figure 60: ~10 s to 1000, ~20 s at 50 to 2000, ~10 s to 3000.
  EXPECT_NEAR(time_, 41.0, 2.0) << "the sequence runs at the wrong speed";
  EXPECT_NEAR(velocity_move_2_entry, 50, 1.0);
  EXPECT_NEAR(velocity_move_3_entry, 50, 1.0);
  EXPECT_GT(move_2_cruise_time, 15.0);
  EXPECT_LE(max_velocity_step, 100 * dt_ + 0.01)
      << "velocity step at t=" << max_velocity_step_t;
  EXPECT_NEAR(axis_->toUserPos(), 3000, 0.01);
  EXPECT_NEAR(axis_->toUserVel(), 0, 0.01);
  EXPECT_TRUE(move_1_.isError() == mcFALSE) << move_1_.getErrorID();
  EXPECT_TRUE(move_2_.isError() == mcFALSE) << move_2_.getErrorID();
  EXPECT_TRUE(move_3_.isError() == mcFALSE) << move_3_.getErrorID();
}

// MC_Stop issued during the Example 4 sequence.
TEST_P(MCStopAbortTest, StopAbortsBlendingLowSequence)
{
  // Keep 'Execute' high for this long after 'Done' (Figure 15, left case)
  // and then watch the axis in 'Standstill' for the same time.
  constexpr double HOLD_TIME = 1.0;

  FbMoveAbsolute* moves[3] = { &move_1_, &move_2_, &move_3_ };
  // 'Done' and 'CommandAborted' are single-cycle pulses once 'Execute' is
  // FALSE (Figure 7), so they are latched every cycle.
  bool done_before_stop[3]    = { false, false, false };
  bool done_after_stop[3]     = { false, false, false };
  bool aborted_before_stop[3] = { false, false, false };
  bool aborted_after_stop[3]  = { false, false, false };
  bool active_after_stop[3]   = { false, false, false };

  double previous_velocity      = 0;
  double stop_time              = NAN;
  double stop_velocity          = NAN;
  double stop_position          = NAN;
  double done_time              = NAN;
  double done_velocity          = NAN;
  double release_time           = NAN;
  double release_position       = NAN;
  double max_velocity_drop      = 0;
  double max_velocity_drop_t    = 0;
  double velocity_before_drop   = 0;
  double velocity_after_drop    = 0;
  double max_velocity_rise      = 0;
  double previous_acceleration  = 0;
  double max_stop_jerk          = 0;
  double max_position_drift     = 0;
  bool not_stopping_while_exec  = false;
  bool done_before_zero         = false;
  bool not_standstill_after_rel = false;
  bool moved_after_release      = false;

  while (time_ < 40.0)
  {
    runCycle();
    driveExecuteSignals();

    const double velocity     = axis_->toUserVel();
    const double acceleration = axis_->toUserAccCmd();
    if (stop_triggered_)
      max_stop_jerk = std::max(
          max_stop_jerk, fabs(acceleration - previous_acceleration) / dt_);
    previous_acceleration = acceleration;

    for (int i = 0; i < 3; i++)
    {
      const bool done    = moves[i]->isDone() == mcTRUE;
      const bool aborted = moves[i]->isAborted() == mcTRUE;
      (stop_triggered_ ? done_after_stop : done_before_stop)[i] |= done;
      (stop_triggered_ ? aborted_after_stop : aborted_before_stop)[i] |=
          aborted;
      // Allow the cycle in which MC_Stop takes over the axis.
      if (stop_triggered_ && time_ - stop_time > 2 * dt_)
        active_after_stop[i] |= moves[i]->isActive() == mcTRUE;
    }

    if (!stop_triggered_ && stopConditionReached(velocity, previous_velocity))
    {
      stop_.setExecute(mcTRUE);
      stop_triggered_   = true;
      stop_time         = time_;
      stop_velocity     = velocity;
      stop_position     = axis_->toUserPos();
      previous_velocity = velocity;
      time_ += dt_;
      continue;
    }

    if (stop_triggered_ && std::isnan(release_time))
    {
      // Ramp-down: from the stop request until 'Execute' is released.
      const double drop = previous_velocity - velocity;
      if (drop > max_velocity_drop)
      {
        max_velocity_drop    = drop;
        max_velocity_drop_t  = time_ - stop_time;
        velocity_before_drop = previous_velocity;
        velocity_after_drop  = velocity;
      }
      max_velocity_rise = std::max(max_velocity_rise, -drop);

      // 'Stopping' from activation until 'Execute' is released, also after
      // 'Done' (Figure 15).
      if (time_ - stop_time > 2 * dt_ && axis_->getAxisState() != mcStopping)
        not_stopping_while_exec = true;

      if (std::isnan(done_time) && stop_.isDone() == mcTRUE)
      {
        done_time     = time_;
        done_velocity = velocity;
        if (fabs(velocity) > 1e-3)
          done_before_zero = true;
      }

      if (!std::isnan(done_time) && time_ - done_time >= HOLD_TIME)
      {
        stop_.setExecute(mcFALSE);
        release_time     = time_;
        release_position = axis_->toUserPos();
      }
    }
    else if (!std::isnan(release_time) && time_ - release_time > 2 * dt_)
    {
      // 'Done' AND NOT 'Execute' -> 'Standstill'; the axis must not resume
      // any of the aborted blended moves.
      if (axis_->getAxisState() != mcStandstill)
        not_standstill_after_rel = true;
      if (fabs(velocity) > 1e-3)
        moved_after_release = true;
      max_position_drift = std::max(
          max_position_drift, fabs(axis_->toUserPos() - release_position));
      if (time_ - release_time >= HOLD_TIME)
        break;
    }

    previous_velocity = velocity;
    time_ += dt_;
  }

#ifdef PLOT
  const std::string name = "plcopen_example4_blending_low_" +
                           plotSuffix(stop_point_) + "_" +
                           std::to_string(static_cast<int>(frequency_)) + "hz";
  const auto signals_file = test_plot::TestPlot::filename(
      "_" + name + "_signals", "mc_stop_blending_test");
  fb_profile_.plot(signals_file, "FB", 1280, 3000);
  plt::close();
  test_plot::TestPlot::recordFile(signals_file);
  const auto motion_file = test_plot::TestPlot::filename(
      "_" + name + "_motion", "mc_stop_blending_test");
  axis_profile_.plot(motion_file);
  plt::close();
  test_plot::TestPlot::recordFile(motion_file);
#endif

  ASSERT_TRUE(stop_triggered_) << "the stop condition was never reached";

  // --- Motion diagram: jerk-limited ramp to zero -----------------------------
  // With a jerk-limited profile the velocity can change by at most
  // 'Deceleration' * cycle time per cycle. An abrupt stop shows up as a
  // single-cycle step far above that bound.
  const double max_step = STOP_DECELERATION * dt_;
  EXPECT_LE(max_stop_jerk, STOP_JERK + 1e-6);
  EXPECT_LE(max_velocity_drop, max_step * 1.05 + 1e-3)
      << "velocity dropped from " << velocity_before_drop << " to "
      << velocity_after_drop << " in one " << dt_ * 1000 << " ms cycle, "
      << max_velocity_drop_t << " s after MC_Stop (stop velocity "
      << stop_velocity << "); expected a ramp of at most " << max_step
      << " per cycle.";
  // When stopped during acceleration the velocity may only keep rising while
  // the acceleration is ramped to zero with 'Jerk'.
  EXPECT_LE(max_velocity_rise, 100 * dt_ + 1e-3);

  // --- Signal diagram ------------------------------------------------------
  // MC_Stop 'Done' exactly at velocity zero, axis 'Stopping' while 'Execute'
  // is TRUE, then 'Standstill' (Figure 15).
  EXPECT_FALSE(std::isnan(done_time)) << "MC_Stop never reported 'Done'";
  EXPECT_FALSE(done_before_zero) << "'Done' set at velocity " << done_velocity;
  EXPECT_FALSE(not_stopping_while_exec)
      << "axis left 'Stopping' while MC_Stop.Execute was TRUE";
  EXPECT_TRUE(stop_.isError() == mcFALSE) << stop_.getErrorID();
  EXPECT_TRUE(stop_.isAborted() == mcFALSE);

  // MC_Stop aborts the active FB and clears the buffer (Section 2.4.2). FBs
  // that finished before the stop keep their result.
  bool expect_done_before_stop[3] = { false, false, false };
  bool expect_aborted[3]          = { false, false, false };
  switch (stop_point_)
  {
    case StopPoint::kMove1Cruise:
    case StopPoint::kBlendEntry:
      expect_aborted[0] = expect_aborted[1] = true;
      break;
    case StopPoint::kMove2Cruise:
      expect_done_before_stop[0] = true;
      expect_aborted[1] = expect_aborted[2] = true;
      break;
    case StopPoint::kMove3Accel:
      expect_done_before_stop[0] = expect_done_before_stop[1] = true;
      expect_aborted[2]                                       = true;
      break;
    case StopPoint::kNone:
      break;
  }
  for (int i = 0; i < 3; i++)
  {
    SCOPED_TRACE("FB" + std::to_string(i + 1));
    EXPECT_EQ(done_before_stop[i], expect_done_before_stop[i]);
    EXPECT_FALSE(aborted_before_stop[i]);
    EXPECT_EQ(aborted_after_stop[i], expect_aborted[i])
        << (expect_aborted[i] ? "active or buffered FB not aborted by MC_Stop" :
                                "finished FB reported 'CommandAborted'");
    EXPECT_FALSE(done_after_stop[i]) << "FB completed after MC_Stop";
    EXPECT_FALSE(active_after_stop[i]) << "FB still active after MC_Stop";
    EXPECT_TRUE(moves[i]->isBusy() == mcFALSE);
  }

  if (std::isnan(done_time) || std::isnan(release_time))
    return;

  // Minimum time and distance of a ramp limited by 'Deceleration'.
  const double stop_duration = done_time - stop_time;
  const double min_duration  = stop_velocity / STOP_DECELERATION;
  const double max_duration =
      min_duration + 2 * STOP_DECELERATION / STOP_JERK + 0.5;
  EXPECT_GE(stop_duration, 0.95 * min_duration)
      << "the axis stopped faster than 'Deceleration' allows";
  EXPECT_LE(stop_duration, max_duration);

  const double stop_distance = fabs(release_position - stop_position);
  const double min_distance =
      stop_velocity * stop_velocity / (2 * STOP_DECELERATION);
  EXPECT_GE(stop_distance, 0.95 * min_distance)
      << "braking distance is shorter than 'Deceleration' allows";
  EXPECT_LE(stop_distance, stop_velocity * max_duration);

  EXPECT_FALSE(not_standstill_after_rel)
      << "axis not in 'Standstill' after 'Done' AND NOT 'Execute'";
  EXPECT_FALSE(moved_after_release);
  EXPECT_LE(max_position_drift, 1e-3);
}

std::string
testName(const ::testing::TestParamInfo<MCStopBlendingTest::ParamType>& info)
{
  return stopPointName(std::get<0>(info.param)) + "_" +
         std::to_string(static_cast<int>(std::get<1>(info.param))) + "Hz";
}

INSTANTIATE_TEST_SUITE_P(PLCopenExample4, BlendingLowSequenceTest,
                         ::testing::Combine(::testing::Values(StopPoint::kNone),
                                            ::testing::Values(1000.0, 500.0,
                                                              250.0)),
                         testName);

INSTANTIATE_TEST_SUITE_P(
    PLCopenExample4, MCStopAbortTest,
    ::testing::Combine(::testing::Values(StopPoint::kMove1Cruise,
                                         StopPoint::kBlendEntry,
                                         StopPoint::kMove2Cruise,
                                         StopPoint::kMove3Accel),
                       ::testing::Values(1000.0, 500.0, 250.0)),
    testName);
