// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file function_block_test.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <string>
#include <thread>
#include "gtest/gtest.h"
#include <fb/common/include/axis.hpp>
#include <fb/common/include/global.hpp>
#include <fb/public/include/fb_move_relative.hpp>
#include <fb/public/include/fb_move_velocity.hpp>
#include <fb/public/include/fb_move_absolute.hpp>
#include <fb/public/include/fb_move_additive.hpp>
#include <fb/public/include/fb_halt.hpp>
#include <fb/public/include/fb_stop.hpp>
#include <fb/public/include/fb_homing.hpp>
#include <fb/public/include/fb_power.hpp>
#include <fb/private/include/fb_set_position.hpp>
#include <fb/public/include/fb_read_actual_position.hpp>
#include <fb/private/include/fb_jog.hpp>
#include <fb/private/include/fb_cam_in.hpp>
#include <fb/private/include/fb_cam_out.hpp>
#include <fb/private/include/fb_cam_ref.hpp>
#include <fb/private/include/fb_cam_table_select.hpp>
#include <fb/private/include/fb_gear_in.hpp>
#include <fb/private/include/fb_gear_out.hpp>
#include <fb/private/include/fb_gear_in_pos.hpp>
#include <fb/private/include/fb_read_motion_state.hpp>
#include <fb/private/include/fb_set_override.hpp>
#include <fb/private/include/fb_move_superimposed.hpp>
#include <fb/private/include/fb_digital_cam_switch.hpp>

#ifdef PLOT
#include <cmath>
#include <map>
#include <type_traits>
#include <utility>
#include "test_plot.hpp"
#include <tool/fb_debug_tool.hpp>
#endif

using namespace RTmotion;

constexpr double gear_in_pos_execute_pulse_seconds = 0.1;

#ifdef PLOT
class GearInTestPlot
{
public:
  void add(const std::string& panel, const std::string& label, double time,
           double value)
  {
    plot_.add(panel, label, time, value);
  }

  void addBlock(const std::string& name, FbAxisNode& fb, double time)
  {
    add("FB signals", name + ".Execute", time, fb.isEnabled() == mcTRUE);
    add("FB signals", name + ".Active", time, fb.isActive() == mcTRUE);
    add("FB signals", name + ".Done", time, fb.isDone() == mcTRUE);
    add("FB signals", name + ".Aborted", time, fb.isAborted() == mcTRUE);
    add("FB signals", name + ".Error", time, fb.isError() != mcFALSE);
  }

  bool empty() const
  {
    return plot_.empty();
  }

  void addPositionGear(FbGearInPos& fb, Axis& master, Axis& slave, double time,
                       double target_position, double ratio)
  {
    add("Position", "Master commanded", time, master.toUserPosCmd());
    add("Position", "Slave commanded", time, slave.toUserPosCmd());
    add("Position", "Slave actual", time, slave.toUserPos());
    add("Position", "Position-lock target", time, target_position);
    add("Velocity", "Target", time, master.toUserVelCmd() * ratio);
    add("Velocity", "Slave commanded", time, slave.toUserVelCmd());
    add("Velocity", "Slave actual", time, slave.toUserVel());
    add("Acceleration", "Slave commanded", time, slave.toUserAccCmd());
    const bool coupled = fb.isPositionCoupled() == mcTRUE;
    add("Position error while coupled", "Command - target", time,
        coupled ? slave.toUserPosCmd() - target_position : NAN);
    add("Position error while coupled", "Actual - target", time,
        coupled ? slave.toUserPos() - target_position : NAN);
    add("FB signals", "PositionGear.Execute", time, fb.isEnabled() == mcTRUE);
    add("FB signals", "PositionGear.StartSync", time,
        fb.getStartSync() == mcTRUE);
    add("FB signals", "PositionGear.InSync", time, fb.getInSync() == mcTRUE);
    add("FB signals", "PositionGear.Active", time, fb.isActive() == mcTRUE);
    add("FB signals", "PositionGear.Busy", time, fb.isBusy() == mcTRUE);
    add("FB signals", "PositionGear.Aborted", time, fb.isAborted() == mcTRUE);
    add("FB signals", "PositionGear.Error", time, fb.isError() != mcFALSE);
    add("Error code", "PositionGear", time, fb.getErrorID());
    add("Error code", "Master axis", time, master.getAxisError());
    add("Error code", "Slave axis", time, slave.getAxisError());
  }

  void plot(const std::string& suffix = "", const std::string& description = "",
            const std::string& xlabel = "Time (s)") const
  {
    plot_.save("_gearin" + suffix, description, xlabel);
  }

private:
  test_plot::TestPlot plot_{ "function_block_test", 320, "FB signals" };
};

// Capture the operands, not assertion success. This also covers validation-only
// tests whose local nodes/configuration never enter a fixture's motion loop.
class FunctionBlockObservations : public ::testing::EmptyTestEventListener
{
public:
  static FunctionBlockObservations& instance()
  {
    static auto* recorder = new FunctionBlockObservations;
    return *recorder;
  }

  void OnTestStart(const ::testing::TestInfo&) override
  {
    checks_  = test_plot::TestPlot();
    signals_ = GearInTestPlot();
    samples_.clear();
    previous_.clear();
    identities_.clear();
    exercised_.clear();
  }

  void OnTestEnd(const ::testing::TestInfo&) override
  {
    checks_.save("_checks", "Observed values and comparison references",
                 "Observation index (per expression)");
    if (!signals_.empty())
      signals_.plot("_subjects", "Subjects exercised by this test",
                    "Cycle index (per subject)");
  }

  template <typename T>
  static void value(const char* expression, int line, const char* role,
                    const T& value)
  {
    if constexpr (std::is_arithmetic_v<T> || std::is_enum_v<T>)
    {
      auto& self              = instance();
      const std::string panel = "Check at line " + std::to_string(line);
      const std::string label = std::string(role) == "Observed" ?
                                    "Observed: " + std::string(expression) :
                                    role;
      const std::string key   = panel + role;
      const auto sample       = self.samples_[key]++;
      // Repeated invariants can execute hundreds of thousands of times. Keep
      // their initial samples, transitions, and regular checkpoints.
      const double numeric = static_cast<double>(value);
      auto& previous       = self.previous_[key];
      if (sample < 2 || sample % 100 == 0 || numeric != previous)
        self.checks_.add(panel, label, sample, numeric);
      previous = numeric;
    }
  }

  template <typename T>
  static const T& boolean(const char* expression, int line, const T& value,
                          bool expected)
  {
    FunctionBlockObservations::value(expression, line, "Observed", value);
    FunctionBlockObservations::value(expression, line, "Expected", expected);
    return value;
  }

  static void axis(const std::string& name, Axis& axis, double time)
  {
    auto& plot = instance().signals_;
    plot.add("Position", name + ".actual", time, axis.toUserPos());
    plot.add("Position", name + ".command", time, axis.toUserPosCmd());
    plot.add("Velocity", name + ".actual", time, axis.toUserVel());
    plot.add("Velocity", name + ".command", time, axis.toUserVelCmd());
    plot.add("Acceleration", name + ".command", time, axis.toUserAccCmd());
    plot.add("Axis state", name, time, axis.getAxisState());
    plot.add("Error code", name, time, axis.getAxisError());
  }

  static void block(const std::string& name, FbAxisNode& block, double time)
  {
    instance().signals_.addBlock(name, block, time);
    instance().signals_.add("Error code", name, time, block.getErrorID());
  }

  template <typename T>
  static void cycle(T& subject, const std::string& requested_name)
  {
    auto& self          = instance();
    auto& identities    = self.identities_[requested_name];
    const auto inserted = identities.emplace(&subject, identities.size());
    const std::string name =
        requested_name + "[" + std::to_string(inserted.first->second) + "]";
    const double cycle = self.samples_["Cycle:" + name]++;
    if constexpr (std::is_base_of_v<FbAxisNode, T>)
    {
      // A fixture also cycles its default gear when a test uses a local block.
      // Do not mistake that unused block for the subject under test.
      bool& exercised = self.exercised_[name];
      exercised |=
          subject.isEnabled() == mcTRUE || subject.isActive() == mcTRUE ||
          subject.isBusy() == mcTRUE || subject.isDone() == mcTRUE ||
          subject.isAborted() == mcTRUE || subject.isError() != mcFALSE;
      if (!exercised)
        return;
    }
    if constexpr (std::is_base_of_v<Axis, T>)
      axis(name, subject, cycle);
    if constexpr (std::is_base_of_v<FbAxisNode, T>)
    {
      block(name, subject, cycle);
      self.signals_.add("FB signals", name + ".Busy", cycle,
                        subject.isBusy() == mcTRUE);
    }
    if constexpr (std::is_base_of_v<FbAxisAdmin, T>)
    {
      self.signals_.add("FB signals", name + ".Enable", cycle,
                        subject.isEnabled() == mcTRUE);
      self.signals_.add("FB signals", name + ".Done", cycle,
                        subject.isDone() == mcTRUE);
      self.signals_.add("FB signals", name + ".Busy", cycle,
                        subject.isBusy() == mcTRUE);
      self.signals_.add("FB signals", name + ".Valid", cycle,
                        subject.isValid() == mcTRUE);
      self.signals_.add("FB signals", name + ".Error", cycle,
                        subject.isError() != mcFALSE);
      self.signals_.add("Error code", name, cycle, subject.getErrorID());
    }
    if constexpr (std::is_base_of_v<FbPower, T>)
      self.signals_.add("FB signals", name + ".Power", cycle,
                        subject.getPowerStatus() == mcTRUE);
    if constexpr (std::is_base_of_v<FbAxisRead, T>)
      self.signals_.add("Read value", name, cycle, subject.getFloatValue());
    if constexpr (std::is_base_of_v<FbGearInPos, T>)
    {
      self.signals_.add("FB signals", name + ".StartSync", cycle,
                        subject.getStartSync() == mcTRUE);
      self.signals_.add("FB signals", name + ".InSync", cycle,
                        subject.getInSync() == mcTRUE);
    }
    else if constexpr (std::is_base_of_v<FbGearIn, T>)
      self.signals_.add("FB signals", name + ".InGear", cycle,
                        subject.getInGear() == mcTRUE);
    if constexpr (std::is_base_of_v<FbReadMotionState, T>)
    {
      self.signals_.add("FB signals", name + ".ConstantVelocity", cycle,
                        subject.getConstantVelocity() == mcTRUE);
      self.signals_.add("FB signals", name + ".Accelerating", cycle,
                        subject.getAccelerating() == mcTRUE);
      self.signals_.add("FB signals", name + ".Decelerating", cycle,
                        subject.getDecelerating() == mcTRUE);
      self.signals_.add("FB signals", name + ".Positive", cycle,
                        subject.getDirectionPositive() == mcTRUE);
      self.signals_.add("FB signals", name + ".Negative", cycle,
                        subject.getDirectionNegative() == mcTRUE);
    }
    if constexpr (std::is_base_of_v<FbDigitalCamSwitch, T>)
      self.signals_.add("FB signals", name + ".InOperation", cycle,
                        subject.isInOperation() == mcTRUE);
  }

  static void commands(double position, double velocity, double acceleration,
                       double target_velocity    = NAN,
                       double acceleration_limit = NAN)
  {
    auto& self         = instance();
    const double cycle = self.samples_["Node commands"]++;
    self.signals_.add("Position", "Node command", cycle, position);
    self.signals_.add("Velocity", "Node command", cycle, velocity);
    if (std::isfinite(target_velocity))
      self.signals_.add("Velocity", "Target", cycle, target_velocity);
    self.signals_.add("Acceleration", "Node command", cycle, acceleration);
    if (std::isfinite(acceleration_limit))
    {
      self.signals_.add("Acceleration", "Upper limit", cycle,
                        acceleration_limit);
      self.signals_.add("Acceleration", "Lower limit", cycle,
                        -acceleration_limit);
    }
  }

private:
  test_plot::TestPlot checks_;
  GearInTestPlot signals_;
  std::map<std::string, size_t> samples_;
  std::map<std::string, double> previous_;
  std::map<std::string, std::map<const void*, size_t>> identities_;
  std::map<std::string, bool> exercised_;
};

const bool function_block_observations_registered = [] {
  ::testing::UnitTest::GetInstance()->listeners().Append(
      &FunctionBlockObservations::instance());
  return true;
}();

// GoogleTest still owns evaluation, diagnostics, streaming, and fatal returns;
// each operand is evaluated exactly once, including calls with side effects.
#undef EXPECT_PRED_FORMAT2
#undef ASSERT_PRED_FORMAT2
#define FB_PLOT_PRED2(pred, v1, v2, failure)                                   \
  GTEST_PRED_FORMAT2_(                                                         \
      ([&](const char* e1, const char* e2, const auto& a, const auto& b) {     \
        FunctionBlockObservations::value(e1, __LINE__, "Observed", a);         \
        FunctionBlockObservations::value(e1, __LINE__, "Reference: " #v2, b);  \
        return pred(e1, e2, a, b);                                             \
      }),                                                                      \
      v1, v2, failure)
#define EXPECT_PRED_FORMAT2(pred, v1, v2)                                      \
  FB_PLOT_PRED2(pred, v1, v2, GTEST_NONFATAL_FAILURE_)
#define ASSERT_PRED_FORMAT2(pred, v1, v2)                                      \
  FB_PLOT_PRED2(pred, v1, v2, GTEST_FATAL_FAILURE_)

#undef EXPECT_PRED_FORMAT3
#undef ASSERT_PRED_FORMAT3
#define FB_PLOT_PRED3(pred, v1, v2, v3, failure)                               \
  GTEST_PRED_FORMAT3_(                                                         \
      ([&](const char* e1, const char* e2, const char* e3, const auto& a,      \
           const auto& b, const auto& tolerance) {                             \
        FunctionBlockObservations::value(e1, __LINE__, "Observed", a);         \
        FunctionBlockObservations::value(e1, __LINE__, "Expected", b);         \
        FunctionBlockObservations::value(e1, __LINE__, "Tolerance",            \
                                         tolerance);                           \
        return pred(e1, e2, e3, a, b, tolerance);                              \
      }),                                                                      \
      v1, v2, v3, failure)
#define EXPECT_PRED_FORMAT3(pred, v1, v2, v3)                                  \
  FB_PLOT_PRED3(pred, v1, v2, v3, GTEST_NONFATAL_FAILURE_)
#define ASSERT_PRED_FORMAT3(pred, v1, v2, v3)                                  \
  FB_PLOT_PRED3(pred, v1, v2, v3, GTEST_FATAL_FAILURE_)

#undef EXPECT_TRUE
#undef EXPECT_FALSE
#undef ASSERT_TRUE
#undef ASSERT_FALSE
#define EXPECT_TRUE(value)                                                     \
  GTEST_EXPECT_TRUE(                                                           \
      FunctionBlockObservations::boolean(#value, __LINE__, (value), true))
#define EXPECT_FALSE(value)                                                    \
  GTEST_EXPECT_FALSE(                                                          \
      FunctionBlockObservations::boolean(#value, __LINE__, (value), false))
#define ASSERT_TRUE(value)                                                     \
  GTEST_ASSERT_TRUE(                                                           \
      FunctionBlockObservations::boolean(#value, __LINE__, (value), true))
#define ASSERT_FALSE(value)                                                    \
  GTEST_ASSERT_FALSE(                                                          \
      FunctionBlockObservations::boolean(#value, __LINE__, (value), false))

template <typename Profile, typename... Args>
void plotProfile(Profile& profile, const std::string& suffix, Args&&... args)
{
  const auto file = test_plot::TestPlot::filename("_" + suffix);
  profile.plot(file, std::forward<Args>(args)...);
  plt::close();
  test_plot::TestPlot::recordFile(file);
}
#endif

template <typename T>
void runObservedCycle(T& subject, const char* name)
{
  subject.runCycle();
#ifdef PLOT
  FunctionBlockObservations::cycle(subject, name);
#else
  (void)name;
#endif
}

template <typename MotionBlock>
class ZeroJerkMotionBlock : public MotionBlock
{
public:
  ZeroJerkMotionBlock()
  {
    this->setVelocity(100);
    this->setAcceleration(100);
    this->setDeceleration(100);
    this->jerk_ = 0;
  }
};

TEST(MotionLimitTest, RejectZeroJerkBeforeAxisAccess)
{
  ZeroJerkMotionBlock<FbStop> stop;
  ZeroJerkMotionBlock<FbHalt> halt;
  ZeroJerkMotionBlock<FbGearInPos> gear_in_pos;
  ZeroJerkMotionBlock<FbJog> jog;
  ZeroJerkMotionBlock<FbCamOut> cam_out;
  ZeroJerkMotionBlock<FbGearOut> gear_out;

  EXPECT_EQ(stop.onRisingEdgeExecution(), mcErrorCodeMotionLimitUnset);
  EXPECT_EQ(halt.onRisingEdgeExecution(), mcErrorCodeMotionLimitUnset);
  const auto gear_error = gear_in_pos.onRisingEdgeExecution();
  EXPECT_EQ(gear_error, mcErrorCodeMotionLimitError);
  Axis master, slave;
  gear_in_pos.setMaster(&master);
  gear_in_pos.setSlave(&slave);
#ifdef PLOT
  GearInTestPlot plot;
#endif
  constexpr int pulse_cycles =
      static_cast<int>(gear_in_pos_execute_pulse_seconds * 1000);
  for (int cycle = 0; cycle < pulse_cycles + 2; ++cycle)
  {
    gear_in_pos.setExecute(cycle >= 1 && cycle <= pulse_cycles ? mcTRUE :
                                                                 mcFALSE);
    runObservedCycle(gear_in_pos, "gear_in_pos");
    if (cycle >= 1 && cycle <= pulse_cycles)
    {
      EXPECT_EQ(gear_in_pos.isError(), mcTRUE);
      EXPECT_EQ(gear_in_pos.getErrorID(), mcErrorCodeMotionLimitError);
    }
    EXPECT_EQ(gear_in_pos.isBusy(), mcFALSE);
    EXPECT_EQ(gear_in_pos.isActive(), mcFALSE);
#ifdef PLOT
    plot.addBlock("PositionGear", gear_in_pos, cycle * 0.001);
    plot.add("Error code", "GearInPos error", cycle * 0.001,
             gear_in_pos.getErrorID());
#endif
  }
  EXPECT_EQ(gear_in_pos.isEnabled(), mcFALSE);
#ifdef PLOT
  plot.plot("_GearInPos", "Zero jerk rejected on an Execute pulse");
#endif
  jog.setJogForwardSignal(mcTRUE);
  EXPECT_EQ(jog.onExecution(), mcErrorCodeMotionLimitUnset);
  EXPECT_EQ(cam_out.onRisingEdgeExecution(), mcErrorCodeMotionLimitUnset);
  EXPECT_EQ(gear_out.onRisingEdgeExecution(), mcErrorCodeMotionLimitUnset);
}

class FunctionBlockTest : public ::testing::Test
{
protected:
  // You can remove any or all of the following functions if their bodies would
  // be empty.

  FunctionBlockTest()
  {
    // You can do set-up work for each test here.
  }

  ~FunctionBlockTest() override
  {
    // You can do clean-up work that doesn't throw exceptions here.
  }

  // If the constructor and destructor are not enough for setting up
  // and cleaning up each test, you can define the following methods:

  void SetUp() override
  {
    // Code here will be called immediately after the constructor (right
    // before each test).
  }

  void TearDown() override
  {
    // Code here will be called immediately after each test (right
    // before the destructor).
  }

  void runBlendingExample(MC_BUFFER_MODE buffer_mode,
                          double second_acceleration,
                          double expected_velocity_at_1000,
                          double expected_velocity_at_2000,
                          const std::string& plot_name)
  {
#ifdef PLOT
    fb_profile_.reset();
    axis_profile_.reset();
#endif

    AxisConfig config;
    AXIS_REF axis = new Axis();
    axis->setAxisId(1);
    axis->setNodeQueueSize(3);
    axis->setAxisConfig(&config);

    Servo* servo = new Servo();
    axis->setServo(servo);

    FbPower fb_power;
    fb_power.setAxis(axis);
    fb_power.setEnable(mcTRUE);
    fb_power.setEnablePositive(mcTRUE);
    fb_power.setEnableNegative(mcTRUE);

    FbSetPosition set_position;
    set_position.setAxis(axis);
    set_position.setMode(mcSetPositionModeAbsolute);
    set_position.setPosition(0);
    set_position.setEnable(mcFALSE);

    FbMoveAbsolute move_1;
    move_1.setAxis(axis);
    move_1.setPosition(1000);
    move_1.setVelocity(100);
    move_1.setAcceleration(100);
    move_1.setDeceleration(100);
    move_1.setBufferMode(mcAborting);

    FbMoveAbsolute move_2;
    move_2.setAxis(axis);
    move_2.setPosition(2000);
    move_2.setVelocity(50);
    move_2.setAcceleration(second_acceleration);
    move_2.setDeceleration(second_acceleration);
    move_2.setBufferMode(buffer_mode);

    FbMoveAbsolute move_3;
    move_3.setAxis(axis);
    move_3.setPosition(3000);
    move_3.setVelocity(100);
    move_3.setAcceleration(100);
    move_3.setDeceleration(100);
    move_3.setBufferMode(buffer_mode);

#ifdef PLOT
    fb_profile_.addFB("move_1");
    fb_profile_.addFB("move_2");
    fb_profile_.addFB("move_3");
    fb_profile_.addItemName("move_1.execute");
    fb_profile_.addItemName("move_1.busy");
    fb_profile_.addItemName("move_1.done");
    fb_profile_.addItemName("move_1.command_aborted");
    fb_profile_.addItemName("move_1.active");
    fb_profile_.addItemName("move_2.execute");
    fb_profile_.addItemName("move_2.busy");
    fb_profile_.addItemName("move_2.done");
    fb_profile_.addItemName("move_2.command_aborted");
    fb_profile_.addItemName("move_2.active");
    fb_profile_.addItemName("move_3.execute");
    fb_profile_.addItemName("move_3.busy");
    fb_profile_.addItemName("move_3.done");
    fb_profile_.addItemName("move_3.command_aborted");
    fb_profile_.addItemName("move_3.active");
#endif

    bool set_position_started                          = false;
    bool move_1_started                                = false;
    bool move_2_started                                = false;
    bool move_3_started                                = false;
    bool sampled_1000                                  = false;
    bool sampled_2000                                  = false;
    bool move_3_done                                   = false;
    double move_1_start_time                           = -1;
    double move_2_start_time                           = -1;
    double move_3_start_time                           = -1;
    double velocity_when_move_2_active                 = NAN;
    double velocity_when_move_3_active                 = NAN;
    double velocity_at_1000                            = 0;
    double velocity_at_2000                            = 0;
    double previous_velocity                           = 0;
    double max_velocity_step                           = 0;
    double max_velocity_step_time                      = 0;
    double velocity_before_max_step                    = 0;
    double velocity_after_max_step                     = 0;
    double move_2_cruise_duration                      = 0;
    double minimum_move_2_velocity                     = INFINITY;
    double minimum_move_2_actual_velocity              = INFINITY;
    double minimum_velocity_after_move_3_start         = INFINITY;
    double high_velocity_before_move_3_active_duration = 0;
    double time                                        = 0;

    while (time < 70.0)
    {
      runObservedCycle(*axis, "axis");
      runObservedCycle(fb_power, "fb_power");
      runObservedCycle(set_position, "set_position");
      runObservedCycle(move_1, "move_1");
      runObservedCycle(move_2, "move_2");
      runObservedCycle(move_3, "move_3");

      const double velocity_step = fabs(axis->toUserVel() - previous_velocity);
      if (velocity_step > max_velocity_step)
      {
        max_velocity_step        = velocity_step;
        max_velocity_step_time   = time;
        velocity_before_max_step = previous_velocity;
        velocity_after_max_step  = axis->toUserVel();
      }
      previous_velocity = axis->toUserVel();

      if (!set_position_started && fb_power.getPowerStatus() == mcTRUE)
      {
        set_position.setEnable(mcTRUE);
        set_position_started = true;
      }

      if (!move_1_started && set_position.isEnabled() == mcTRUE)
      {
        move_1.setExecute(mcTRUE);
        move_1_started    = true;
        move_1_start_time = time;
      }
      else if (move_1.isEnabled() == mcTRUE && time - move_1_start_time >= 0.5)
      {
        move_1.setExecute(mcFALSE);
      }

      if (!move_2_started && axis->toUserPos() >= 500)
      {
        move_2.setExecute(mcTRUE);
        move_2_started    = true;
        move_2_start_time = time;
      }
      else if (move_2.isEnabled() == mcTRUE && time - move_2_start_time >= 0.5)
      {
        move_2.setExecute(mcFALSE);
      }

      if (!move_3_started && axis->toUserPos() >= 1500 &&
          move_2.isActive() == mcTRUE)
      {
        move_3.setExecute(mcTRUE);
        move_3_started    = true;
        move_3_start_time = time;
      }
      else if (move_3.isEnabled() == mcTRUE && time - move_3_start_time >= 0.5)
      {
        move_3.setExecute(mcFALSE);
      }

      if (isnan(velocity_when_move_2_active) && move_2.isActive() == mcTRUE)
        velocity_when_move_2_active = axis->toUserVel();
      if (move_2.isActive() == mcTRUE &&
          fabs(axis->toUserVelCmd() - 50.0) <= 1.0)
        move_2_cruise_duration += 0.001;
      if (move_2.isActive() == mcTRUE)
      {
        // Guard both the planner command and the signal used by motion plots
        // against an undershoot during the 100-to-50 blend entry.
        minimum_move_2_velocity =
            std::min(minimum_move_2_velocity, axis->toUserVelCmd());
        minimum_move_2_actual_velocity =
            std::min(minimum_move_2_actual_velocity, axis->toUserVel());
      }
      if (move_3_started && move_2.isActive() == mcTRUE)
      {
        // Early look-ahead must not erase FB2's 50-unit cruise segment.
        minimum_velocity_after_move_3_start =
            std::min(minimum_velocity_after_move_3_start, axis->toUserVelCmd());
        if (axis->toUserVelCmd() >= expected_velocity_at_2000 - 1.0)
          high_velocity_before_move_3_active_duration += 0.001;
      }
      if (isnan(velocity_when_move_3_active) && move_3.isActive() == mcTRUE)
        velocity_when_move_3_active = axis->toUserVel();

      if (!sampled_1000 && move_1.isDone() == mcTRUE)
      {
        velocity_at_1000 = axis->toUserVelCmd();
        sampled_1000     = true;
      }
      else if (axis->toUserPos() >= 990 && axis->toUserPos() < 1000)
      {
        velocity_at_1000 = axis->toUserVel();
        sampled_1000     = true;
      }
      if (!sampled_2000 && move_2.isDone() == mcTRUE)
      {
        velocity_at_2000 = axis->toUserVelCmd();
        sampled_2000     = true;
      }
      else if (!sampled_2000 && move_3.isActive() == mcTRUE)
      {
        velocity_at_2000 = axis->toUserVelCmd();
        sampled_2000     = true;
      }
      else if (axis->toUserPos() >= 1990 && axis->toUserPos() < 2000)
      {
        velocity_at_2000 = axis->toUserVel();
        sampled_2000     = true;
      }

#ifdef PLOT
      axis_profile_.addState(axis->toUserPos(), axis->toUserVel(),
                             axis->toUserAccCmd(), time);
      fb_profile_.addState("move_1.execute", move_1.isEnabled() == mcTRUE);
      fb_profile_.addState("move_1.busy", move_1.isBusy() == mcTRUE);
      fb_profile_.addState("move_1.done", move_1.isDone() == mcTRUE);
      fb_profile_.addState("move_1.command_aborted",
                           move_1.isAborted() == mcTRUE);
      fb_profile_.addState("move_1.active", move_1.isActive() == mcTRUE);
      fb_profile_.addState("move_2.execute", move_2.isEnabled() == mcTRUE);
      fb_profile_.addState("move_2.busy", move_2.isBusy() == mcTRUE);
      fb_profile_.addState("move_2.done", move_2.isDone() == mcTRUE);
      fb_profile_.addState("move_2.command_aborted",
                           move_2.isAborted() == mcTRUE);
      fb_profile_.addState("move_2.active", move_2.isActive() == mcTRUE);
      fb_profile_.addState("move_3.execute", move_3.isEnabled() == mcTRUE);
      fb_profile_.addState("move_3.busy", move_3.isBusy() == mcTRUE);
      fb_profile_.addState("move_3.done", move_3.isDone() == mcTRUE);
      fb_profile_.addState("move_3.command_aborted",
                           move_3.isAborted() == mcTRUE);
      fb_profile_.addState("move_3.active", move_3.isActive() == mcTRUE);
      fb_profile_.addTime(time);
#endif

      if (move_3.isDone() == mcTRUE)
      {
        move_3_done = true;
        break;
      }
      time += 0.001;
    }

#ifdef PLOT
    plotProfile(fb_profile_, plot_name + "_signals", "Move", 1280, 2400);
    plotProfile(axis_profile_, plot_name + "_motion");
#endif

    EXPECT_TRUE(sampled_1000);
    EXPECT_TRUE(sampled_2000);
    EXPECT_TRUE(move_3_done);
    EXPECT_NEAR(velocity_at_1000, expected_velocity_at_1000, 1.0);
    EXPECT_NEAR(velocity_at_2000, expected_velocity_at_2000, 1.0);
    EXPECT_NEAR(velocity_when_move_2_active, expected_velocity_at_1000, 1.0);
    EXPECT_NEAR(velocity_when_move_3_active, expected_velocity_at_2000, 1.0);
    EXPECT_GT(move_2_cruise_duration, 1.0);
    EXPECT_GE(minimum_move_2_velocity, 49.999);
    EXPECT_GE(minimum_move_2_actual_velocity, 49.999);
    if (expected_velocity_at_2000 > move_2.getVelocity())
    {
      EXPECT_GE(minimum_velocity_after_move_3_start,
                move_2.getVelocity() - 1.0);
      EXPECT_LT(high_velocity_before_move_3_active_duration, 0.05);
    }
    EXPECT_LE(max_velocity_step,
              std::max(second_acceleration, 100.0) * 0.001 + 0.01)
        << "at t=" << max_velocity_step_time << ", velocity changed from "
        << velocity_before_max_step << " to " << velocity_after_max_step;
    EXPECT_NEAR(axis->toUserPos(), 3000, 0.01);
    EXPECT_NEAR(axis->toUserVel(), 0, 0.01);
    EXPECT_TRUE(move_1.isError() == mcFALSE) << move_1.getErrorID();
    EXPECT_TRUE(move_2.isError() == mcFALSE) << move_2.getErrorID();
    EXPECT_TRUE(move_3.isError() == mcFALSE) << move_3.getErrorID();
    EXPECT_TRUE(move_1.isAborted() == mcFALSE);
    EXPECT_TRUE(move_2.isAborted() == mcFALSE);
    EXPECT_TRUE(move_3.isAborted() == mcFALSE);

    delete servo;
    delete axis;
  }

  // PLCopen Part 1 Version 2.0, Section 3.3, Figure 15: MC_Stop timing
  // diagram. The axis cruises with MC_MoveVelocity and is ramped down by
  // MC_Stop. With 'release_before_done' = false, 'Execute' is held after
  // 'Done' (left side of Figure 15), otherwise it is released while the axis
  // is still decelerating (right side of Figure 15).
  void runStopTimingDiagram(double frequency, bool release_before_done,
                            const std::string& plot_name)
  {
#ifdef PLOT
    fb_profile_.reset();
    axis_profile_.reset();
#endif
    const double dt                = 1.0 / frequency;
    const double cruise_velocity   = 50;
    const double stop_deceleration = 20;
    const double stop_jerk         = 200;

    AxisConfig config;
    config.frequency_ = frequency;
    AXIS_REF axis     = new Axis();
    axis->setAxisId(1);
    axis->setAxisConfig(&config);

    Servo* servo = new Servo();
    axis->setServo(servo);

    FbPower fb_power;
    fb_power.setAxis(axis);
    fb_power.setEnable(mcTRUE);
    fb_power.setEnablePositive(mcTRUE);
    fb_power.setEnableNegative(mcTRUE);

    FbMoveVelocity move_vel;
    move_vel.setAxis(axis);
    move_vel.setVelocity(cruise_velocity);
    move_vel.setAcceleration(50);
    move_vel.setDeceleration(50);
    move_vel.setJerk(500);
    move_vel.setBufferMode(mcAborting);

    FbStop stop;
    stop.setAxis(axis);
    stop.setDeceleration(stop_deceleration);
    stop.setJerk(stop_jerk);

#ifdef PLOT
    fb_profile_.addFB("stop");
    fb_profile_.addFB("axis");
    fb_profile_.addItemName("stop.execute");
    fb_profile_.addItemName("stop.busy");
    fb_profile_.addItemName("stop.done");
    fb_profile_.addItemName("stop.command_aborted");
    fb_profile_.addItemName("axis.stopping");
    fb_profile_.addItemName("axis.standstill");
#endif

    double time                  = 0;
    double stop_time             = NAN;
    double stop_velocity         = NAN;
    double stop_position         = NAN;
    double done_time             = NAN;
    double release_time          = NAN;
    double done_off_time         = NAN;
    double standstill_time       = NAN;
    double previous_velocity     = 0;
    double max_velocity_drop     = 0;
    double max_velocity_drop_t   = 0;
    double velocity_before_drop  = 0;
    double velocity_after_drop   = 0;
    bool in_velocity_before_stop = false;
    bool done_before_zero        = false;
    bool done_dropped_while_exec = false;
    bool left_stopping_early     = false;

    while (time < 12.0)
    {
      axis->runCycle();
      fb_power.runCycle();
      move_vel.runCycle();
      stop.runCycle();

      const double velocity = axis->toUserVel();

      if (move_vel.isEnabled() == mcFALSE &&
          fb_power.getPowerStatus() == mcTRUE && std::isnan(stop_time))
        move_vel.setExecute(mcTRUE);
      in_velocity_before_stop |= std::isnan(stop_time) &&
                                 move_vel.isInVelocity() == mcTRUE;

      if (std::isnan(stop_time) && time >= 3.0)
      {
        stop.setExecute(mcTRUE);
        stop_time     = time;
        stop_velocity = velocity;
        stop_position = axis->toUserPos();
      }
      else if (!std::isnan(stop_time))
      {
        const double drop = previous_velocity - velocity;
        if (std::isnan(done_time) && drop > max_velocity_drop)
        {
          max_velocity_drop    = drop;
          max_velocity_drop_t  = time - stop_time;
          velocity_before_drop = previous_velocity;
          velocity_after_drop  = velocity;
        }

        if (std::isnan(done_time) && stop.isDone() == mcTRUE)
        {
          done_time        = time;
          done_before_zero = fabs(velocity) > 1e-3;
        }
        if (!std::isnan(done_time) && std::isnan(done_off_time) &&
            stop.isDone() == mcFALSE)
        {
          done_off_time = time;
          if (std::isnan(release_time))
            done_dropped_while_exec = true;
        }

        // Figure 15: 'Stopping' while 'Execute' is TRUE or velocity zero is
        // not yet reached.
        const bool must_be_stopping = std::isnan(release_time) ||
                                      std::isnan(done_time);
        if (time - stop_time > 2 * dt && must_be_stopping &&
            axis->getAxisState() != mcStopping)
          left_stopping_early = true;
        if (std::isnan(standstill_time) && axis->getAxisState() == mcStandstill)
          standstill_time = time;

        const bool release = release_before_done ? time - stop_time >= 0.5 :
                                                   !std::isnan(done_time) &&
                                                       time - done_time >= 1.0;
        if (std::isnan(release_time) && release)
        {
          stop.setExecute(mcFALSE);
          release_time = time;
        }
      }
      previous_velocity = velocity;

#ifdef PLOT
      axis_profile_.addState(axis->toUserPos(), velocity, axis->toUserAccCmd(),
                             time);
      fb_profile_.addState("stop.execute", stop.isEnabled() == mcTRUE);
      fb_profile_.addState("stop.busy", stop.isBusy() == mcTRUE);
      fb_profile_.addState("stop.done", stop.isDone() == mcTRUE);
      fb_profile_.addState("stop.command_aborted", stop.isAborted() == mcTRUE);
      fb_profile_.addState("axis.stopping", axis->getAxisState() == mcStopping);
      fb_profile_.addState("axis.standstill",
                           axis->getAxisState() == mcStandstill);
      fb_profile_.addTime(time);
#endif
      time += dt;
    }

#ifdef PLOT
    plotProfile(fb_profile_, plot_name + "_signals", "FB", 1280, 1440);
    plotProfile(axis_profile_, plot_name + "_motion");
#endif

    EXPECT_TRUE(in_velocity_before_stop);
    EXPECT_NEAR(stop_velocity, cruise_velocity, 0.01);

    // Motion: velocity ramps down with 'Deceleration', no single-cycle step.
    const double max_step = stop_deceleration * dt;
    EXPECT_LE(max_velocity_drop, max_step * 1.05 + 1e-3)
        << "velocity dropped from " << velocity_before_drop << " to "
        << velocity_after_drop << " in one " << dt * 1000 << " ms cycle, "
        << max_velocity_drop_t << " s after MC_Stop; expected at most "
        << max_step << " per cycle.";

    // Signals: 'Done' when velocity zero is reached.
    ASSERT_FALSE(std::isnan(done_time)) << "MC_Stop never reported 'Done'";
    EXPECT_FALSE(done_before_zero);
    const double min_duration = cruise_velocity / stop_deceleration;
    EXPECT_GE(done_time - stop_time, 0.95 * min_duration)
        << "the axis stopped faster than 'Deceleration' allows";
    EXPECT_LE(done_time - stop_time,
              min_duration + 2 * stop_deceleration / stop_jerk + 0.5);
    EXPECT_GE(fabs(axis->toUserPos() - stop_position),
              0.95 * cruise_velocity * cruise_velocity /
                  (2 * stop_deceleration))
        << "braking distance is shorter than 'Deceleration' allows";
    EXPECT_FALSE(left_stopping_early)
        << "axis left 'Stopping' while 'Execute' was TRUE or before velocity "
           "zero";
    EXPECT_FALSE(done_dropped_while_exec)
        << "'Done' reset while 'Execute' was still TRUE";

    // 'Done' AND NOT 'Execute' -> 'Standstill'.
    ASSERT_FALSE(std::isnan(release_time));
    ASSERT_FALSE(std::isnan(standstill_time));
    EXPECT_GE(standstill_time, std::max(release_time, done_time));
    EXPECT_LE(standstill_time - std::max(release_time, done_time), 2 * dt);
    EXPECT_FALSE(std::isnan(done_off_time)) << "'Done' never reset";
    EXPECT_EQ(axis->getAxisState(), mcStandstill);
    EXPECT_NEAR(axis->toUserVel(), 0, 1e-3);
    EXPECT_TRUE(stop.isError() == mcFALSE) << stop.getErrorID();
    EXPECT_TRUE(move_vel.isAborted() == mcTRUE);

    delete servo;
    delete axis;
  }

  // PLCopen Part 1 Version 2.0, Section 3.3, Figure 16: MC_Stop in
  // combination with MC_MoveVelocity.
  //  a) A rotating axis is ramped down with MC_Stop.
  //  b) The axis rejects motion commands as long as MC_Stop 'Execute' is
  //     TRUE; MC_MoveVelocity reports an error.
  void runStopWithMoveVelocity(double frequency, const std::string& plot_name)
  {
#ifdef PLOT
    fb_profile_.reset();
    axis_profile_.reset();
#endif
    const double dt                = 1.0 / frequency;
    const double cruise_velocity   = 50;
    const double stop_deceleration = 20;
    // Figure 16 uses 'Jerk' = 0 (no jerk limit), which this implementation
    // rejects, so steep jerk values are used instead.
    const double stop_jerk = 200;

    AxisConfig config;
    config.frequency_ = frequency;
    AXIS_REF axis     = new Axis();
    axis->setAxisId(1);
    axis->setAxisConfig(&config);

    Servo* servo = new Servo();
    axis->setServo(servo);

    FbPower fb_power;
    fb_power.setAxis(axis);
    fb_power.setEnable(mcTRUE);
    fb_power.setEnablePositive(mcTRUE);
    fb_power.setEnableNegative(mcTRUE);

    FbMoveVelocity move_vel;
    move_vel.setAxis(axis);
    move_vel.setContinuousUpdate(mcFALSE);
    move_vel.setVelocity(cruise_velocity);
    move_vel.setAcceleration(10);
    move_vel.setDeceleration(10);
    move_vel.setJerk(100);
    move_vel.setDirection(mcPositiveDirection);
    move_vel.setBufferMode(mcAborting);

    FbStop stop;
    stop.setAxis(axis);
    stop.setDeceleration(stop_deceleration);
    stop.setJerk(stop_jerk);

#ifdef PLOT
    fb_profile_.addFB("move_vel");
    fb_profile_.addFB("stop");
    fb_profile_.addItemName("move_vel.execute");
    fb_profile_.addItemName("move_vel.in_velocity");
    fb_profile_.addItemName("move_vel.command_aborted");
    fb_profile_.addItemName("move_vel.error");
    fb_profile_.addItemName("stop.execute");
    fb_profile_.addItemName("stop.done");
#endif

    // Figure 16 'Execute' edges.
    const double stop_rise        = 7.0;   // Exe_2 rises during a)
    const double move_fall        = 8.0;   // Exe_1 falls (aborted)
    const double move_rejected    = 11.0;  // Exe_1 rises during b)
    const double stop_fall        = 13.0;  // Exe_2 falls
    const double move_error_reset = 14.0;  // Exe_1 falls, error reset
    const double move_restart     = 15.0;  // Exe_1 rises again

    double time                  = 0;
    double stop_time             = NAN;
    double stop_velocity         = NAN;
    double stop_position         = NAN;
    double done_time             = NAN;
    double done_position         = NAN;
    double previous_velocity     = 0;
    double max_velocity_drop     = 0;
    double max_velocity_drop_t   = 0;
    double velocity_before_drop  = 0;
    double velocity_after_drop   = 0;
    double max_drift_while_stop  = 0;
    bool in_velocity_before_stop = false;
    bool aborted_by_stop         = false;
    bool in_velocity_during_stop = false;
    bool rejected_with_error     = false;
    bool done_before_zero        = false;
    bool done_dropped_while_exec = false;
    bool left_stopping_early     = false;
    bool standstill_after_stop   = false;
    bool error_after_reset       = false;

    while (time < 22.0)
    {
      axis->runCycle();
      fb_power.runCycle();
      move_vel.runCycle();
      stop.runCycle();

      const double velocity = axis->toUserVel();

      // FB1 'Exe_1'
      if (fb_power.getPowerStatus() == mcTRUE &&
          (time < move_fall ||
           (time >= move_rejected && time < move_error_reset) ||
           time >= move_restart))
        move_vel.setExecute(mcTRUE);
      else
        move_vel.setExecute(mcFALSE);

      // FB2 'Exe_2'
      if (std::isnan(stop_time) && time >= stop_rise)
      {
        stop.setExecute(mcTRUE);
        stop_time     = time;
        stop_velocity = velocity;
        stop_position = axis->toUserPos();
      }
      else if (time >= stop_fall)
        stop.setExecute(mcFALSE);

      if (std::isnan(stop_time))
        in_velocity_before_stop |= move_vel.isInVelocity() == mcTRUE;
      else if (time < stop_fall)
      {
        // a) ramp-down
        const double drop = previous_velocity - velocity;
        if (std::isnan(done_time) && drop > max_velocity_drop)
        {
          max_velocity_drop    = drop;
          max_velocity_drop_t  = time - stop_time;
          velocity_before_drop = previous_velocity;
          velocity_after_drop  = velocity;
        }
        aborted_by_stop |= move_vel.isAborted() == mcTRUE;
        in_velocity_during_stop |= time - stop_time > 2 * dt &&
                                   move_vel.isInVelocity() == mcTRUE;
        if (time - stop_time > 2 * dt && axis->getAxisState() != mcStopping)
          left_stopping_early = true;

        if (std::isnan(done_time) && stop.isDone() == mcTRUE)
        {
          done_time        = time;
          done_position    = axis->toUserPos();
          done_before_zero = fabs(velocity) > 1e-3;
        }
        if (!std::isnan(done_time))
        {
          done_dropped_while_exec |= stop.isDone() == mcFALSE;
          max_drift_while_stop = std::max(
              max_drift_while_stop, fabs(axis->toUserPos() - done_position));
        }

        // b) motion command rejected while MC_Stop 'Execute' is TRUE
        if (time >= move_rejected)
          rejected_with_error |= move_vel.isError() == mcTRUE;
      }
      else if (time < move_restart)
      {
        standstill_after_stop |= axis->getAxisState() == mcStandstill;
        if (time > move_error_reset + 2 * dt)
          error_after_reset |= move_vel.isError() == mcTRUE;
      }
      previous_velocity = velocity;

#ifdef PLOT
      axis_profile_.addState(axis->toUserPos(), velocity, axis->toUserAccCmd(),
                             time);
      fb_profile_.addState("move_vel.execute", move_vel.isEnabled() == mcTRUE);
      fb_profile_.addState("move_vel.in_velocity",
                           move_vel.isInVelocity() == mcTRUE);
      fb_profile_.addState("move_vel.command_aborted",
                           move_vel.isAborted() == mcTRUE);
      fb_profile_.addState("move_vel.error", move_vel.isError() == mcTRUE);
      fb_profile_.addState("stop.execute", stop.isEnabled() == mcTRUE);
      fb_profile_.addState("stop.done", stop.isDone() == mcTRUE);
      fb_profile_.addTime(time);
#endif
      time += dt;
    }

#ifdef PLOT
    plotProfile(fb_profile_, plot_name + "_signals", "FB", 1280, 1440);
    plotProfile(axis_profile_, plot_name + "_motion");
#endif

    // a) InVel_1 before the stop, Abort_1 when MC_Stop takes over.
    EXPECT_TRUE(in_velocity_before_stop);
    EXPECT_NEAR(stop_velocity, cruise_velocity, 0.01);
    EXPECT_TRUE(aborted_by_stop) << "MC_MoveVelocity not aborted by MC_Stop";
    EXPECT_FALSE(in_velocity_during_stop);

    // a) Velocity ramps down with 'Deceleration', no single-cycle step.
    const double max_step = stop_deceleration * dt;
    EXPECT_LE(max_velocity_drop, max_step * 1.05 + 1e-3)
        << "velocity dropped from " << velocity_before_drop << " to "
        << velocity_after_drop << " in one " << dt * 1000 << " ms cycle, "
        << max_velocity_drop_t << " s after MC_Stop; expected at most "
        << max_step << " per cycle.";
    ASSERT_FALSE(std::isnan(done_time)) << "MC_Stop never reported 'Done'";
    EXPECT_FALSE(done_before_zero);
    const double min_duration = cruise_velocity / stop_deceleration;
    EXPECT_GE(done_time - stop_time, 0.95 * min_duration)
        << "the axis stopped faster than 'Deceleration' allows";
    EXPECT_LE(done_time - stop_time,
              min_duration + 2 * stop_deceleration / stop_jerk + 0.5);
    EXPECT_GE(done_position - stop_position, 0.95 * cruise_velocity *
                                                 cruise_velocity /
                                                 (2 * stop_deceleration))
        << "braking distance is shorter than 'Deceleration' allows";
    EXPECT_FALSE(left_stopping_early)
        << "axis left 'Stopping' while MC_Stop.Execute was TRUE";
    EXPECT_FALSE(done_dropped_while_exec)
        << "'Done_2' reset while 'Exe_2' was still TRUE";

    // b) MC_MoveVelocity rejected with an error, the axis does not move.
    EXPECT_TRUE(rejected_with_error)
        << "MC_MoveVelocity accepted while MC_Stop.Execute was TRUE";
    EXPECT_LE(max_drift_while_stop, 1e-3);

    // 'Done_2' AND NOT 'Exe_2' -> 'Standstill'; motion is accepted again.
    EXPECT_TRUE(standstill_after_stop);
    EXPECT_FALSE(error_after_reset);
    EXPECT_TRUE(move_vel.isInVelocity() == mcTRUE);
    EXPECT_NEAR(axis->toUserVel(), cruise_velocity, 0.01);
    EXPECT_TRUE(stop.isError() == mcFALSE) << stop.getErrorID();

    delete servo;
    delete axis;
  }

#ifdef PLOT
  AxisProfile axis_profile_;
  FBDigitalProfile fb_profile_;
#endif
};

// PLCopen Part 1 Version 2.0, Appendix A, Examples 4-7.
TEST_F(FunctionBlockTest, MC_BlendingLow)
{
  runBlendingExample(mcBlendingLow, 50, 50, 50,
                     "plcopen_example4_blending_low");
}

TEST_F(FunctionBlockTest, MC_BlendingPrevious)
{
  runBlendingExample(mcBlendingPrevious, 200, 100, 50,
                     "plcopen_example5_blending_previous");
}

TEST_F(FunctionBlockTest, MC_BlendingNext)
{
  runBlendingExample(mcBlendingNext, 50, 50, 100,
                     "plcopen_example6_blending_next");
}

TEST_F(FunctionBlockTest, MC_BlendingHigh)
{
  runBlendingExample(mcBlendingHigh, 200, 100, 100,
                     "plcopen_example7_blending_high");
}

// Test MC_MoveRelative
TEST_F(FunctionBlockTest, DemoRelative)
{
#ifdef PLOT
  fb_profile_.reset();
  axis_profile_.reset();
#endif

  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbMoveRelative fb_move_rel;
  fb_move_rel.setAxis(axis);
  fb_move_rel.setExecute(mcFALSE);
  fb_move_rel.setContinuousUpdate(mcFALSE);
  fb_move_rel.setDistance(3.14);
  fb_move_rel.setVelocity(1.57);
  fb_move_rel.setAcceleration(3.14);
  fb_move_rel.setDeceleration(3.14);
  fb_move_rel.setJerk(50);
  printf("Function block initialized.\n");

  double timeout = 0;
  while (fb_move_rel.isDone() == mcFALSE && timeout < 5)
  {
    runObservedCycle(*axis, "axis");
    runObservedCycle(fb_power, "fb_power");
    runObservedCycle(fb_move_rel, "fb_move_rel");
    timeout += 0.001;
#ifdef PLOT
    axis_profile_.addState(axis->toUserPos(), axis->toUserVel(),
                           axis->toUserAccCmd(), timeout);
#endif

    if (fb_move_rel.isEnabled() == mcFALSE &&
        fb_power.getPowerStatus() == mcTRUE)
    {
      fb_move_rel.setExecute(mcTRUE);
      // printf("Axis powered on %d\n", fb_power.getPowerStatus() == mcTRUE);
    }

    // printf("Run time: %f, pos: %lf, vel: %lf\n", timeout, axis->toUserPos(),
    //        axis->toUserVel());
  }
#ifdef PLOT
  plotProfile(axis_profile_, "DemoRelative");
#endif
  ASSERT_TRUE(fb_move_rel.isDone() == mcTRUE);
  ASSERT_LT(fabs(axis->toUserPos() - 3.14), 0.01);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_MoveVelocity
TEST_F(FunctionBlockTest, DemoVelocity)
{
#ifdef PLOT
  fb_profile_.reset();
  axis_profile_.reset();
#endif

  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbMoveVelocity fb_move_vel;
  fb_move_vel.setAxis(axis);
  fb_move_vel.setExecute(mcFALSE);
  fb_move_vel.setContinuousUpdate(mcFALSE);
  fb_move_vel.setVelocity(1.57);
  fb_move_vel.setAcceleration(3.14);
  fb_move_vel.setDeceleration(3.14);
  fb_move_vel.setJerk(50);
  printf("Function block initialized.\n");

  double timeout = 0;
  while (fb_move_vel.isInVelocity() == mcFALSE && timeout < 5.0)
  {
    runObservedCycle(*axis, "axis");
    runObservedCycle(fb_power, "fb_power");
    runObservedCycle(fb_move_vel, "fb_move_vel");
    timeout += 0.001;

#ifdef PLOT
    axis_profile_.addState(axis->toUserPos(), axis->toUserVel(),
                           axis->toUserAccCmd(), timeout);
#endif

    if (fb_move_vel.isEnabled() == mcFALSE &&
        fb_power.getPowerStatus() == mcTRUE)
    {
      fb_move_vel.setExecute(mcTRUE);
      // printf("Axis powered on %d\n", fb_power.getPowerStatus() == mcTRUE);
    }

    // printf("Run time: %f, pos: %lf, vel: %lf\n", timeout, axis->toUserPos(),
    //         axis->toUserVel());
  }
#ifdef PLOT
  plotProfile(axis_profile_, "DemoVelocity");
#endif
  ASSERT_TRUE(fb_move_vel.isInVelocity() == mcTRUE);
  ASSERT_LT(fabs(axis->toUserVel() - 1.57), 0.01);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_Stop
TEST_F(FunctionBlockTest, MC_Stop)
{
#ifdef PLOT
  fb_profile_.reset();
  axis_profile_.reset();
#endif

  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbMoveVelocity move_vel;
  move_vel.setAxis(axis);
  move_vel.setVelocity(50);
  move_vel.setAcceleration(10);
  move_vel.setDeceleration(10);
  move_vel.setJerk(5000);
  move_vel.setBufferMode(mcAborting);

  FbStop stop;
  stop.setAxis(axis);
  stop.setAcceleration(20);
  stop.setDeceleration(20);
  stop.setJerk(5000);
#ifdef PLOT
  fb_profile_.addFB("mov_vel");
  fb_profile_.addFB("stop");
  fb_profile_.addItemName("mov_vel.execute");
  fb_profile_.addItemName("mov_vel.inVel");
  fb_profile_.addItemName("mov_vel.abort");
  fb_profile_.addItemName("mov_vel.error");
  fb_profile_.addItemName("stop.execute");
  fb_profile_.addItemName("stop.done");
#endif
  double time_out = 25;
  double t        = 0;
  while (t < time_out)
  {
    runObservedCycle(*axis, "axis");
    runObservedCycle(fb_power, "fb_power");
    runObservedCycle(move_vel, "move_vel");
    runObservedCycle(stop, "stop");

    if (move_vel.isEnabled() == mcFALSE && t < 7.5)
    {  //使能成功后move1开始移动
      std::cout << "axis poweron, mov_vel start" << std::endl;
      move_vel.setExecute(mcTRUE);
    }

    if (6 < t && t < 12.5 && stop.isEnabled() == mcFALSE)
      stop.setExecute(mcTRUE);

    if (12.5 < t && stop.isEnabled() == mcTRUE)
      stop.setExecute(mcFALSE);

    if (7.5 < t && t < 10 && move_vel.isEnabled() == mcTRUE)
      move_vel.setExecute(mcFALSE);

    if (10 < t && t < 15 && move_vel.isEnabled() == mcFALSE)
      move_vel.setExecute(mcTRUE);

    if (15 < t && t < 20 && move_vel.isEnabled() == mcTRUE)
      move_vel.setExecute(mcFALSE);

    if (17.5 < t && move_vel.isEnabled() == mcFALSE)
      move_vel.setExecute(mcTRUE);
#ifdef PLOT
    axis_profile_.addState(axis->toUserPos(), axis->toUserVel(),
                           axis->toUserAccCmd(), t);
    fb_profile_.addState("mov_vel.execute", move_vel.isEnabled() == mcTRUE);
    fb_profile_.addState("mov_vel.inVel", move_vel.isInVelocity() == mcTRUE);
    fb_profile_.addState("mov_vel.abort", move_vel.isAborted() == mcTRUE);
    fb_profile_.addState("mov_vel.error", move_vel.isError() == mcTRUE);
    fb_profile_.addState("stop.execute", stop.isEnabled() == mcTRUE);
    fb_profile_.addState("stop.done", stop.isDone() == mcTRUE);
    fb_profile_.addTime(t);
#endif
    // printf("Run time: %f, pos: %f, vel: %f\n", t, axis->toUserPos(),
    // axis->toUserVel());
    t += 0.001;
  }
#ifdef PLOT
  plotProfile(axis_profile_, "mc_stop_axis");
  plotProfile(fb_profile_, "mc_stop_fb");
#endif
  ASSERT_TRUE(move_vel.isInVelocity() == mcTRUE);
  ASSERT_LT(fabs(axis->toUserVel() - 50), 0.01);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// PLCopen Part 1 Version 2.0, Section 3.3, Figure 15. The ramp-down must be
// jerk limited at every axis cycle rate, not only at 1 kHz.
TEST_F(FunctionBlockTest, MC_StopFigure15ExecuteHeld_1000Hz)
{
  runStopTimingDiagram(1000, false,
                       "plcopen_figure15_mc_stop_execute_held_1000hz");
}

TEST_F(FunctionBlockTest, MC_StopFigure15ExecuteHeld_500Hz)
{
  runStopTimingDiagram(500, false,
                       "plcopen_figure15_mc_stop_execute_held_500hz");
}

TEST_F(FunctionBlockTest, MC_StopFigure15ExecuteReleased_1000Hz)
{
  runStopTimingDiagram(1000, true,
                       "plcopen_figure15_mc_stop_execute_released_1000hz");
}

TEST_F(FunctionBlockTest, MC_StopFigure15ExecuteReleased_500Hz)
{
  runStopTimingDiagram(500, true,
                       "plcopen_figure15_mc_stop_execute_released_500hz");
}

// PLCopen Part 1 Version 2.0, Section 3.3, Figure 16.
TEST_F(FunctionBlockTest, MC_StopFigure16MoveVelocity_1000Hz)
{
  runStopWithMoveVelocity(1000,
                          "plcopen_figure16_mc_stop_move_velocity_1000hz");
}

TEST_F(FunctionBlockTest, MC_StopFigure16MoveVelocity_500Hz)
{
  runStopWithMoveVelocity(500, "plcopen_figure16_mc_stop_move_velocity_500hz");
}

TEST_F(FunctionBlockTest, MC_StopFigure16MoveVelocity_250Hz)
{
  runStopWithMoveVelocity(250, "plcopen_figure16_mc_stop_move_velocity_250hz");
}

// Test MC_Halt
TEST_F(FunctionBlockTest, MC_Halt)
{
#ifdef PLOT
  fb_profile_.reset();
  axis_profile_.reset();
#endif
  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbMoveVelocity move_vel;
  move_vel.setAxis(axis);
  move_vel.setVelocity(50);
  move_vel.setAcceleration(10);
  move_vel.setDeceleration(10);
  move_vel.setJerk(50);
  move_vel.setBufferMode(mcAborting);

  FbHalt halt;
  halt.setAxis(axis);
  halt.setAcceleration(5);
  halt.setJerk(50);
  halt.setBufferMode(mcAborting);
#ifdef PLOT
  fb_profile_.addFB("mov_vel");
  fb_profile_.addFB("halt");
  fb_profile_.addItemName("mov_vel.execute");
  fb_profile_.addItemName("mov_vel.inVel");
  fb_profile_.addItemName("mov_vel.abort");
  fb_profile_.addItemName("halt.execute");
  fb_profile_.addItemName("halt.done");
  fb_profile_.addItemName("halt.abort");
#endif
  double time_out = 40;
  double t        = 0;
  while (t < time_out)
  {
    runObservedCycle(*axis, "axis");
    runObservedCycle(fb_power, "fb_power");
    runObservedCycle(move_vel, "move_vel");
    runObservedCycle(halt, "halt");

    if (move_vel.isEnabled() == mcFALSE && t < 7.5)
    {  //使能成功后move1开始移动
      std::cout << "axis poweron, mov_vel start" << std::endl;
      move_vel.setExecute(mcTRUE);
    }

    if (8.5 < t && t < 19 && move_vel.isEnabled() == mcTRUE)
      move_vel.setExecute(mcFALSE);

    if (19 < t && t < 21.5 && move_vel.isEnabled() == mcFALSE)
      move_vel.setExecute(mcTRUE);

    if (21.5 < t && t < 32.5 && move_vel.isEnabled() == mcTRUE)
      move_vel.setExecute(mcFALSE);

    if (32.5 < t && move_vel.isEnabled() == mcFALSE)
      move_vel.setExecute(mcTRUE);

    if (7 < t && t < 17.5 && halt.isEnabled() == mcFALSE)
      halt.setExecute(mcTRUE);

    if (17.5 < t && t < 27.5 && halt.isEnabled() == mcTRUE)
      halt.setExecute(mcFALSE);

    if (27.5 < t && t < 37.5 && halt.isEnabled() == mcFALSE)
      halt.setExecute(mcTRUE);

    if (37.5 < t && halt.isEnabled() == mcTRUE)
      halt.setExecute(mcFALSE);
#ifdef PLOT
    axis_profile_.addState(axis->toUserPos(), axis->toUserVel(),
                           axis->toUserAccCmd(), t);
    fb_profile_.addState("mov_vel.execute", move_vel.isEnabled() == mcTRUE);
    fb_profile_.addState("mov_vel.inVel", move_vel.isInVelocity() == mcTRUE);
    fb_profile_.addState("mov_vel.abort", move_vel.isAborted() == mcTRUE);
    fb_profile_.addState("halt.execute", halt.isEnabled() == mcTRUE);
    fb_profile_.addState("halt.done", halt.isDone() == mcTRUE);
    fb_profile_.addState("halt.abort", halt.isAborted() == mcTRUE);
    fb_profile_.addTime(t);
#endif
    // printf("Run time: %f, pos: %f, vel: %f\n", t, axis->toUserPos(),
    // axis->toUserVel());
    t += 0.001;
  }
#ifdef PLOT
  plotProfile(axis_profile_, "mc_halt_axis");
  plotProfile(fb_profile_, "mc_halt_fb");
#endif
  ASSERT_TRUE(move_vel.isInVelocity() == mcTRUE);
  ASSERT_LT(fabs(axis->toUserVel() - 50), 0.01);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_MoveAbsolute
TEST_F(FunctionBlockTest, MC_MoveAbsolute)
{
#ifdef PLOT
  fb_profile_.reset();
  axis_profile_.reset();
#endif
  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbMoveAbsolute move_abs1;
  move_abs1.setAxis(axis);
  move_abs1.setPosition(600);
  move_abs1.setVelocity(300);
  move_abs1.setAcceleration(500);
  move_abs1.setDeceleration(500);
  move_abs1.setJerk(5000);

  FbMoveAbsolute move_abs2;
  move_abs2.setAxis(axis);
  move_abs2.setPosition(1000);
  move_abs2.setVelocity(200);
  move_abs2.setAcceleration(500);
  move_abs2.setDeceleration(500);
  move_abs2.setJerk(5000);
  move_abs2.setBufferMode(mcAborting);

  FbSetPosition set_position1;
  set_position1.setAxis(axis);
  set_position1.setMode(mcSetPositionModeRelative);
  set_position1.setPosition(0);

#ifdef PLOT
  fb_profile_.addFB("move_abs1");
  fb_profile_.addFB("move_abs2");
  fb_profile_.addItemName("move_abs1.go");
  fb_profile_.addItemName("move_abs1.done");
  fb_profile_.addItemName("move_abs1.aborted");
  fb_profile_.addItemName("move_abs2.test");
  fb_profile_.addItemName("move_abs2.finish");
#endif
  double time_out = 7;
  double t        = 0;
  while (t < time_out)
  {
    //功能块调用
    runObservedCycle(*axis, "axis");
    runObservedCycle(fb_power, "fb_power");
    runObservedCycle(set_position1, "set_position1");
    runObservedCycle(move_abs1, "move_abs1");
    runObservedCycle(move_abs2, "move_abs2");

    if (set_position1.isEnabled() == mcFALSE &&
        fb_power.getPowerStatus() == mcTRUE && t < 2)
    {
      std::cout << "axis poweron, set position" << std::endl;
      set_position1.setEnable(mcTRUE);
    }

    if (set_position1.isEnabled() == mcTRUE &&
        move_abs1.isEnabled() == mcFALSE && t < 2)
    {  //使能成功后move1开始移动
      std::cout << "axis poweron, move_abs1 start" << std::endl;
      move_abs1.setExecute(mcTRUE);
    }

    if (2 < t && move_abs1.isEnabled() == mcTRUE)
      move_abs1.setExecute(mcFALSE);

    if (1 < t && t < 6 && move_abs2.isEnabled() == mcFALSE)
      move_abs2.setExecute(mcTRUE);

    if (6 < t && move_abs2.isEnabled() == mcTRUE)
      move_abs2.setExecute(mcFALSE);
#ifdef PLOT
    axis_profile_.addState(axis->toUserPos(), axis->toUserVel(),
                           axis->toUserAccCmd(), t);
    fb_profile_.addState("move_abs1.go", move_abs1.isEnabled() == mcTRUE);
    fb_profile_.addState("move_abs1.done", move_abs1.isDone() == mcTRUE);
    fb_profile_.addState("move_abs1.aborted", move_abs1.isAborted() == mcTRUE);
    fb_profile_.addState("move_abs2.test", move_abs2.isEnabled() == mcTRUE);
    fb_profile_.addState("move_abs2.finish", move_abs2.isDone() == mcTRUE);
    fb_profile_.addTime(t);
#endif
    // printf("Run time: %f, pos: %f, vel: %f\n", t, axis->toUserPos(),
    // axis->toUserVel());
    t += 0.001;
  }
#ifdef PLOT
  plotProfile(axis_profile_, "mc_move_abs_axis");
  plotProfile(fb_profile_, "mc_move_abs_fb");
#endif
  ASSERT_LT(fabs(axis->toUserVel() - 0.0), 0.01);
  ASSERT_LT(fabs(axis->toUserPos() - 1000), 0.01);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_MoveRelative
TEST_F(FunctionBlockTest, MC_MoveRelative)
{
#ifdef PLOT
  fb_profile_.reset();
  axis_profile_.reset();
#endif
  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbMoveRelative fb_move_rel_1, fb_move_rel_2;
  fb_move_rel_1.setAxis(axis);
  fb_move_rel_1.setContinuousUpdate(mcFALSE);
  fb_move_rel_1.setDistance(600);
  fb_move_rel_1.setVelocity(300);
  fb_move_rel_1.setAcceleration(500);
  fb_move_rel_1.setDeceleration(500);
  fb_move_rel_1.setJerk(5000);

  fb_move_rel_2.setAxis(axis);
  fb_move_rel_2.setContinuousUpdate(mcFALSE);
  fb_move_rel_2.setDistance(400);
  fb_move_rel_2.setVelocity(200);
  fb_move_rel_2.setAcceleration(500);
  fb_move_rel_2.setDeceleration(500);
  fb_move_rel_2.setJerk(5000);
  fb_move_rel_2.setBufferMode(mcAborting);
#ifdef PLOT
  fb_profile_.addFB("fb_move_rel_1");
  fb_profile_.addFB("fb_move_rel_2");
  fb_profile_.addItemName("fb_move_rel_1.go");
  fb_profile_.addItemName("fb_move_rel_1.done");
  fb_profile_.addItemName("fb_move_rel_1.aborted");
  fb_profile_.addItemName("fb_move_rel_2.test");
  fb_profile_.addItemName("fb_move_rel_2.finish");
#endif
  double time_out = 4;
  double t        = 0;
  double pos_tmp  = 0;
  mcBOOL trigger  = mcFALSE;
  while (t < time_out)
  {
    runObservedCycle(*axis, "axis");
    runObservedCycle(fb_power, "fb_power");
    runObservedCycle(fb_move_rel_1, "fb_move_rel_1");
    runObservedCycle(fb_move_rel_2, "fb_move_rel_2");
    if (trigger == mcTRUE)
    {
      pos_tmp = axis->toUserPos();
      trigger = mcFALSE;
    }

    if (fb_move_rel_1.isEnabled() == mcFALSE && t < 2)
    {
      // After enabled, move_relative_1 start to move
      fb_move_rel_1.setExecute(mcTRUE);
      std::cout << "axis poweron, fb_move_rel_1 start" << std::endl;
    }

    if (2 < t && fb_move_rel_1.isEnabled() == mcTRUE)
      fb_move_rel_1.setExecute(mcFALSE);

    if (1 < t && t < 3.8 && fb_move_rel_2.isEnabled() == mcFALSE)
    {
      fb_move_rel_2.setExecute(mcTRUE);
      trigger = mcTRUE;
    }

    if (3.8 < t && fb_move_rel_2.isEnabled() == mcTRUE)
      fb_move_rel_2.setExecute(mcFALSE);
#ifdef PLOT
    axis_profile_.addState(axis->toUserPos(), axis->toUserVel(),
                           axis->toUserAccCmd(), t);
    fb_profile_.addState("fb_move_rel_1.go",
                         fb_move_rel_1.isEnabled() == mcTRUE);
    fb_profile_.addState("fb_move_rel_1.done",
                         fb_move_rel_1.isDone() == mcTRUE);
    fb_profile_.addState("fb_move_rel_1.aborted",
                         fb_move_rel_1.isAborted() == mcTRUE);
    fb_profile_.addState("fb_move_rel_2.test",
                         fb_move_rel_2.isEnabled() == mcTRUE);
    fb_profile_.addState("fb_move_rel_2.finish",
                         fb_move_rel_2.isDone() == mcTRUE);
    fb_profile_.addTime(t);
#endif
    t += 0.001;
    // printf("Run time: %f, pos: %f, vel: %f\n", t, axis->toUserPos(),
    // axis->toUserVel());
  }
#ifdef PLOT
  plotProfile(axis_profile_, "mc_mov_rel_axis");
  plotProfile(fb_profile_, "mc_mov_rel_fb");
#endif
  ASSERT_LT(fabs(axis->toUserVel() - 0.0), 0.01);
  ASSERT_LT(fabs(axis->toUserPos() - (pos_tmp + 400)), 0.01);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_MoveAdditive
TEST_F(FunctionBlockTest, MC_MoveAdditive)
{
#ifdef PLOT
  fb_profile_.reset();
  axis_profile_.reset();
#endif
  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbMoveAbsolute move_abs1;
  move_abs1.setAxis(axis);
  move_abs1.setPosition(600);
  move_abs1.setVelocity(300);
  move_abs1.setAcceleration(500);
  move_abs1.setDeceleration(500);
  move_abs1.setJerk(5000);
  move_abs1.setDirection(mcPositiveDirection);

  FbMoveAdditive move_add2;
  move_add2.setAxis(axis);
  move_add2.setDistance(400);
  move_add2.setVelocity(200);
  move_add2.setAcceleration(500);
  move_add2.setDeceleration(500);
  move_add2.setJerk(5000);
  move_add2.setBufferMode(mcAborting);

  FbSetPosition set_position1;
  set_position1.setAxis(axis);
  set_position1.setMode(mcSetPositionModeRelative);
  set_position1.setPosition(0);

#ifdef PLOT
  fb_profile_.addFB("move_abs1");
  fb_profile_.addFB("move_add2");
  fb_profile_.addItemName("move_abs1.go");
  fb_profile_.addItemName("move_abs1.done");
  fb_profile_.addItemName("move_abs1.aborted");
  fb_profile_.addItemName("move_add2.test");
  fb_profile_.addItemName("move_add2.finish");
#endif
  double time_out = 7;
  double t        = 0;
  while (t < time_out)
  {
    runObservedCycle(*axis, "axis");
    runObservedCycle(fb_power, "fb_power");
    runObservedCycle(set_position1, "set_position1");
    runObservedCycle(move_abs1, "move_abs1");
    runObservedCycle(move_add2, "move_add2");

    if (set_position1.isEnabled() == mcFALSE &&
        fb_power.getPowerStatus() == mcTRUE)
    {
      std::cout << "axis poweron, set position" << std::endl;
      set_position1.setEnable(mcTRUE);
    }

    if (set_position1.isEnabled() == mcTRUE &&
        move_abs1.isEnabled() == mcFALSE && t < 2)
    {  //使能成功后move1开始移动
      std::cout << "axis poweron, move_abs1 start" << std::endl;
      move_abs1.setExecute(mcTRUE);
    }

    if (2 < t && move_abs1.isEnabled() == mcTRUE)
      move_abs1.setExecute(mcFALSE);

    if (1 < t && t < 6 && move_add2.isEnabled() == mcFALSE)
    {
      move_add2.setExecute(mcTRUE);
    }

    if (6 < t && move_add2.isEnabled() == mcTRUE)
      move_add2.setExecute(mcFALSE);
#ifdef PLOT
    axis_profile_.addState(axis->toUserPos(), axis->toUserVel(),
                           axis->toUserAccCmd(), t);
    fb_profile_.addState("move_abs1.go", move_abs1.isEnabled() == mcTRUE);
    fb_profile_.addState("move_abs1.done", move_abs1.isDone() == mcTRUE);
    fb_profile_.addState("move_abs1.aborted", move_abs1.isAborted() == mcTRUE);
    fb_profile_.addState("move_add2.test", move_add2.isEnabled() == mcTRUE);
    fb_profile_.addState("move_add2.finish", move_add2.isDone() == mcTRUE);
    fb_profile_.addTime(t);
#endif
    t += 0.001;
    // printf("Run time: %f, pos: %f, vel: %f\n", t, axis->toUserPos(),
    // axis->toUserVel());
  }
#ifdef PLOT
  plotProfile(axis_profile_, "mc_moveAdd_axis");
  plotProfile(fb_profile_, "mc_moveAdd_fb");
#endif
  ASSERT_LT(fabs(axis->toUserVel() - 0.0), 0.01);
  ASSERT_LT(fabs(axis->toUserPos() - (600 + 400)), 0.01);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_MoveVelocity
TEST_F(FunctionBlockTest, MC_MoveVelocity)
{
#ifdef PLOT
  fb_profile_.reset();
  axis_profile_.reset();
#endif
  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbMoveVelocity mov_vel1;
  mov_vel1.setAxis(axis);
  mov_vel1.setVelocity(500);
  mov_vel1.setAcceleration(500);
  mov_vel1.setDeceleration(500);
  mov_vel1.setJerk(5000);
  mov_vel1.setBufferMode(mcAborting);

  FbMoveVelocity mov_vel2;
  mov_vel2.setAxis(axis);
  mov_vel2.setVelocity(200);
  mov_vel2.setAcceleration(500);
  mov_vel2.setDeceleration(500);
  mov_vel2.setJerk(5000);
  mov_vel2.setBufferMode(mcAborting);
#ifdef PLOT
  fb_profile_.addFB("mov_vel1");
  fb_profile_.addFB("mov_vel2");
  fb_profile_.addItemName("mov_vel1.go");
  fb_profile_.addItemName("mov_vel1.inVel");
  fb_profile_.addItemName("mov_vel1.aborted");
  fb_profile_.addItemName("mov_vel1.next");
  fb_profile_.addItemName("mov_vel2.test");
  fb_profile_.addItemName("mov_vel2.finish");
#endif
  double time_out = 9;
  double t        = 0;
  mcBOOL next = mcFALSE, test = mcFALSE;
  while (t < time_out)
  {
    runObservedCycle(*axis, "axis");
    runObservedCycle(fb_power, "fb_power");
    runObservedCycle(mov_vel1, "mov_vel1");
    runObservedCycle(mov_vel2, "mov_vel2");

    if (mov_vel1.isEnabled() == mcFALSE && t < 5)
    {  //使能成功后move1开始移动
      std::cout << "axis poweron, mov_vel1 start" << std::endl;
      mov_vel1.setExecute(mcTRUE);
    }

    if (5 < t && t < 6 && mov_vel1.isEnabled() == mcTRUE)
      mov_vel1.setExecute(mcFALSE);

    if (6 < t && t < 8 && mov_vel1.isEnabled() == mcFALSE)
      mov_vel1.setExecute(mcTRUE);

    if (8 < t && mov_vel1.isEnabled() == mcTRUE)
      mov_vel1.setExecute(mcFALSE);

    if (2 < t && t < 4 && next == mcFALSE)
    {
      next = mcTRUE;
      mov_vel2.setExecute(next);
    }

    if (4 < t && next == mcTRUE)
    {
      next = mcFALSE;
      mov_vel2.setExecute(mcFALSE);
    }

    if (6.5 < t && t < 8.5 && test == mcFALSE)
    {
      test = mcTRUE;
      mov_vel2.setExecute(test);
    }

    if (8.5 < t && test == mcTRUE)
    {
      test = mcFALSE;
      mov_vel2.setExecute(test);
    }
#ifdef PLOT
    axis_profile_.addState(axis->toUserPos(), axis->toUserVel(),
                           axis->toUserAccCmd(), t);
    fb_profile_.addState("mov_vel1.go", mov_vel1.isEnabled() == mcTRUE);
    fb_profile_.addState("mov_vel1.inVel", mov_vel1.isDone() == mcTRUE);
    fb_profile_.addState("mov_vel1.aborted", mov_vel1.isAborted() == mcTRUE);
    fb_profile_.addState("mov_vel1.next", next == mcTRUE);
    fb_profile_.addState("mov_vel2.test", test == mcTRUE);
    fb_profile_.addState("mov_vel2.finish", mov_vel2.isDone() == mcTRUE);
    fb_profile_.addTime(t);
#endif
    t += 0.001;
    // printf("Run time: %f, pos: %f, vel: %f\n", t, axis->toUserPos(),
    // axis->toUserVel());
  }
#ifdef PLOT
  plotProfile(axis_profile_, "mc_mov_vel_axis");
  plotProfile(fb_profile_, "mc_mov_vel_fb");
#endif
  ASSERT_LT(fabs(axis->toUserVel() - 200), 0.01);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_SetPosition
TEST_F(FunctionBlockTest, MC_SetPosition1)
{
  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbMoveAbsolute move_abs1;
  move_abs1.setAxis(axis);
  move_abs1.setPosition(600);
  move_abs1.setVelocity(300);
  move_abs1.setAcceleration(500);
  move_abs1.setDeceleration(500);
  move_abs1.setJerk(5000);

  FbMoveAbsolute move_abs2;
  move_abs2.setAxis(axis);
  move_abs2.setPosition(100);
  move_abs2.setVelocity(300);
  move_abs2.setAcceleration(500);
  move_abs2.setDeceleration(500);
  move_abs2.setJerk(5000);

  FbSetPosition set_position1;
  set_position1.setAxis(axis);
  set_position1.setMode(mcSetPositionModeAbsolute);
  set_position1.setPosition(0);

  FbReadActualPosition read_actual_pos1;
  read_actual_pos1.setAxis(axis);
  read_actual_pos1.setEnable(mcTRUE);

  double time_out = 5;
  double t        = 0;
  while (t < time_out)
  {
    //功能块调用
    runObservedCycle(*axis, "axis");
    runObservedCycle(fb_power, "fb_power");
    runObservedCycle(set_position1, "set_position1");
    runObservedCycle(move_abs1, "move_abs1");
    runObservedCycle(move_abs2, "move_abs2");
    runObservedCycle(read_actual_pos1, "read_actual_pos1");

    if (set_position1.isEnabled() == mcFALSE &&
        fb_power.getPowerStatus() == mcTRUE && t < 0.5)
    {
      std::cout << "axis poweron, set position" << std::endl;
      set_position1.setEnable(mcTRUE);
    }

    if (move_abs1.isEnabled() == mcFALSE && t > 0.5)
    {  //使能成功后move1开始移动
      std::cout << "axis poweron, move_abs1 start" << std::endl;
      move_abs1.setExecute(mcTRUE);
      set_position1.setEnable(mcFALSE);
    }

    if (read_actual_pos1.getFloatValue() >= 100 &&
        set_position1.isEnabled() == mcFALSE)
    {  //当位置抵达100时，设置POS为300
      std::cout << "axis reach 100, setPosition1 start" << std::endl;
      set_position1.setPosition(300);
      set_position1.setEnable(mcTRUE);
    }

    if (move_abs1.isDone() == mcTRUE && move_abs2.isEnabled() == mcFALSE)
      move_abs2.setExecute(mcTRUE);  //当位置抵达600时，触发第二个功能块到100

    // printf("Run time: %ld, usr pos: %f, act pos: %f\n", t, axis->toUserPos(),
    // axis->getPos());
    t += 0.001;
  }

  ASSERT_LT(fabs(axis->toUserVel() - 0.0), 0.01);
  ASSERT_LT(fabs(axis->toUserPos() - 100), 0.5);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_SetPosition
TEST_F(FunctionBlockTest, MC_SetPosition2)
{
  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbMoveRelative move_rel1;
  move_rel1.setAxis(axis);
  move_rel1.setPosition(600);
  move_rel1.setVelocity(300);
  move_rel1.setAcceleration(500);
  move_rel1.setDeceleration(500);
  move_rel1.setJerk(5000);

  FbMoveRelative move_rel2;
  move_rel2.setAxis(axis);
  move_rel2.setPosition(100);
  move_rel2.setVelocity(300);
  move_rel2.setAcceleration(500);
  move_rel2.setDeceleration(500);
  move_rel2.setJerk(5000);

  FbSetPosition set_position1;
  set_position1.setAxis(axis);
  set_position1.setMode(mcSetPositionModeAbsolute);
  set_position1.setPosition(300);

  FbReadActualPosition read_actual_pos1;
  read_actual_pos1.setAxis(axis);
  read_actual_pos1.setEnable(mcTRUE);

  double time_out = 5;
  double t        = 0;
  while (t < time_out)
  {
    //功能块调用
    runObservedCycle(*axis, "axis");
    runObservedCycle(fb_power, "fb_power");
    runObservedCycle(move_rel1, "move_rel1");
    runObservedCycle(move_rel2, "move_rel2");
    runObservedCycle(set_position1, "set_position1");
    runObservedCycle(read_actual_pos1, "read_actual_pos1");

    if (move_rel1.isEnabled() == mcFALSE)
    {  //使能成功后move1开始移动
      std::cout << "axis poweron, moveRel1 start" << std::endl;
      move_rel1.setExecute(mcTRUE);
    }

    if (read_actual_pos1.getFloatValue() >= 100 &&
        set_position1.isEnabled() == mcFALSE)
    {  //当位置抵达100时，设置POS为300
      std::cout << "axis reach 100, setPosition1 start" << std::endl;
      set_position1.setEnable(mcTRUE);
    }

    if (move_rel1.isDone() == mcTRUE && move_rel2.isEnabled() == mcFALSE)
      move_rel2.setExecute(mcTRUE);  //当位置抵达600时，触发第二个功能块到700

    // printf("Run time: %ld, usr pos: %f, act pos: %f\n", t, axis->toUserPos(),
    // axis->getPos());
    t += 0.001;
  }

  ASSERT_LT(fabs(axis->toUserVel() - 0.0), 0.01);
  ASSERT_LT(fabs(axis->toUserPos() - 700), 0.01);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_Homing
TEST_F(FunctionBlockTest, MC_Homing1)
{
  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);
  axis->setNodeQueueSize(3);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbHoming move_homing;
  move_homing.setAxis(axis);
  move_homing.setDirection(mcNegativeDirection);
  move_homing.setVelocity(300);
  move_homing.setAcceleration(500);
  move_homing.setDeceleration(500);
  move_homing.setJerk(5000);

  FbReadActualPosition read_actual_pos;
  read_actual_pos.setAxis(axis);
  read_actual_pos.setEnable(mcTRUE);
  double time_out = 3.5;
  double t        = 0;
  int64_t count   = 0;
  while (t < time_out)
  {
    //功能块调用
    runObservedCycle(*axis, "axis");
    runObservedCycle(fb_power, "fb_power");
    runObservedCycle(move_homing, "move_homing");
    runObservedCycle(read_actual_pos, "read_actual_pos");

    if (move_homing.isEnabled() == mcFALSE &&
        fb_power.getPowerStatus() == mcTRUE)
    {  //使能成功后moveRel开始移动
      std::cout << "axis poweron, moveHome start" << std::endl;
      move_homing.setExecute(mcTRUE);
      move_homing.setRefSignal(mcTRUE);  //触发home
    }

    if (count == 100)
    {
      move_homing.setRefSignal(mcFALSE);
    }

    if (move_homing.isDone() == mcTRUE)
    {
      std::cout << "moveHome done" << std::endl;
      break;
    }

    // printf("Run time: %ld, usr pos: %f, act vel: %f\n", t, axis->toUserPos(),
    // axis->toUserVel());
    count++;
    t += 0.001;
  }

  ASSERT_LT(fabs(axis->toUserVel() - 0.0), 0.01);
  ASSERT_LT(fabs(axis->toUserPos() - 0.0), 0.01);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_Homing
TEST_F(FunctionBlockTest, MC_Homing2)
{
  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);
  axis->setNodeQueueSize(3);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbMoveRelative move_rel;
  move_rel.setAxis(axis);
  move_rel.setPosition(100);
  move_rel.setVelocity(300);
  move_rel.setAcceleration(500);
  move_rel.setDeceleration(500);
  move_rel.setJerk(5000);

  FbHoming move_homing;
  move_homing.setAxis(axis);
  move_homing.setDirection(mcNegativeDirection);
  move_homing.setVelocity(300);
  move_homing.setAcceleration(500);
  move_homing.setDeceleration(500);
  move_homing.setJerk(5000);

  FbReadActualPosition read_actual_pos;
  read_actual_pos.setAxis(axis);
  read_actual_pos.setEnable(mcTRUE);
  double time_out = 3.5;
  double t        = 0;
  while (t < time_out)
  {
    //功能块调用
    runObservedCycle(*axis, "axis");
    runObservedCycle(fb_power, "fb_power");
    runObservedCycle(move_rel, "move_rel");
    runObservedCycle(move_homing, "move_homing");
    runObservedCycle(read_actual_pos, "read_actual_pos");

    if (move_rel.isEnabled() == mcFALSE && fb_power.getPowerStatus() == mcTRUE)
    {  //使能成功后moveRel开始移动
      std::cout << "axis poweron, moveRel start" << std::endl;
      move_rel.setExecute(mcTRUE);
    }

    if (move_rel.isDone() == mcTRUE && move_homing.isEnabled() == mcFALSE)
    {
      std::cout << "moveRel done, moveHome start" << std::endl;
      move_homing.setExecute(mcTRUE);  //当位置到达100后，触发home
    }

    if (move_homing.isEnabled() == mcTRUE &&
        read_actual_pos.getFloatValue() <= 0.0)
      move_homing.setRefSignal(mcTRUE);

    if (move_homing.isDone() == mcTRUE)
    {
      std::cout << "moveHome done" << std::endl;
      break;
    }

    // printf("Run time: %ld, usr pos: %f, act vel: %f\n", t, axis->toUserPos(),
    // axis->toUserVel());
    t += 0.001;
  }

  ASSERT_LT(fabs(axis->toUserVel() - 0.0), 0.01);
  ASSERT_LT(fabs(axis->toUserPos() - 0.0), 0.01);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_Homing
TEST_F(FunctionBlockTest, MC_Homing3)
{
  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);
  axis->setNodeQueueSize(3);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbHoming move_homing;
  move_homing.setAxis(axis);
  move_homing.setDirection(mcNegativeDirection);
  move_homing.setVelocity(300);
  move_homing.setAcceleration(500);
  move_homing.setDeceleration(500);
  move_homing.setJerk(5000);

  FbReadActualPosition read_actual_pos;
  read_actual_pos.setAxis(axis);
  read_actual_pos.setEnable(mcTRUE);

  double time_out = 3.5;
  double t        = 0;
  int64_t count   = 0;
  while (t < time_out)
  {
    //功能块调用
    runObservedCycle(*axis, "axis");
    runObservedCycle(fb_power, "fb_power");
    runObservedCycle(move_homing, "move_homing");
    runObservedCycle(read_actual_pos, "read_actual_pos");

    if (move_homing.isEnabled() == mcFALSE &&
        fb_power.getPowerStatus() == mcTRUE)
    {  //使能成功后moveHome开始移动
      std::cout << "axis poweron, moveRel start" << std::endl;
      move_homing.setExecute(mcTRUE);
    }

    if (count == 500)
    {
      move_homing.setLimitNegSignal(mcTRUE);
    }

    if (count == 1500)
    {
      move_homing.setRefSignal(mcTRUE);
    }

    if (count == 1600)
    {
      move_homing.setRefSignal(mcFALSE);
    }

    if (move_homing.isDone() == mcTRUE)
    {
      std::cout << "moveHome done" << std::endl;
      break;
    }

    // printf("Run time: %ld, usr pos: %f, act vel: %f\n", t, axis->toUserPos(),
    // axis->toUserVel());
    count++;
    t += 0.001;
  }

  ASSERT_LT(fabs(axis->toUserVel() - 0.0), 0.0001);
  ASSERT_LT(fabs(axis->toUserPos() - 0.0), 0.01);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_MoveVelocity -> MC_Halt/MC_Stop -> MC_MoveRelative
TEST_F(FunctionBlockTest, MC_Sequence1)
{
  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbMoveVelocity fb_move_vel;
  fb_move_vel.setAxis(axis);
  fb_move_vel.setVelocity(50);
  fb_move_vel.setAcceleration(10);
  fb_move_vel.setDeceleration(10);
  fb_move_vel.setJerk(50);
  fb_move_vel.setBufferMode(mcAborting);

  FbHalt fb_halt;
  fb_halt.setAxis(axis);
  fb_halt.setAcceleration(5);
  fb_halt.setJerk(50);
  fb_halt.setBufferMode(mcAborting);

  FbMoveAbsolute fb_move_abs;
  fb_move_abs.setAxis(axis);
  fb_move_abs.setPosition(600);
  fb_move_abs.setVelocity(300);
  fb_move_abs.setAcceleration(500);
  fb_move_abs.setDeceleration(500);
  fb_move_abs.setJerk(5000);

  FbSetPosition set_position1;
  set_position1.setAxis(axis);
  set_position1.setMode(mcSetPositionModeRelative);
  set_position1.setPosition(0);

  double time_out = 17;
  double t        = 0;
  while (t < time_out)
  {
    runObservedCycle(*axis, "axis");
    runObservedCycle(fb_power, "fb_power");
    runObservedCycle(set_position1, "set_position1");
    runObservedCycle(fb_move_vel, "fb_move_vel");
    runObservedCycle(fb_halt, "fb_halt");
    runObservedCycle(fb_move_abs, "fb_move_abs");

    if (set_position1.isEnabled() == mcFALSE &&
        fb_power.getPowerStatus() == mcTRUE)
    {
      std::cout << "axis poweron, set position" << std::endl;
      set_position1.setEnable(mcTRUE);
    }

    if (fb_move_vel.isEnabled() == mcFALSE &&
        fb_power.getPowerStatus() == mcTRUE &&
        set_position1.isEnabled() == mcTRUE)
    {  //使能成功后move1开始移动
      std::cout << "axis poweron, fb_move_vel start" << std::endl;
      fb_move_vel.setExecute(mcTRUE);
    }

    if (fb_move_vel.isInVelocity() == mcTRUE && fb_halt.isEnabled() == mcFALSE)
    {  //使能成功后move1开始移动
      std::cout << "axis in velocity, halt start" << std::endl;
      fb_halt.setExecute(mcTRUE);
    }

    if (fb_halt.isDone() == mcTRUE && fb_move_abs.isEnabled() == mcFALSE)
    {  //使能成功后move1开始移动
      std::cout << "axis halt, fb_move_abs start" << std::endl;
      fb_move_abs.setExecute(mcTRUE);
    }

    // printf("Run time: %ld, pos: %f, vel: %f\n", t, axis->toUserPos(),
    //        axis->toUserVel());
    t += 0.001;
  }

  ASSERT_LT(fabs(axis->toUserPos() - 600), 0.01);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_Jog
TEST_F(FunctionBlockTest, MC_Jog)
{
#ifdef PLOT
  fb_profile_.reset();
  axis_profile_.reset();
#endif
  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbJog fb_jog;
  fb_jog.setAxis(axis);
  fb_jog.setExecute(mcFALSE);
  fb_jog.setContinuousUpdate(mcFALSE);
  fb_jog.setVelocity(1.57);
  fb_jog.setAcceleration(3.14);
  fb_jog.setJerk(50);
  printf("Function block initialized.\n");

  double timeout = 0.0;
  while (timeout < 5.0)
  {
    runObservedCycle(*axis, "axis");
    runObservedCycle(fb_power, "fb_power");
    runObservedCycle(fb_jog, "fb_jog");
    timeout += 0.001;

#ifdef PLOT
    axis_profile_.addState(axis->toUserPos(), axis->toUserVel(),
                           axis->toUserAccCmd(), timeout);
#endif

    if (fb_jog.isEnabled() == mcFALSE && fb_power.getPowerStatus() == mcTRUE)
    {
      fb_jog.setExecute(mcTRUE);
      printf("Axis powered on %d\n", fb_power.getPowerStatus() == mcTRUE);
    }
    // Jog forward
    if (fabs(timeout - 1.0) < 0.0001)
    {
      fb_jog.setJogForwardSignal(mcTRUE);
    }
    // Jog halt
    if (fabs(timeout - 2.0) < 0.0001)
    {
      fb_jog.setJogForwardSignal(mcFALSE);
    }
    // Jog backward
    if (fabs(timeout - 3.0) < 0.0001)
    {
      fb_jog.setJogBackwardSignal(mcTRUE);
    }
    // Jog halt
    if (fabs(timeout - 4.0) < 0.0001)
    {
      fb_jog.setJogBackwardSignal(mcFALSE);
    }
  }
#ifdef PLOT
  plotProfile(axis_profile_, "mc_jog_axis");
#endif
  ASSERT_LT(fabs(axis->toUserVel()), 0.01);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_CamIn, MC_CamSelect
TEST_F(FunctionBlockTest, MC_Cam)
{
#ifdef PLOT
  fb_profile_.reset();
  axis_profile_.reset();
#endif
  RTmotion::AxisConfig config1;
  RTmotion::AxisConfig config2;
  RTmotion::AXIS_REF axis1;
  axis1 = new RTmotion::Axis();
  axis1->setAxisId(1);
  RTmotion::AXIS_REF axis2;
  axis2 = new RTmotion::Axis();
  axis2->setAxisId(2);

  axis1->setAxisConfig(&config1);
  printf("Axis1 initialized.\n");
  axis2->setAxisConfig(&config2);
  printf("Axis2 initialized.\n");

  RTmotion::Servo* servo1;
  servo1 = new RTmotion::Servo();
  axis1->setServo(servo1);

  RTmotion::Servo* servo2;
  servo2 = new RTmotion::Servo();
  axis2->setServo(servo2);

  RTmotion::FbPower fb_power1;
  fb_power1.setAxis(axis1);
  fb_power1.setEnable(mcTRUE);
  fb_power1.setEnablePositive(mcTRUE);
  fb_power1.setEnableNegative(mcTRUE);

  RTmotion::FbPower fb_power2;
  fb_power2.setAxis(axis2);
  fb_power2.setEnable(mcTRUE);
  fb_power2.setEnablePositive(mcTRUE);
  fb_power2.setEnableNegative(mcTRUE);

  RTmotion::FbMoveVelocity fb_move_vel;
  fb_move_vel.setAxis(axis1);
  fb_move_vel.setVelocity(1);
  fb_move_vel.setAcceleration(10);
  fb_move_vel.setDeceleration(10);
  fb_move_vel.setJerk(50);
  fb_move_vel.setBufferMode(RTmotion::mcAborting);

  RTmotion::McCamXYVA* cam_table = new RTmotion::McCamXYVA[21]{
    { 0, 0, NAN, NAN, RTmotion::polyFive },
    { 0.05, 0.18216653494266, NAN, NAN, RTmotion::polyFive },
    { 0.1, 0.87016810548376, NAN, NAN, RTmotion::polyFive },
    { 0.15, 2.05641722576408, NAN, NAN, RTmotion::polyFive },
    { 0.2, 3.13167438555392, NAN, NAN, RTmotion::polyFive },
    { 0.25, 3.73191015715167, NAN, NAN, RTmotion::polyFive },
    { 0.3, 3.96932297189104, NAN, NAN, RTmotion::polyFive },
    { 0.35, 3.98989548504385, NAN, NAN, RTmotion::polyFive },
    { 0.4, 3.87565752765028, NAN, NAN, RTmotion::polyFive },
    { 0.45, 3.66918595869634, NAN, NAN, RTmotion::polyFive },
    { 0.5, 3.39454683260162, NAN, NAN, RTmotion::polyFive },
    { 0.55, 3.06754062544119, NAN, NAN, RTmotion::polyFive },
    { 0.6, 2.70046667554222, NAN, NAN, RTmotion::polyFive },
    { 0.65, 2.30447191676131, NAN, NAN, RTmotion::polyFive },
    { 0.7, 1.89086353242174, NAN, NAN, RTmotion::polyFive },
    { 0.75, 1.47202253393456, NAN, NAN, RTmotion::polyFive },
    { 0.8, 1.06229448249912, NAN, NAN, RTmotion::polyFive },
    { 0.85, 0.67926960044916, NAN, NAN, RTmotion::polyFive },
    { 0.9, 0.34631157212864, NAN, NAN, RTmotion::polyFive },
    { 0.95, 0.09869066438798, NAN, NAN, RTmotion::polyFive },
    { 1.0, 0, NAN, NAN, RTmotion::noNextSegment }
  };

  RTmotion::FbCamRef fb_cam_ref;
  fb_cam_ref.setType(RTmotion::xyva);
  fb_cam_ref.setElementNum(21);
  fb_cam_ref.setMasterRangeStart(0);
  fb_cam_ref.setMasterRangeEnd(1.0);
  fb_cam_ref.setElements((unsigned char*)cam_table);

  RTmotion::FbCamTableSelect fb_cam_table_select;
  fb_cam_table_select.setMaster(axis1);
  fb_cam_table_select.setSlave(axis2);
  fb_cam_table_select.setCamTable(&fb_cam_ref);
  fb_cam_table_select.setMasterAbsolute(mcFALSE);
  fb_cam_table_select.setSlaveAbsolute(mcFALSE);
  fb_cam_table_select.setPeriodic(mcTRUE);
  fb_cam_table_select.setEnable(mcTRUE);

  RTmotion::FbCamIn fb_cam_in;
  fb_cam_in.setMaster(axis1);
  fb_cam_in.setSlave(axis2);
  fb_cam_in.setCamTableID(fb_cam_table_select.getCamTableID());
  fb_cam_in.setStartMode(RTmotion::mcRelative);
  fb_cam_in.setVelocity(50);
  fb_cam_in.setAcceleration(500);
  fb_cam_in.setDeceleration(500);
  fb_cam_in.setPosThreshold(1.0);
  fb_cam_in.setVelThreshold(10.0);
  fb_cam_in.setExecute(mcFALSE);

  RTmotion::FbCamOut fb_cam_out;
  fb_cam_out.setSlave(axis2);
  fb_cam_out.setExecute(mcFALSE);

#ifdef PLOT
  fb_profile_.addFB("fbCamIn");
  fb_profile_.addItemName("fbCamIn.isEnabled");
  fb_profile_.addItemName("fbCamIn.isDone");
#endif
  double time_out = 5;
  double t        = 0;
  while (t < time_out)
  {
    runObservedCycle(*axis1, "axis1");
    runObservedCycle(*axis2, "axis2");
    runObservedCycle(fb_power1, "fb_power1");
    runObservedCycle(fb_power2, "fb_power2");
    runObservedCycle(fb_move_vel, "fb_move_vel");
    runObservedCycle(fb_cam_table_select, "fb_cam_table_select");
    runObservedCycle(fb_cam_in, "fb_cam_in");
    runObservedCycle(fb_cam_out, "fb_cam_out");

    if (fb_power1.getPowerStatus() == mcTRUE &&
        fb_power2.getPowerStatus() == mcTRUE)
    {
      fb_move_vel.setExecute(mcTRUE);
      fb_cam_in.setExecute(mcTRUE);
    }

    if (t > 4.0)
    {
      fb_cam_out.setExecute(mcTRUE);
    }

#ifdef PLOT
    axis_profile_.addState(axis2->toUserPos(), axis2->toUserVel(),
                           axis2->toUserAccCmd(), t);
    fb_profile_.addState("fbCamIn.isEnabled", fb_cam_in.isEnabled() == mcTRUE);
    fb_profile_.addState("fbCamIn.isDone", fb_cam_in.isDone() == mcTRUE);
    fb_profile_.addTime(t);
#endif
    // printf("Axis 1: Run time: %f, pos: %f, vel: %f\n", t,
    // axis1->toUserPos(), axis1->toUserVel());
    // printf("Axis 2: Run time: %f, pos: %f, vel: %f, axis state: %d\n", t,
    // axis2->toUserPos(), axis2->toUserVel(), axis2->getAxisState());

    t += 0.001;
  }
#ifdef PLOT
  plotProfile(axis_profile_, "mc_cam_in_axis");
  plotProfile(fb_profile_, "mc_cam_fb");
#endif
  ASSERT_TRUE(fb_cam_out.isDone() == mcTRUE);
  delete servo1;
  delete servo2;
  delete axis1;
  delete axis2;
  delete[] cam_table;
  servo1    = nullptr;
  servo2    = nullptr;
  axis1     = nullptr;
  axis2     = nullptr;
  cam_table = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_GearIn, MC_GearOut
// With PLOT enabled, run with MPLBACKEND=Agg for headless PNG output in the
// working directory. The master-speed change here occurs after GearOut.
TEST_F(FunctionBlockTest, MC_Gear)
{
#ifdef PLOT
  fb_profile_.reset();
  axis_profile_.reset();
  AxisProfile master_profile;
#endif
  RTmotion::AxisConfig config1;
  RTmotion::AxisConfig config2;
  RTmotion::AXIS_REF axis1;
  axis1 = new RTmotion::Axis();
  axis1->setAxisId(1);
  RTmotion::AXIS_REF axis2;
  axis2 = new RTmotion::Axis();
  axis2->setAxisId(2);

  axis1->setAxisConfig(&config1);
  printf("Axis1 initialized.\n");
  axis2->setAxisConfig(&config2);
  printf("Axis2 initialized.\n");

  RTmotion::Servo* servo1;
  servo1 = new RTmotion::Servo();
  axis1->setServo(servo1);

  RTmotion::Servo* servo2;
  servo2 = new RTmotion::Servo();
  axis2->setServo(servo2);

  RTmotion::FbPower fb_power1;
  fb_power1.setAxis(axis1);
  fb_power1.setEnable(mcTRUE);
  fb_power1.setEnablePositive(mcTRUE);
  fb_power1.setEnableNegative(mcTRUE);

  RTmotion::FbPower fb_power2;
  fb_power2.setAxis(axis2);
  fb_power2.setEnable(mcTRUE);
  fb_power2.setEnablePositive(mcTRUE);
  fb_power2.setEnableNegative(mcTRUE);

  RTmotion::FbMoveVelocity fb_move_vel;
  fb_move_vel.setAxis(axis1);
  fb_move_vel.setVelocity(1);
  fb_move_vel.setAcceleration(10);
  fb_move_vel.setDeceleration(10);
  fb_move_vel.setJerk(50);
  fb_move_vel.setBufferMode(RTmotion::mcAborting);

  /* initialize MC_GearIn */
  RTmotion::FbGearIn fb_gear_in;
  fb_gear_in.setMaster(axis1);
  fb_gear_in.setSlave(axis2);
  fb_gear_in.setRatioNumerator(2);
  fb_gear_in.setRatioDenominator(1);
  fb_gear_in.setAcceleration(10);
  fb_gear_in.setDeceleration(10);
  fb_gear_in.setJerk(50);
  fb_gear_in.setBufferMode(RTmotion::mcAborting);
  // The default absolute tolerance (2) is too loose for a target speed of 2.
  const mcREAL in_gear_threshold = 0.01f;
  fb_gear_in.setInGearThreshold(in_gear_threshold);

  /* GearOut slave */
  RTmotion::FbGearOut fb_gear_out;
  fb_gear_out.setSlave(axis2);

#ifdef PLOT
  fb_profile_.addFB("gear_in");
  fb_profile_.addItemName("gear_in.execute");
  fb_profile_.addItemName("gear_in.inGear");
  fb_profile_.addItemName("gear_in.busy");
  fb_profile_.addItemName("gear_in.error");
  fb_profile_.addFB("gear_out");
  fb_profile_.addItemName("gear_out.execute");
  fb_profile_.addItemName("gear_out.done");
  fb_profile_.addItemName("gear_out.busy");
  fb_profile_.addItemName("gear_out.error");
#endif

  double time_out      = 2;
  double t             = 0;
  mcBOOL gear_in_flag  = mcTRUE;
  mcBOOL gear_out_flag = mcTRUE;
  // Hold Execute high for 20 cycles (20 ms), then leave it low.
  const int pulse_cycles          = 20;
  int gear_in_pulse               = 0;
  int gear_out_pulse              = 0;
  int gear_in_high_cycles         = 0;
  int gear_out_high_cycles        = 0;
  bool geared_with_execute_low    = false;
  bool gear_out_done              = false;
  int previous_master_counts      = servo1->pos();
  int cruise_samples              = 0;
  int noisy_cruise_samples        = 0;
  double peak_cruise_acceleration = 0;

  while (t < time_out)
  {
    runObservedCycle(*axis1, "axis1");
    runObservedCycle(*axis2, "axis2");
    runObservedCycle(fb_power1, "fb_power1");
    runObservedCycle(fb_power2, "fb_power2");
    runObservedCycle(fb_move_vel, "fb_move_vel");
    runObservedCycle(fb_gear_in, "fb_gear_in");
    runObservedCycle(fb_gear_out, "fb_gear_out");

    if (fb_gear_in.getInGear() == mcTRUE)
    {
      EXPECT_LT(fabs(axis2->toUserVel() - 2 * axis1->toUserVel()),
                in_gear_threshold);
    }

    // At velocity 1 and 1 kHz, the master advances exactly 1000 counts/cycle.
    // Check only settled gearing, before GearOut changes the motion.
    const int master_counts = servo1->pos();
    if (t >= 0.75 && t < 0.99)
    {
      ++cruise_samples;
      EXPECT_NEAR(axis1->toUserVelCmd(), 1.0, 1e-12);
      if (master_counts - previous_master_counts != 1000)
      {
        if (noisy_cruise_samples < 6)
          printf(
              "Gear cruise t=%.3f: master command counts=%.12f, "
              "count delta=%d, master velocity=%.6f, slave acceleration=%.6f\n",
              t, axis1->getPosCmd() * config1.encoder_count_per_unit_,
              master_counts - previous_master_counts, axis1->toUserVel(),
              axis2->toUserAccCmd());
        ++noisy_cruise_samples;
      }
      peak_cruise_acceleration =
          std::max(peak_cruise_acceleration, fabs(axis2->toUserAccCmd()));
    }
    previous_master_counts = master_counts;

    if (gear_in_pulse > 0)
    {
      ++gear_in_high_cycles;
      if (--gear_in_pulse == 0)
        fb_gear_in.setExecute(mcFALSE);
    }
    if (gear_out_pulse > 0)
    {
      ++gear_out_high_cycles;
      if (--gear_out_pulse == 0)
        fb_gear_out.setExecute(mcFALSE);
    }
    if (fb_power1.getPowerStatus() == mcTRUE &&
        fb_power2.getPowerStatus() == mcTRUE)
    {
      fb_move_vel.setExecute(mcTRUE);
    }
    if (fb_move_vel.isInVelocity() == mcTRUE && gear_in_flag == mcTRUE)
    {
      fb_gear_in.setExecute(mcTRUE);
      gear_in_pulse = pulse_cycles;
      gear_in_flag  = mcFALSE;
      printf("Slave gear in.\n");
    }
    if (fb_gear_in.isError() == mcTRUE)
    {
      printf("Slave gear in failed! Error ID:%X\n", fb_gear_in.getErrorID());
      break;
    }
    if ((t > (time_out / 2)) && (gear_out_flag == mcTRUE))
    {
      printf("master vel:%f  slave vel:%f  slave state:%d\n",
             axis1->toUserVel(), axis2->toUserVel(), axis2->getAxisState());
      fb_gear_out.setExecute(mcTRUE);
      gear_out_pulse = pulse_cycles;
      /* Change Master velocity */
      fb_move_vel.setVelocity(2);
      fb_move_vel.onRisingEdgeExecution();
      printf("Slave gear out and change master velocity to 2.\n");
      gear_out_flag = mcFALSE;
    }
    if (fb_gear_in.isEnabled() == mcFALSE && fb_gear_in.getInGear() == mcTRUE &&
        gear_out_flag == mcTRUE &&
        fabs(axis2->toUserVel() - 2 * axis1->toUserVel()) < 0.01)
      geared_with_execute_low = true;
    if (fb_gear_out.isDone() == mcTRUE)
      gear_out_done = true;
#ifdef PLOT
    master_profile.addState(axis1->toUserPos(), axis1->toUserVel(),
                            axis1->toUserAccCmd(), t);
    axis_profile_.addState(axis2->toUserPos(), axis2->toUserVel(),
                           axis2->toUserAccCmd(), t);
    fb_profile_.addState("gear_in.execute", fb_gear_in.isEnabled() == mcTRUE);
    fb_profile_.addState("gear_in.inGear", fb_gear_in.getInGear() == mcTRUE);
    fb_profile_.addState("gear_in.busy", fb_gear_in.isBusy() == mcTRUE);
    fb_profile_.addState("gear_in.error", fb_gear_in.isError() == mcTRUE);
    fb_profile_.addState("gear_out.execute", fb_gear_out.isEnabled() == mcTRUE);
    fb_profile_.addState("gear_out.done", fb_gear_out.isDone() == mcTRUE);
    fb_profile_.addState("gear_out.busy", fb_gear_out.isBusy() == mcTRUE);
    fb_profile_.addState("gear_out.error", fb_gear_out.isError() == mcTRUE);
    fb_profile_.addTime(t);
#endif
    t += 0.001;
  }
  printf("master vel:%f  slave vel:%f  slave state:%d\n", axis1->toUserVel(),
         axis2->toUserVel(), axis2->getAxisState());

  EXPECT_EQ(gear_in_high_cycles, pulse_cycles);
  EXPECT_EQ(gear_out_high_cycles, pulse_cycles);
  EXPECT_EQ(fb_gear_in.isEnabled(), mcFALSE);
  EXPECT_EQ(fb_gear_out.isEnabled(), mcFALSE);
  EXPECT_TRUE(geared_with_execute_low);
  EXPECT_TRUE(gear_out_done);
  EXPECT_GT(cruise_samples, 200);
  EXPECT_EQ(noisy_cruise_samples, 0);
  EXPECT_NEAR(peak_cruise_acceleration, 0, 1e-9);
  EXPECT_EQ(fb_gear_in.isError(), mcFALSE);
  EXPECT_EQ(fb_gear_out.isError(), mcFALSE);

#ifdef PLOT
  plotProfile(master_profile, "mc_gear_master_axis");
  plotProfile(axis_profile_, "mc_gear_slave_axis");
  plotProfile(fb_profile_, "mc_gear_fb", "gear_");
#endif

  /* Post Processing */
  delete servo1;
  delete servo2;
  delete axis1;
  delete axis2;
  servo1 = nullptr;
  servo2 = nullptr;
  axis1  = nullptr;
  axis2  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

TEST(MotionVelocityTest, CompletionHoldsExactTargetWithOverride)
{
  for (const double velocity : { 1.0, -1.0 })
  {
    for (const float factor : { 1.0f, 0.5f })
    {
      SCOPED_TRACE(::testing::Message()
                   << "velocity=" << velocity << ", override=" << factor);
      Axis axis;
      FbMoveVelocity move;
      move.setAxis(&axis);
      ExecutionNode node;
      node.setBasicParams(&move, mcMoveVelocityMode, NAN, velocity, 10, 10, 50,
                          mcAborting, mcOffLine);
      node.setTerminateCondition(0);
      OverrideFactors factors{ factor, 1, 1, mcFALSE };
      node.updateOverrideFactors(factors);
      const double target = velocity * factor;
      node.setStartVel(0);
      node.setStartAcc(0);
      node.setReplan();
      MC_AXIS_STATES state = mcContinuousMotion;
      node.onActive(&state);
      double position = 0, commanded_velocity = 0, acceleration = 0;
      int cruise_cycles = 0;
      for (int cycle = 0; cycle < 1000; ++cycle)
      {
        if (node.isDone() == mcFALSE)
        {
          if (node.checkMissionDone(position, commanded_velocity) == mcTRUE)
          {
            EXPECT_NEAR(commanded_velocity, target, 1e-12);
            EXPECT_NEAR(acceleration, 0, 1e-12);
            node.onDone(&state);
          }
          else
            node.onExecution(0, 0);
        }
        ASSERT_EQ(node.isError(), mcFALSE);
        node.getCommands(&position, &commanded_velocity, &acceleration);
#ifdef PLOT
        FunctionBlockObservations::commands(position, commanded_velocity,
                                            acceleration, target, 10);
#endif
        if (node.isDone() == mcTRUE)
        {
          EXPECT_DOUBLE_EQ(commanded_velocity, target);
          EXPECT_DOUBLE_EQ(acceleration, 0);
          ++cruise_cycles;
        }
      }
      EXPECT_GE(cruise_cycles, 100);
      EXPECT_EQ(state, mcContinuousMotion);
      EXPECT_EQ(move.isDone(), mcTRUE);
    }
  }
}

TEST(MotionVelocityTest, SmallLimitsArePreservedThroughCompletion)
{
  const double dt                 = 0.001;
  const double acceleration_limit = 0.01;
  const double jerk_limit         = 0.1;
  for (const double requested_velocity : { 0.00005, 0.001, -0.001 })
  {
    for (const float factor : { 1.0f, 0.5f })
    {
      for (const double start_factor : { 0.0, 0.91, 1.0, 1.09, 2.0 })
      {
        SCOPED_TRACE(::testing::Message() << "velocity=" << requested_velocity
                                          << ", override=" << factor
                                          << ", start_factor=" << start_factor);
        const double target          = requested_velocity * factor;
        const double start_velocity  = target * start_factor;
        const double velocity_change = fabs(target - start_velocity);
        const double ramp_duration =
            velocity_change <
                    acceleration_limit * acceleration_limit / jerk_limit ?
                2 * sqrt(velocity_change / jerk_limit) :
                velocity_change / acceleration_limit +
                    acceleration_limit / jerk_limit;
        Axis axis;
        FbMoveVelocity move;
        move.setAxis(&axis);
        ExecutionNode node;
        node.setFrequency(1 / dt);
        node.setBasicParams(&move, mcMoveVelocityMode, NAN, requested_velocity,
                            acceleration_limit, acceleration_limit, jerk_limit,
                            mcAborting, mcOffLine);
        node.setStartPos(0);
        node.setStartVel(start_velocity);
        node.setStartAcc(0);
        node.setTerminateCondition(0);
        OverrideFactors factors{ factor, 1, 1, mcFALSE };
        node.updateOverrideFactors(factors);
        node.setReplan();
        MC_AXIS_STATES state = mcContinuousMotion;
        node.onActive(&state);
        double position = 0, velocity = start_velocity, acceleration = 0;
        double peak_acceleration = 0, peak_velocity_step = 0, peak_jerk = 0;
        double completion_time = -1;
        for (int cycle = 0; cycle < 600; ++cycle)
        {
          const double previous_velocity     = velocity;
          const double previous_acceleration = acceleration;
          if (node.isDone() == mcFALSE)
          {
            if (node.checkMissionDone(position, velocity) == mcTRUE)
            {
              completion_time = cycle * dt;
              node.onDone(&state);
            }
            else
              node.onExecution(0, 0);
          }
          ASSERT_EQ(node.isError(), mcFALSE);
          node.getCommands(&position, &velocity, &acceleration);
#ifdef PLOT
          FunctionBlockObservations::commands(position, velocity, acceleration,
                                              target, acceleration_limit);
#endif
          peak_acceleration = std::max(peak_acceleration, fabs(acceleration));
          peak_velocity_step =
              std::max(peak_velocity_step, fabs(velocity - previous_velocity));
          peak_jerk = std::max(peak_jerk,
                               fabs(acceleration - previous_acceleration) / dt);
        }
        EXPECT_EQ(move.isDone(), mcTRUE);
        EXPECT_GE(completion_time + 1e-12, ramp_duration);
        EXPECT_LE(peak_acceleration, acceleration_limit + 1e-10);
        EXPECT_LE(peak_velocity_step / dt, acceleration_limit + 1e-10);
        EXPECT_LE(peak_jerk, jerk_limit + 1e-10);
        EXPECT_DOUBLE_EQ(velocity, target);
        EXPECT_DOUBLE_EQ(acceleration, 0);
      }
    }
  }
}

TEST_F(FunctionBlockTest, MC_GearIn_MasterVelocityChangeWhileGeared)
{
  AxisConfig master_config;
  master_config.frequency_ = 1000;
  AxisConfig slave_config  = master_config;
  Servo master_servo, slave_servo;
  Axis master, slave;
  master.setAxisId(1);
  slave.setAxisId(2);
  master.setAxisConfig(&master_config);
  slave.setAxisConfig(&slave_config);
  master.setServo(&master_servo);
  slave.setServo(&slave_servo);

  FbPower master_power, slave_power;
  master_power.setAxis(&master);
  slave_power.setAxis(&slave);
  for (auto* power : { &master_power, &slave_power })
  {
    power->setEnable(mcTRUE);
    power->setEnablePositive(mcTRUE);
    power->setEnableNegative(mcTRUE);
  }

  FbMoveVelocity initial_move, changed_move;
  for (auto* move : { &initial_move, &changed_move })
  {
    move->setAxis(&master);
    move->setAcceleration(1000);
    move->setDeceleration(1000);
    move->setJerk(10000);
    move->setBufferMode(mcAborting);
  }
  initial_move.setVelocity(100);
  changed_move.setVelocity(500);

  FbGearIn gear;
  gear.setMaster(&master);
  gear.setSlave(&slave);
  gear.setRatioNumerator(1);
  gear.setRatioDenominator(1);
  // Higher than the master's dynamics: this is not a slave-capability test.
  gear.setAcceleration(4000);
  gear.setDeceleration(4000);
  gear.setJerk(40000);
  gear.setInGearThreshold(0.01);
  gear.setBufferMode(mcAborting);

  const double dt = 1.0 / master_config.frequency_;
  // Allow five cycles of master acceleration plus feedback quantization.
  // This is a regression-test tolerance, not a PLCopen-specified limit.
  const double tracking_tolerance = 5 * 1000 * dt + 0.01;
  int stable_cycles               = 0;
  int change_cycle                = -1;
  int tracking_cycles             = 0;
  int out_of_gear_cycles          = 0;
  double peak_command_error       = 0;
  double peak_actual_error        = 0;
#ifdef PLOT
  std::vector<double> times, master_velocities, slave_commands;
  std::vector<double> slave_velocities, command_errors;
  fb_profile_.reset();
  fb_profile_.addFB("gear");
  fb_profile_.addItemName("gear.execute");
  fb_profile_.addItemName("gear.inGear");
  fb_profile_.addItemName("gear.error");
#endif

  for (int cycle = 0; cycle < 6000; ++cycle)
  {
    runObservedCycle(master, "master");
    runObservedCycle(slave, "slave");
    runObservedCycle(master_power, "master_power");
    runObservedCycle(slave_power, "slave_power");
    runObservedCycle(initial_move, "initial_move");
    runObservedCycle(changed_move, "changed_move");
    runObservedCycle(gear, "gear");

    ASSERT_EQ(master.getAxisError(), mcErrorCodeGood);
    ASSERT_EQ(slave.getAxisError(), mcErrorCodeGood);
    ASSERT_EQ(master_power.isError(), mcFALSE);
    ASSERT_EQ(slave_power.isError(), mcFALSE);
    ASSERT_EQ(initial_move.isError(), mcFALSE) << initial_move.getErrorID();
    ASSERT_EQ(changed_move.isError(), mcFALSE) << changed_move.getErrorID();
    ASSERT_EQ(gear.isError(), mcFALSE) << gear.getErrorID();

    if (master_power.getPowerStatus() == mcTRUE &&
        slave_power.getPowerStatus() == mcTRUE)
      initial_move.setExecute(mcTRUE);
    if (change_cycle < 0 && initial_move.isInVelocity() == mcTRUE)
      gear.setExecute(mcTRUE);

    const double command_error =
        fabs(slave.toUserVelCmd() - master.toUserVel());
    const double actual_error = fabs(slave.toUserVel() - master.toUserVel());
    if (change_cycle < 0)
    {
      if (gear.getInGear() == mcTRUE && fabs(master.toUserVel() - 100) < 0.01 &&
          actual_error < 0.01 && command_error < 0.01)
        ++stable_cycles;
      else
        stable_cycles = 0;
      if (stable_cycles >= 100)
      {
        change_cycle = cycle;
        changed_move.setExecute(mcTRUE);
      }
    }
    else
    {
      ASSERT_EQ(gear.isEnabled(), mcTRUE);
      ASSERT_EQ(slave.getAxisState(), mcSynchronizedMotion);
      ++tracking_cycles;
      if (gear.getInGear() == mcFALSE)
        ++out_of_gear_cycles;
      if (command_error > peak_command_error)
        peak_command_error = command_error;
      if (actual_error > peak_actual_error)
        peak_actual_error = actual_error;
    }
#ifdef PLOT
    times.push_back(cycle * dt);
    master_velocities.push_back(master.toUserVel());
    slave_commands.push_back(slave.toUserVelCmd());
    slave_velocities.push_back(slave.toUserVel());
    command_errors.push_back(command_error);
    fb_profile_.addState("gear.execute", gear.isEnabled() == mcTRUE);
    fb_profile_.addState("gear.inGear", gear.getInGear() == mcTRUE);
    fb_profile_.addState("gear.error", gear.isError() == mcTRUE);
    fb_profile_.addTime(cycle * dt);
#endif
    if (tracking_cycles >= 3000)
      break;
  }

#ifdef PLOT
  plt::figure_size(1280, 720);
  plt::subplot(2, 1, 1);
  plt::title("GearIn 1:1: master velocity changes while still geared");
  plt::named_plot("Master actual / slave target", times, master_velocities);
  plt::named_plot("Slave commanded", times, slave_commands);
  plt::named_plot("Slave actual", times, slave_velocities);
  plt::ylabel("Velocity");
  plt::legend();
  plt::subplot(2, 1, 2);
  plt::named_plot("Absolute command tracking error", times, command_errors);
  plt::named_plot("Post-sync tolerance", times,
                  std::vector<double>(times.size(), tracking_tolerance));
  plt::ylabel("Velocity error");
  plt::xlabel("Time (s)");
  plt::legend();
  const auto file = test_plot::TestPlot::filename("_velocity_change");
  plt::save(file);
  test_plot::TestPlot::recordFile(file);
  plotProfile(fb_profile_, "mc_gear_velocity_change_fb");
#endif

  printf("GearIn velocity change: change time=%.3f s, "
         "peak command error=%.6f, peak actual error=%.6f, "
         "InGear false=%d/%d post-change cycles, tolerance=%.6f\n",
         change_cycle * dt, peak_command_error, peak_actual_error,
         out_of_gear_cycles, tracking_cycles, tracking_tolerance);
  ASSERT_GE(change_cycle, 0) << "Initial gearing never stabilized.";
  ASSERT_EQ(tracking_cycles, 3000);
  EXPECT_EQ(changed_move.isInVelocity(), mcTRUE);
  EXPECT_NEAR(master.toUserVel(), 500, 0.01);
  EXPECT_NEAR(slave.toUserVel(), 500, 0.01);
  EXPECT_EQ(gear.getInGear(), mcTRUE);
  EXPECT_LE(peak_command_error, tracking_tolerance)
      << "Slave command failed to follow the master after synchronization.";
  EXPECT_LE(peak_actual_error, tracking_tolerance)
      << "Slave feedback failed to follow the master after synchronization.";
}

TEST(ExecutionNodeStatusTest, CompletedFiniteMotionsKeepTheirResult)
{
  for (const auto mode :
       { mcMoveAbsoluteMode, mcMoveRelativeMode, mcMoveAdditiveMode, mcHaltMode,
         mcStopMode, mcHomingMode, mcMoveVelocityMode, mcSyncOutMode })
  {
    SCOPED_TRACE(mode);
    FbMoveRelative block;
    ExecutionNode node;
    node.setBasicParams(&block, mode, 1, 1, 4, 4, 40, mcAborting, mcRuckig);
    MC_AXIS_STATES state = mcStandstill;
    node.onDone(&state);
    ASSERT_EQ(block.isDone(), mcTRUE);
    node.onCommandAborted();
    const bool continuous = mode == mcMoveVelocityMode || mode == mcSyncOutMode;
    EXPECT_EQ(block.isDone(), continuous ? mcFALSE : mcTRUE);
    EXPECT_EQ(block.isAborted(), continuous ? mcTRUE : mcFALSE);
  }
}

TEST(MotionKernelStatusTest, ControlledStopRejectsDirectEnqueue)
{
  class StoppingNode : public ExecutionNode
  {
  public:
    void beginStop()
    {
      stopping_on_error_ = mcTRUE;
    }
  };
  MotionKernel kernel;
  FbMoveRelative stopping_fb, submitted_fb;
  Axis axis;
  stopping_fb.setAxis(&axis);
  submitted_fb.setAxis(&axis);
  StoppingNode stopping;
  stopping.setBasicParams(&stopping_fb, mcGearInPosMode, 1, 1, 4, 4, 40,
                          mcAborting, mcRuckig);
  kernel.addFBToQueue(&stopping, 0, 1, 0, 0);
  stopping.beginStop();
  for (const bool superimposed : { false, true })
  {
    ExecutionNode submitted;
    submitted.setBasicParams(&submitted_fb, mcMoveRelativeMode, 1, 1, 4, 4, 40,
                             mcAborting, mcRuckig);
    submitted.taken_ = mcTRUE;
    if (superimposed)
      kernel.addSupMoveFB(&submitted, 0, 1, 0, 0);
    else
      kernel.addFBToQueue(&submitted, 0, 1, 0, 0);
    EXPECT_EQ(submitted.isError(), mcTRUE);
    EXPECT_EQ(submitted_fb.getErrorID(), mcErrorCodeAxisStateViolation);
    EXPECT_EQ(submitted.taken_, mcFALSE);
    ASSERT_EQ(kernel.getQueuedMotions().size(), 1u);
    EXPECT_EQ(kernel.getQueuedMotions().front(), &stopping);
    EXPECT_TRUE(kernel.isStoppingOnError());
    EXPECT_EQ(stopping.isAborted(), mcFALSE);
  }
}

TEST(MotionKernelStatusTest, ControlledStopUsesSelectedCommandState)
{
  class FaultingNode : public ExecutionNode
  {
  public:
    void onExecution(mcLREAL position, mcLREAL velocity) override
    {
      stopping_on_error_ = error_ = mcTRUE;
      error_id_                   = mcErrorCodeSlaveExceedLimit;
      ExecutionNode::onExecution(position, velocity);
    }
  };
  for (const auto selected : { mcFALSE, mcTRUE })
  {
    MotionKernel kernel;
    Axis axis;
    FbMoveRelative underlying_fb, overlay_fb;
    underlying_fb.setAxis(&axis);
    overlay_fb.setAxis(&axis);
    overlay_fb.setPosition(10);
    overlay_fb.setVelocity(1);
    overlay_fb.setAcceleration(4);
    overlay_fb.setDeceleration(4);
    overlay_fb.setJerk(40);
    FaultingNode underlying;
    ExecutionNode overlay;
    underlying.setFrequency(1000);
    underlying.setBasicParams(&underlying_fb, mcGearInPosMode, 1, 1, 4, 4, 40,
                              mcAborting, mcRuckig);
    kernel.addFBToQueue(&underlying, 0, 0.5, 0, 0);
    overlay.setBasicParams(&overlay_fb, mcMoveSupMode, 10, 1, 4, 4, 40,
                           mcAborting, mcRuckig);
    kernel.addSupMoveFB(&overlay, 2, 1, 0, 0);
    MC_AXIS_STATES state = mcStandstill;
    OverrideFactors overrides{ 1, 1, 1, mcFALSE };
    kernel.runCycle(0, 0, 0, 0.5, 0, &state, overrides, selected);
    double position = 0, velocity = 0, acceleration = 0;
    kernel.getCommands(&position, &velocity, &acceleration);
#ifdef PLOT
    FunctionBlockObservations::commands(position, velocity, acceleration,
                                        selected == mcTRUE ? 1 : 0.5);
#endif
    EXPECT_EQ(overlay_fb.isAborted(), mcTRUE);
    EXPECT_EQ(state, mcStopping);
    EXPECT_NEAR(velocity, selected == mcTRUE ? 1 : 0.5, 0.001);
    EXPECT_NEAR(position, selected == mcTRUE ? 2 : 0, 0.002);
  }
}

class AxisCycleTimeTest : public FunctionBlockTest,
                          public ::testing::WithParamInterface<double>
{
protected:
  void SetUp() override
  {
    config_.frequency_ = GetParam();
    axis_.setAxisConfig(&config_);
    // Growing the queue after configuration must not expose default-rate nodes.
    axis_.setNodeQueueSize(3);
    axis_.setServo(&servo_);
    power_.setAxis(&axis_);
    power_.setEnable(mcTRUE);
    power_.setEnablePositive(mcTRUE);
    power_.setEnableNegative(mcTRUE);
    for (int cycle = 0; cycle < 10; ++cycle)
      runCycle({});
    ASSERT_EQ(power_.getPowerStatus(), mcTRUE);
  }

  void configureMotion(FbAxisMotion& block)
  {
    block.setAxis(&axis_);
    block.setPosition(2);
    block.setVelocity(1);
    block.setAcceleration(4);
    block.setDeceleration(4);
    block.setJerk(40);
    block.setBufferMode(mcBuffered);
  }

  void runCycle(std::initializer_list<FbAxisMotion*> blocks)
  {
    runObservedCycle(axis_, "axis_");
    runObservedCycle(power_, "power_");
    for (auto* block : blocks)
    {
      runObservedCycle(*block, "block");
      ASSERT_EQ(block->isError(), mcFALSE) << block->getErrorID();
    }
    ASSERT_EQ(axis_.getAxisError(), mcErrorCodeGood);
    ASSERT_EQ(power_.isError(), mcFALSE);
  }

  void checkPowerRecovery(double direction, bool issue_recovery_move)
  {
    ASSERT_EQ(axis_.setHomePositionOffset(7), mcTRUE);
    const double home = axis_.getHomePos();
    FbMoveRelative interrupted, pending, recovery;
    for (auto* move : { &interrupted, &pending, &recovery })
    {
      configureMotion(*move);
      move->setPosition(1000 * direction);
      move->setVelocity(500);
      move->setAcceleration(2000);
      move->setDeceleration(2000);
      move->setJerk(20000);
    }
    interrupted.setBufferMode(mcAborting);
    interrupted.setExecute(mcTRUE);
    pending.setExecute(mcTRUE);
    bool moving = false;
    for (int cycle = 0; cycle < GetParam(); ++cycle)
    {
      runCycle({ &interrupted, &pending });
      if (direction * axis_.toUserVel() > 300)
      {
        moving = true;
        break;
      }
    }
    ASSERT_TRUE(moving);
    ASSERT_GT(direction * axis_.toUserVelCmd(), 300);
    ASSERT_GT(fabs(axis_.toUserAccCmd()), 1);
    power_.setEnable(mcFALSE);
    for (int cycle = 0; cycle < 10; ++cycle)
      runCycle({ &interrupted, &pending });
    ASSERT_EQ(power_.getPowerStatus(), mcFALSE);
    const double stop_position = axis_.getPosCmd();
    EXPECT_EQ(interrupted.isAborted(), mcTRUE);
    EXPECT_EQ(pending.isAborted(), mcTRUE);
    power_.setEnable(mcTRUE);
    for (int cycle = 0; cycle < 10; ++cycle)
      runCycle({ &interrupted, &pending });
    ASSERT_EQ(power_.getPowerStatus(), mcTRUE);
    ASSERT_EQ(axis_.getAxisState(), mcStandstill);
    EXPECT_DOUBLE_EQ(axis_.toUserVelCmd(), 0);
    EXPECT_DOUBLE_EQ(axis_.toUserAccCmd(), 0);
    EXPECT_DOUBLE_EQ(axis_.getHomePos(), home);
    EXPECT_NEAR(axis_.getPosCmd(), stop_position, 1e-6);
    const double target       = axis_.toUserPos() + 50 * direction;
    double peak_overshoot     = 0;
    double peak_idle_velocity = 0, peak_idle_acceleration = 0;
    recovery.setPosition(50 * direction);
    recovery.setBufferMode(mcAborting);
    if (issue_recovery_move)
      recovery.setExecute(mcTRUE);
#ifdef PLOT
    std::vector<double> times, positions, velocities, accelerations, targets;
#endif
    for (int cycle = 0; cycle < 4 * GetParam(); ++cycle)
    {
      runCycle({ &interrupted, &pending, &recovery });
      if (issue_recovery_move && cycle <= 1)
      {
        EXPECT_LE(fabs(axis_.toUserVelCmd()),
                  20000 / (GetParam() * GetParam()));
        EXPECT_LE(fabs(axis_.toUserAccCmd()), 20000 / GetParam());
      }
      peak_overshoot =
          std::max(peak_overshoot, direction * (axis_.toUserPos() - target));
      peak_idle_velocity =
          std::max(peak_idle_velocity, fabs(axis_.toUserVelCmd()));
      peak_idle_acceleration =
          std::max(peak_idle_acceleration, fabs(axis_.toUserAccCmd()));
#ifdef PLOT
      times.push_back(cycle / GetParam());
      positions.push_back(axis_.toUserPos());
      velocities.push_back(axis_.toUserVelCmd());
      accelerations.push_back(axis_.toUserAccCmd());
      targets.push_back(issue_recovery_move ? target : stop_position - home);
#endif
    }
    if (issue_recovery_move)
    {
      EXPECT_EQ(recovery.isDone(), mcTRUE);
      EXPECT_LT(peak_overshoot, 0.5);
      EXPECT_NEAR(axis_.toUserPos(), target, 0.001);
    }
    else
    {
      EXPECT_DOUBLE_EQ(peak_idle_velocity, 0);
      EXPECT_DOUBLE_EQ(peak_idle_acceleration, 0);
      EXPECT_NEAR(axis_.getPosCmd(), stop_position, 1e-6);
    }
    EXPECT_DOUBLE_EQ(axis_.getHomePos(), home);
#ifdef PLOT
    const auto* test = ::testing::UnitTest::GetInstance()->current_test_info();
    const auto filename = test_plot::TestPlot::filename("_power_recovery");
    plt::figure_size(1280, 960);
    plt::subplot(3, 1, 1);
    plt::title(test->name());
    plt::named_plot("Actual", times, positions);
    plt::named_plot("Target", times, targets);
    plt::ylabel("Position");
    plt::legend();
    plt::subplot(3, 1, 2);
    plt::plot(times, velocities);
    plt::ylabel("Command velocity");
    plt::subplot(3, 1, 3);
    plt::plot(times, accelerations);
    plt::ylabel("Command acceleration");
    plt::xlabel("Time (s)");
    plt::save(filename);
    test_plot::TestPlot::recordFile(filename);
    plt::close();
#endif
  }

  void checkSuperimposedRecovery(bool fault, bool with_underlying)
  {
    FbMoveRelative underlying;
    FbMoveSuperimposed overlay;
    for (auto* move : { static_cast<FbAxisMotion*>(&underlying),
                        static_cast<FbAxisMotion*>(&overlay) })
    {
      configureMotion(*move);
      move->setPosition(100);
      move->setVelocity(10);
      move->setAcceleration(20);
      move->setDeceleration(20);
      move->setJerk(200);
      move->setBufferMode(mcAborting);
    }
    if (with_underlying)
    {
      underlying.setExecute(mcTRUE);
      for (int cycle = 0; cycle < GetParam() / 4; ++cycle)
        ASSERT_NO_FATAL_FAILURE(runCycle({ &underlying }));
    }
    overlay.setExecute(mcTRUE);
    for (int cycle = 0; cycle < GetParam() / 4; ++cycle)
      ASSERT_NO_FATAL_FAILURE(runCycle({ &underlying, &overlay }));
    ASSERT_EQ(axis_.getAxisSuperimposedState(), mcTRUE);
    ASSERT_EQ(overlay.isDone(), mcFALSE);
    ASSERT_GT(axis_.toUserVelCmd(), 1);
    ASSERT_GT(fabs(axis_.toUserAccCmd()), 1);

    if (fault)
    {
      config_.sw_vel_limit_ = mcTRUE;
      config_.vel_limit_    = 0.1;
    }
    else
      power_.setEnable(mcFALSE);
    // Axis health is processed before the FB inputs reach the next cycle.
    for (int cycle = 0; cycle < 3; ++cycle)
    {
      runObservedCycle(axis_, "axis_");
      runObservedCycle(power_, "power_");
    }
    if (fault)
      ASSERT_EQ(axis_.getAxisError(), mcErrorCodeVelocityOverLimit);
    else
      ASSERT_EQ(power_.getPowerStatus(), mcFALSE);
    EXPECT_EQ(overlay.isAborted(), mcTRUE);
    EXPECT_EQ(axis_.getAxisSuperimposedState(), mcFALSE);
    EXPECT_DOUBLE_EQ(axis_.getMoveSupCoveredDistance(), 0);
    EXPECT_DOUBLE_EQ(axis_.toUserVelCmd(), 0);
    EXPECT_DOUBLE_EQ(axis_.toUserAccCmd(), 0);
    if (with_underlying)
      EXPECT_EQ(underlying.isAborted(), mcTRUE);

    const double position = axis_.getPos();
    config_.sw_vel_limit_ = mcFALSE;
    if (fault)
      axis_.resetError(mcTRUE);
    else
      power_.setEnable(mcTRUE);
    for (int cycle = 0; cycle < GetParam(); ++cycle)
    {
      ASSERT_NO_FATAL_FAILURE(runCycle({ &underlying, &overlay }));
      EXPECT_EQ(axis_.getAxisSuperimposedState(), mcFALSE);
      EXPECT_DOUBLE_EQ(axis_.toUserVelCmd(), 0);
      EXPECT_DOUBLE_EQ(axis_.toUserAccCmd(), 0);
      EXPECT_NEAR(axis_.getPos(), position, 1e-6);
      EXPECT_NEAR(axis_.getPosCmd(), position, 1e-6);
    }
    ASSERT_EQ(power_.getPowerStatus(), mcTRUE);
    ASSERT_EQ(axis_.getAxisState(), mcStandstill);
    EXPECT_EQ(overlay.isAborted(), mcTRUE);

    // A new Execute edge may reuse the overlay slot, but no old motion resumes.
    overlay.setExecute(mcFALSE);
    ASSERT_NO_FATAL_FAILURE(runCycle({ &overlay }));
    overlay.setExecute(mcTRUE);
    for (int cycle = 0; cycle < GetParam() / 4; ++cycle)
      ASSERT_NO_FATAL_FAILURE(runCycle({ &overlay }));
    EXPECT_EQ(overlay.isAborted(), mcFALSE);
    EXPECT_EQ(overlay.isDone(), mcFALSE);
    EXPECT_EQ(axis_.getAxisSuperimposedState(), mcTRUE);
    EXPECT_GT(axis_.getPos(), position);
    EXPECT_GT(axis_.toUserVelCmd(), 1);
  }

  void checkAxisErrorRecovery()
  {
    FbMoveRelative interrupted, recovery;
    for (auto* move : { &interrupted, &recovery })
    {
      configureMotion(*move);
      move->setPosition(1000);
      move->setVelocity(500);
      move->setAcceleration(2000);
      move->setDeceleration(2000);
      move->setJerk(20000);
    }
    interrupted.setBufferMode(mcAborting);
    interrupted.setExecute(mcTRUE);
    bool moving = false;
    for (int cycle = 0; cycle < GetParam(); ++cycle)
    {
      runCycle({ &interrupted });
      if (axis_.toUserVel() > 300)
      {
        moving = true;
        break;
      }
    }
    ASSERT_TRUE(moving);
    ASSERT_GT(axis_.toUserVelCmd(), 300);
    ASSERT_GT(fabs(axis_.toUserAccCmd()), 1);

    config_.sw_vel_limit_ = mcTRUE;
    config_.vel_limit_    = 1;
    runObservedCycle(axis_, "axis_");
    runObservedCycle(power_, "power_");
    runObservedCycle(axis_, "axis_");
    runObservedCycle(power_, "power_");
    ASSERT_EQ(axis_.getAxisError(), mcErrorCodeVelocityOverLimit);
    ASSERT_EQ(axis_.getAxisState(), mcErrorStop);

    axis_.resetError(mcTRUE);
    runObservedCycle(axis_, "axis_");
    runObservedCycle(power_, "power_");
    ASSERT_EQ(axis_.getAxisError(), mcErrorCodeGood);
    ASSERT_EQ(power_.getPowerStatus(), mcFALSE);
    EXPECT_DOUBLE_EQ(axis_.toUserVelCmd(), 0);
    EXPECT_DOUBLE_EQ(axis_.toUserAccCmd(), 0);

    config_.sw_vel_limit_ = mcFALSE;
    for (int cycle = 0; cycle < 10; ++cycle)
    {
      runObservedCycle(axis_, "axis_");
      runObservedCycle(power_, "power_");
      ASSERT_EQ(axis_.getAxisError(), mcErrorCodeGood);
      ASSERT_EQ(power_.isError(), mcFALSE);
      EXPECT_DOUBLE_EQ(axis_.toUserVelCmd(), 0);
      EXPECT_DOUBLE_EQ(axis_.toUserAccCmd(), 0);
    }
    ASSERT_EQ(power_.getPowerStatus(), mcTRUE);
    ASSERT_EQ(axis_.getAxisState(), mcStandstill);

    recovery.setPosition(50);
    recovery.setBufferMode(mcAborting);
    recovery.setExecute(mcTRUE);
    for (int cycle = 0; cycle < 4 * GetParam(); ++cycle)
    {
      runCycle({ &interrupted, &recovery });
      if (cycle <= 1)
      {
        EXPECT_LE(fabs(axis_.toUserVelCmd()),
                  20000 / (GetParam() * GetParam()));
        EXPECT_LE(fabs(axis_.toUserAccCmd()), 20000 / GetParam());
      }
    }
    EXPECT_EQ(recovery.isDone(), mcTRUE);
    EXPECT_NEAR(axis_.toUserPos(), 50, 0.001);
  }

  void checkHomingSearchAbort(bool use_stop)
  {
    FbHoming home;
    FbStop stop;
    FbMoveRelative move;
    FbAxisMotion* successor = use_stop ? static_cast<FbAxisMotion*>(&stop) :
                                         static_cast<FbAxisMotion*>(&move);
    configureMotion(home);
    configureMotion(*successor);
    home.setDirection(mcPositiveDirection);
    home.setExecute(mcTRUE);
    successor->setBufferMode(mcAborting);
    for (int cycle = 0; cycle < GetParam(); ++cycle)
      runCycle({ &home });
    ASSERT_NEAR(axis_.toUserVelCmd(), 1, 0.001);
    ASSERT_EQ(home.isDone(), mcFALSE);
    ASSERT_EQ(home.isAborted(), mcFALSE);
    successor->setExecute(mcTRUE);
    for (int cycle = 0; cycle < 3 * GetParam(); ++cycle)
    {
      runCycle({ &home, successor });
      if (cycle == 0)
        continue;
      EXPECT_EQ(home.isAborted(), mcTRUE);
      EXPECT_EQ(home.isDone(), mcFALSE);
      EXPECT_EQ(home.isBusy(), mcFALSE);
    }
    EXPECT_EQ(successor->isDone(), mcTRUE);
  }

  void checkStopAfterCompletion(bool keep_execute_high)
  {
    FbMoveRelative first, second, pending;
    FbStop stop;
    for (auto* move : { &first, &second, &pending })
    {
      configureMotion(*move);
      move->setBufferMode(mcBlendingLow);
      move->setExecute(mcTRUE);
    }
    second.setPosition(20);
    pending.setPosition(20);
    configureMotion(stop);
    stop.setBufferMode(mcAborting);

    bool stopped = false, first_done = false;
    bool second_aborted = false, pending_aborted = false;
    for (int cycle = 0; cycle < 10 * GetParam(); ++cycle)
    {
      if (!keep_execute_high && cycle >= 0.1 * GetParam())
        first.setExecute(mcFALSE);
      ASSERT_NO_FATAL_FAILURE(runCycle({ &first, &second, &pending, &stop }));
      first_done |= first.isDone() == mcTRUE;
      EXPECT_EQ(first.isAborted(), mcFALSE);
      second_aborted |= second.isAborted() == mcTRUE;
      pending_aborted |= pending.isAborted() == mcTRUE;
      if (!stopped && second.isActive() == mcTRUE && axis_.toUserPos() > 2.5)
      {
        ASSERT_TRUE(first_done);
        ASSERT_EQ(pending.isBusy(), mcTRUE);
        ASSERT_EQ(pending.isActive(), mcFALSE);
        stop.setExecute(mcTRUE);
        stopped = true;
      }
      if (stop.isDone() == mcTRUE)
        break;
    }
    ASSERT_TRUE(stopped);
    ASSERT_EQ(stop.isDone(), mcTRUE);
    EXPECT_TRUE(second_aborted);
    EXPECT_TRUE(pending_aborted);
    EXPECT_EQ(first.isDone(), keep_execute_high ? mcTRUE : mcFALSE);
    EXPECT_EQ(first.isAborted(), mcFALSE);
    EXPECT_EQ(axis_.getAxisState(), mcStopping);
    EXPECT_NEAR(axis_.toUserVel(), 0,
                config_.factor_.vel_ +
                    GetParam() / config_.encoder_count_per_unit_);
    stop.setExecute(mcFALSE);
    for (int cycle = 0; cycle < 10; ++cycle)
    {
      ASSERT_NO_FATAL_FAILURE(runCycle({ &first, &second, &pending, &stop }));
      EXPECT_EQ(first.isAborted(), mcFALSE);
    }
    EXPECT_EQ(axis_.getAxisState(), mcStandstill);
  }

  AxisConfig config_;
  Servo servo_;
  Axis axis_;
  FbPower power_;
};

TEST_P(AxisCycleTimeTest, SuperimposedUsesConfiguredFrequencyAfterReset)
{
  const double frequency = GetParam();
  config_.frequency_     = frequency / 2;
  axis_.setAxisConfig(&config_);
  config_.frequency_ = frequency;
  axis_.setAxisConfig(&config_);
  FbMoveSuperimposed move;
  configureMotion(move);
  move.setDistance(2);
  move.setVelocityDiff(1);
  move.setExecute(mcTRUE);
  int completion_cycles = 0;
  int settled_cycles    = 0;
  double peak_velocity  = 0;
  for (int cycle = 1; cycle < 6 * frequency; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle({ &move }));
    const double velocity = axis_.toUserVel();
    peak_velocity         = std::max(peak_velocity, fabs(velocity));
    // Feedback is a quantized interval average, not endpoint velocity.
    EXPECT_NEAR(velocity, axis_.toUserVelCmd(),
                4 / frequency +
                    2 * frequency / config_.encoder_count_per_unit_ + 1e-8);
    if (settled_cycles == 0 && fabs(axis_.getPosCmd() - 2) < 1e-8 &&
        fabs(axis_.toUserVelCmd()) < 1e-8)
      settled_cycles = cycle;
    if (move.isDone() == mcTRUE)
    {
      completion_cycles = cycle;
      break;
    }
  }
  ASSERT_GT(completion_cycles, 0);
  ASSERT_GT(settled_cycles, 0);
  // Measure trajectory timing, independent of the FB's exact-distance Done
  // test. Symmetric jerk-limited move: distance/v + v/a + a/j.
  EXPECT_NEAR(settled_cycles / frequency, 2.35, 4 / frequency);
  EXPECT_NEAR(peak_velocity, 1, 0.005);
  EXPECT_NEAR(axis_.toUserPos(), 2, 0.001);
  move.setExecute(mcFALSE);
  for (int cycle = 0; cycle < 10; ++cycle)
    ASSERT_NO_FATAL_FAILURE(runCycle({ &move }));
  EXPECT_EQ(axis_.getAxisState(), mcStandstill);
}

TEST_P(AxisCycleTimeTest, QueueGrowthPreservesFrequencyForEverySlot)
{
  FbMoveRelative moves[3];
  for (auto& move : moves)
  {
    configureMotion(move);
    move.setExecute(mcTRUE);
  }
  int completion_cycles[3] = {};
  for (int cycle = 1; cycle < 12 * GetParam(); ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle({ &moves[0], &moves[1], &moves[2] }));
    EXPECT_NEAR(axis_.toUserVel(), axis_.toUserVelCmd(),
                4 / GetParam() +
                    2 * GetParam() / config_.encoder_count_per_unit_ + 1e-8);
    for (int i = 0; i < 3; ++i)
    {
      EXPECT_EQ(moves[i].isAborted(), mcFALSE);
      if (completion_cycles[i] == 0 && moves[i].isDone() == mcTRUE)
        completion_cycles[i] = cycle;
    }
    if (completion_cycles[2] != 0)
      break;
  }
  for (int i = 0; i < 3; ++i)
  {
    ASSERT_GT(completion_cycles[i], 0);
    const int start_cycle = i == 0 ? 0 : completion_cycles[i - 1];
    EXPECT_NEAR((completion_cycles[i] - start_cycle) / GetParam(), 2.35,
                4 / GetParam());
  }
  EXPECT_NEAR(axis_.toUserPos(), 6, 0.001);
}

TEST_P(AxisCycleTimeTest, StopPreservesCompletedResultWithExecuteHigh)
{
  checkStopAfterCompletion(true);
}

TEST_P(AxisCycleTimeTest, StopDoesNotAbortCompletedPulsedCommand)
{
  checkStopAfterCompletion(false);
}

TEST_P(AxisCycleTimeTest, StopStillAbortsVelocityHold)
{
  FbMoveVelocity move;
  FbStop stop;
  configureMotion(move);
  configureMotion(stop);
  stop.setBufferMode(mcAborting);
  move.setExecute(mcTRUE);
  for (int cycle = 0; cycle < GetParam(); ++cycle)
    ASSERT_NO_FATAL_FAILURE(runCycle({ &move, &stop }));
  ASSERT_EQ(move.isInVelocity(), mcTRUE);
  stop.setExecute(mcTRUE);
  bool aborted = false;
  for (int cycle = 0; cycle < GetParam(); ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle({ &move, &stop }));
    aborted |= move.isAborted() == mcTRUE;
  }
  EXPECT_TRUE(aborted);
  EXPECT_EQ(move.isInVelocity(), mcFALSE);
  EXPECT_EQ(stop.isDone(), mcTRUE);
  EXPECT_NEAR(axis_.toUserVel(), 0, 0.001);
}

TEST_P(AxisCycleTimeTest, ExecutionNodeCopiesRetainClockAfterReset)
{
  FbMoveRelative move;
  ExecutionNode original;
  original.setFrequency(GetParam());
  ExecutionNode copied(original);
  ExecutionNode assigned;
  assigned.setFrequency(GetParam() / 2);
  assigned = original;
  for (auto* node : { &original, &copied, &assigned })
  {
    node->reset();
    node->setBasicParams(&move, mcMoveRelativeMode, 2, 1, 4, 4, 40, mcAborting,
                         mcRuckig);
    node->setStartPos(0);
    node->setStartVel(0);
    node->setStartAcc(0);
    node->setTerminateCondition(0);
    node->setReplan();
    MC_AXIS_STATES state = mcStandstill;
    node->onActive(&state);
    double position = 0, velocity = 0, acceleration = 0;
    for (int cycle = 0; cycle < GetParam(); ++cycle)
    {
      node->onExecution(0, 0);
      node->getCommands(&position, &velocity, &acceleration);
#ifdef PLOT
      FunctionBlockObservations::commands(position, velocity, acceleration);
#endif
      ASSERT_EQ(node->isError(), mcFALSE);
    }
    EXPECT_NEAR(position, 0.825, 1e-9);
    EXPECT_NEAR(velocity, 1, 1e-9);
  }
}

TEST_P(AxisCycleTimeTest, AxisCopiesUseAcceptedClockForMotionAndServo)
{
  config_.frequency_ = GetParam() * 2;
  Axis copied(axis_);
  Axis assigned;
  assigned = axis_;
  for (auto* axis : { &copied, &assigned })
  {
    Servo servo;
    axis->setServo(&servo);
    EXPECT_DOUBLE_EQ(axis->getFrequency(), GetParam());
    EXPECT_DOUBLE_EQ(axis->getDeltaTime(), 1 / GetParam());
    FbMoveRelative move;
    configureMotion(move);
    move.setAxis(axis);
    move.setExecute(mcTRUE);
    runObservedCycle(move, "move");
    for (int cycle = 0; cycle < GetParam(); ++cycle)
    {
      runObservedCycle(*axis, "axis");
      runObservedCycle(move, "move");
      ASSERT_EQ(axis->getAxisError(), mcErrorCodeGood);
      ASSERT_EQ(move.isError(), mcFALSE);
    }
    EXPECT_NEAR(axis->getPosCmd(), 0.825, 1e-9);
    EXPECT_NEAR(axis->toUserVel(), 1, 0.005);
  }
}

TEST_P(AxisCycleTimeTest, RejectsInvalidFrequencyWithoutChangingClock)
{
  axis_.setAxisConfig(nullptr);
  EXPECT_DOUBLE_EQ(axis_.getFrequency(), GetParam());
  for (const double frequency : { 0.0, -1.0, static_cast<double>(NAN),
                                  static_cast<double>(INFINITY), 1e-320 })
  {
    SCOPED_TRACE(frequency);
    AxisConfig rejected = config_;
    rejected.frequency_ = frequency;
    axis_.setAxisConfig(&rejected);
    EXPECT_DOUBLE_EQ(axis_.getFrequency(), GetParam());
    EXPECT_DOUBLE_EQ(axis_.getDeltaTime(), 1 / GetParam());
    ASSERT_NO_FATAL_FAILURE(runCycle({}));
  }
}

TEST_P(AxisCycleTimeTest, ExternalCycleUsesAcceptedClockAfterConfigMutation)
{
  config_.frequency_    = GetParam() * 2;
  config_.sw_vel_limit_ = mcTRUE;
  config_.vel_limit_    = 1.1;
  for (int cycle = 1; cycle <= 10; ++cycle)
  {
    axis_.runCycle(cycle / GetParam(), 1);
#ifdef PLOT
    FunctionBlockObservations::cycle(axis_, "axis_");
#endif
    EXPECT_EQ(axis_.getAxisError(), mcErrorCodeGood);
    EXPECT_NEAR(axis_.toUserVel(), 1, 0.005);
  }
  EXPECT_DOUBLE_EQ(axis_.getFrequency(), GetParam());
}

TEST_P(AxisCycleTimeTest, RejectsClockChangeWhileMotionIsQueued)
{
  FbMoveRelative move;
  configureMotion(move);
  move.setExecute(mcTRUE);
  runObservedCycle(move, "move");
  ASSERT_EQ(move.isBusy(), mcTRUE);
  ASSERT_EQ(move.isActive(), mcFALSE);
  ASSERT_EQ(axis_.getAxisState(), mcStandstill);
  AxisConfig rejected = config_;
  rejected.frequency_ = GetParam() * 2;
  axis_.setAxisConfig(&rejected);
  EXPECT_DOUBLE_EQ(axis_.getFrequency(), GetParam());
  ASSERT_NO_FATAL_FAILURE(runCycle({ &move }));
  EXPECT_EQ(move.isActive(), mcTRUE);
  EXPECT_EQ(move.isAborted(), mcFALSE);
}

TEST_P(AxisCycleTimeTest, RejectsClockChangeDuringSuperimposedMotion)
{
  FbMoveSuperimposed move;
  configureMotion(move);
  move.setExecute(mcTRUE);
  ASSERT_NO_FATAL_FAILURE(runCycle({ &move }));
  ASSERT_EQ(axis_.getAxisSuperimposedState(), mcTRUE);
  config_.frequency_ = GetParam() * 2;
  axis_.setAxisConfig(&config_);
  EXPECT_DOUBLE_EQ(axis_.getFrequency(), GetParam());
  for (int cycle = 0; cycle < GetParam(); ++cycle)
    ASSERT_NO_FATAL_FAILURE(runCycle({ &move }));
  EXPECT_NEAR(axis_.getPosCmd(), 0.825, 1e-9);
  EXPECT_NEAR(axis_.toUserVel(), 1, 0.005);
  EXPECT_EQ(move.isAborted(), mcFALSE);
}

TEST_P(AxisCycleTimeTest, ClockChangesOnlyAfterVelocityHoldAndStopFinish)
{
  FbMoveVelocity velocity;
  FbStop stop;
  configureMotion(velocity);
  configureMotion(stop);
  stop.setBufferMode(mcAborting);
  velocity.setExecute(mcTRUE);
  for (int cycle = 0; cycle < GetParam(); ++cycle)
    ASSERT_NO_FATAL_FAILURE(runCycle({ &velocity, &stop }));
  ASSERT_EQ(velocity.isInVelocity(), mcTRUE);

  config_.frequency_    = GetParam() * 2;
  config_.sw_vel_limit_ = mcTRUE;
  config_.vel_limit_    = 1.1;
  axis_.setAxisConfig(&config_);
  EXPECT_DOUBLE_EQ(axis_.getFrequency(), GetParam());
  AxisConfig other_config = config_;
  Axis other;
  other.setAxisConfig(&other_config);
  axis_ = other;
  EXPECT_DOUBLE_EQ(axis_.getFrequency(), GetParam());
  for (int cycle = 0; cycle < 10; ++cycle)
    ASSERT_NO_FATAL_FAILURE(runCycle({ &velocity, &stop }));
  EXPECT_NEAR(axis_.toUserVel(), 1, 0.005);
  EXPECT_EQ(velocity.isAborted(), mcFALSE);

  stop.setExecute(mcTRUE);
  for (int cycle = 0; cycle < GetParam(); ++cycle)
    ASSERT_NO_FATAL_FAILURE(runCycle({ &velocity, &stop }));
  ASSERT_EQ(stop.isDone(), mcTRUE);
  axis_.setAxisConfig(&config_);
  EXPECT_DOUBLE_EQ(axis_.getFrequency(), GetParam());
  stop.setExecute(mcFALSE);
  for (int cycle = 0; cycle < 10; ++cycle)
    ASSERT_NO_FATAL_FAILURE(runCycle({ &velocity, &stop }));
  ASSERT_EQ(axis_.getAxisState(), mcStandstill);

  axis_.setAxisConfig(&config_);
  ASSERT_DOUBLE_EQ(axis_.getFrequency(), GetParam() * 2);
  EXPECT_DOUBLE_EQ(axis_.getDeltaTime(), 1 / (GetParam() * 2));
  FbMoveRelative next;
  configureMotion(next);
  next.setExecute(mcTRUE);
  const double start_position = axis_.getPosCmd();
  int completion_cycles       = 0;
  for (int cycle = 1; cycle < 4 * axis_.getFrequency(); ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle({ &next }));
    if (next.isDone() == mcTRUE)
    {
      completion_cycles = cycle;
      break;
    }
  }
  ASSERT_GT(completion_cycles, 0);
  // The final jerk ramp can satisfy velocity tolerance before its endpoint.
  const double early_completion =
      sqrt(2 * config_.factor_.vel_ / next.getJerk());
  EXPECT_GE(completion_cycles / axis_.getFrequency(),
            2.35 - early_completion - 4 * axis_.getDeltaTime());
  EXPECT_LE(completion_cycles / axis_.getFrequency(),
            2.35 + 4 * axis_.getDeltaTime());
  EXPECT_NEAR(axis_.getPosCmd() - start_position, 2, 0.001);
}

TEST_P(AxisCycleTimeTest, StopAbortsHomingVelocitySearch)
{
  checkHomingSearchAbort(true);
}

TEST_P(AxisCycleTimeTest, ReplacementAbortsHomingVelocitySearch)
{
  checkHomingSearchAbort(false);
}

TEST_P(AxisCycleTimeTest, PowerRecoveryClearsPositiveCommandDerivatives)
{
  checkPowerRecovery(1, false);
}

TEST_P(AxisCycleTimeTest, PowerRecoveryClearsNegativeCommandDerivatives)
{
  checkPowerRecovery(-1, false);
}

TEST_P(AxisCycleTimeTest, PositiveMoveAfterPowerRecoveryDoesNotOvershoot)
{
  checkPowerRecovery(1, true);
}

TEST_P(AxisCycleTimeTest, NegativeMoveAfterPowerRecoveryDoesNotOvershoot)
{
  checkPowerRecovery(-1, true);
}

TEST_P(AxisCycleTimeTest, ReplacingSuperimposedMotionKeepsItsNodeReserved)
{
  axis_.setNodeQueueSize(10);
  FbMoveRelative underlying[9];
  for (auto& move : underlying)
  {
    configureMotion(move);
    move.setPosition(1000);
    move.setBufferMode(mcBuffered);
    move.setExecute(mcTRUE);
  }
  FbMoveSuperimposed first_overlay, replacement_overlay;
  for (auto* move : { &first_overlay, &replacement_overlay })
  {
    configureMotion(*move);
    move->setDistance(100);
    move->setVelocityDiff(1);
    move->setExecute(mcTRUE);
  }
  FbMoveRelative replacement;
  configureMotion(replacement);
  replacement.setBufferMode(mcAborting);

  const auto run_all = [&]() {
    runCycle({ &underlying[0], &underlying[1], &underlying[2], &underlying[3],
               &underlying[4], &underlying[5], &underlying[6], &underlying[7],
               &underlying[8], &first_overlay, &replacement_overlay,
               &replacement });
  };
  ASSERT_NO_FATAL_FAILURE(run_all());
  ASSERT_NO_FATAL_FAILURE(run_all());
  ASSERT_EQ(axis_.getAxisSuperimposedState(), mcTRUE);
  ASSERT_EQ(first_overlay.isAborted(), mcTRUE);
  ASSERT_EQ(replacement_overlay.isAborted(), mcFALSE);

  replacement.setExecute(mcTRUE);
  ASSERT_NO_FATAL_FAILURE(run_all());
  EXPECT_EQ(replacement.isError(), mcFALSE);
  EXPECT_EQ(replacement.isAborted(), mcFALSE);
  EXPECT_EQ(replacement.isBusy(), mcTRUE);
}

TEST_P(AxisCycleTimeTest, VelocityReversalPreservesAsymmetricLimitsAndJerk)
{
  FbMoveVelocity moves[3];
  const double targets[]       = { 1, -1, 0.5 };
  double previous_velocity     = axis_.toUserVelCmd();
  double previous_acceleration = axis_.toUserAccCmd();
  for (int phase = 0; phase < 3; ++phase)
  {
    auto& move = moves[phase];
    configureMotion(move);
    move.setBufferMode(mcAborting);
    move.setVelocity(targets[phase]);
    move.setAcceleration(2);
    move.setDeceleration(4);
    move.setJerk(40);
    move.setExecute(mcTRUE);
    for (int cycle = 0; cycle < 3 * GetParam(); ++cycle)
    {
      ASSERT_NO_FATAL_FAILURE(runCycle({ &move }));
      const double velocity     = axis_.toUserVelCmd();
      const double acceleration = axis_.toUserAccCmd();
      const double limit        = previous_velocity * acceleration < 0 ? 4 : 2;
      EXPECT_LE(fabs(acceleration), limit + 1e-8);
      EXPECT_LE(fabs(acceleration - previous_acceleration),
                40 / GetParam() + 1e-8);
      EXPECT_LE(fabs(velocity - previous_velocity), 4 / GetParam() + 1e-8);
      previous_velocity     = velocity;
      previous_acceleration = acceleration;
    }
    EXPECT_EQ(move.isInVelocity(), mcTRUE);
    EXPECT_NEAR(axis_.toUserVelCmd(), targets[phase], 1e-12);
    EXPECT_NEAR(axis_.toUserAccCmd(), 0, 1e-12);
  }
}

TEST_P(AxisCycleTimeTest, PowerRecoveryAbortsStandaloneSuperimposedMotion)
{
  checkSuperimposedRecovery(false, false);
}

TEST_P(AxisCycleTimeTest, PowerRecoveryAbortsOverlayAndUnderlyingMotion)
{
  checkSuperimposedRecovery(false, true);
}

TEST_P(AxisCycleTimeTest, ErrorRecoveryAbortsStandaloneSuperimposedMotion)
{
  checkSuperimposedRecovery(true, false);
}

TEST_P(AxisCycleTimeTest, ErrorRecoveryAbortsOverlayAndUnderlyingMotion)
{
  checkSuperimposedRecovery(true, true);
}

TEST_P(AxisCycleTimeTest, AxisErrorRecoveryClearsCommandsAndStartsMoveFromRest)
{
  checkAxisErrorRecovery();
}

INSTANTIATE_TEST_SUITE_P(CycleFrequencies, AxisCycleTimeTest,
                         ::testing::Values(250.0, 500.0, 1000.0, 2000.0));

class GearInRegressionTest : public FunctionBlockTest
{
protected:
  enum class ExecuteAtError
  {
    High,
    Low,
    Falling
  };

  void checkAxisLimitError(bool master_error, ExecuteAtError execute_at_error);

#ifdef PLOT
  void recordPlot()
  {
    plot_time_ = static_cast<double>(plot_cycle_++) / master_config_.frequency_;
    gear_plot_.add("Velocity", "Master actual", plot_time_,
                   master_.toUserVel());
    gear_plot_.add("Acceleration", "Master commanded", plot_time_,
                   master_.toUserAccCmd());
    gear_plot_.add("Axis state / error code", "Slave state", plot_time_,
                   slave_.getAxisState());
    gear_plot_.add("Axis state / error code", "Slave error", plot_time_,
                   slave_.getAxisError());
    gear_plot_.add("Velocity", "Slave commanded", plot_time_,
                   slave_.toUserVelCmd());
    gear_plot_.add("Velocity", "Slave actual", plot_time_, slave_.toUserVel());
    gear_plot_.add("Acceleration", "Slave commanded", plot_time_,
                   slave_.toUserAccCmd());
    gear_plot_.add("Position", "Slave commanded", plot_time_,
                   slave_.toUserPosCmd());
    gear_plot_.add("Position", "Slave actual", plot_time_, slave_.toUserPos());
    if (record_gear_status_ &&
        (gear_.isEnabled() == mcTRUE || gear_.isActive() == mcTRUE ||
         gear_.isDone() == mcTRUE || gear_.isAborted() == mcTRUE ||
         gear_.isError() != mcFALSE))
    {
      gear_plot_.add("Velocity", "Gear target (while active)", plot_time_,
                     gear_.isActive() == mcTRUE ? gear_.getVelocity() : NAN);
      gear_plot_.addBlock("Gear", gear_, plot_time_);
      gear_plot_.add("FB signals", "Gear.InGear", plot_time_,
                     gear_.getInGear() == mcTRUE);
    }
    gear_plot_.add("FB signals", "Master.Execute", plot_time_,
                   master_move_.isEnabled() == mcTRUE);
  }

  void TearDown() override
  {
    if (!gear_plot_.empty())
      gear_plot_.plot("", plot_description_);
    FunctionBlockTest::TearDown();
  }

  GearInTestPlot gear_plot_;
  bool record_gear_status_ = true;
  double plot_time_        = 0;
  size_t plot_cycle_       = 0;
  std::string plot_description_;
#endif

  void SetUp() override
  {
    FunctionBlockTest::SetUp();
    master_config_.frequency_ = 1000;
    slave_config_             = master_config_;
    master_.setAxisId(1);
    slave_.setAxisId(2);
    master_.setAxisConfig(&master_config_);
    slave_.setAxisConfig(&slave_config_);
    master_.setServo(&master_servo_);
    slave_.setServo(&slave_servo_);
    master_power_.setAxis(&master_);
    slave_power_.setAxis(&slave_);
    for (auto* power : { &master_power_, &slave_power_ })
    {
      power->setEnable(mcTRUE);
      power->setEnablePositive(mcTRUE);
      power->setEnableNegative(mcTRUE);
    }
    master_move_.setAxis(&master_);
    master_move_.setVelocity(500);
    master_move_.setAcceleration(4000);
    master_move_.setDeceleration(4000);
    master_move_.setJerk(1e12);
    master_move_.setBufferMode(mcAborting);
    gear_.setMaster(&master_);
    gear_.setSlave(&slave_);
    gear_.setAcceleration(1000);
    gear_.setDeceleration(1000);
    gear_.setJerk(1e12);
    gear_.setInGearThreshold(0.01);
    gear_.setBufferMode(mcAborting);
  }

  void runCycle()
  {
    runObservedCycle(master_, "master_");
    runObservedCycle(slave_, "slave_");
    runObservedCycle(master_power_, "master_power_");
    runObservedCycle(slave_power_, "slave_power_");
    runObservedCycle(master_move_, "master_move_");
    runObservedCycle(gear_, "gear_");
#ifdef PLOT
    recordPlot();
#endif
    ASSERT_EQ(master_.getAxisError(), mcErrorCodeGood);
    ASSERT_EQ(slave_.getAxisError(), mcErrorCodeGood);
    ASSERT_EQ(master_power_.isError(), mcFALSE);
    ASSERT_EQ(slave_power_.isError(), mcFALSE);
    ASSERT_EQ(master_move_.isError(), mcFALSE) << master_move_.getErrorID();
    ASSERT_EQ(gear_.isError(), mcFALSE) << gear_.getErrorID();
  }

  void runPositionGearCycle(FbGearInPos& position_gear, int cycle)
  {
    const int pulse_cycles = static_cast<int>(
        gear_in_pos_execute_pulse_seconds * master_config_.frequency_);
    position_gear.setExecute(cycle >= 6 && cycle < 6 + pulse_cycles ? mcTRUE :
                                                                      mcFALSE);
    runObservedCycle(position_gear, "position_gear");
    if (cycle >= 6 && cycle <= 6 + pulse_cycles)
      EXPECT_EQ(position_gear.isBusy(), mcTRUE);
  }

  AxisConfig master_config_, slave_config_;
  Servo master_servo_, slave_servo_;
  Axis master_, slave_;
  FbPower master_power_, slave_power_;
  FbMoveVelocity master_move_;
  FbGearIn gear_;
};

class GearInCycleTimeTest : public GearInRegressionTest,
                            public ::testing::WithParamInterface<double>
{
protected:
  void checkPositionGearRetrigger(bool during_acquisition, double direction);

  void configurePositionGear(FbGearInPos& position_gear, double velocity = 50)
  {
    master_config_.frequency_ = slave_config_.frequency_ = GetParam();
    master_.setAxisConfig(&master_config_);
    slave_.setAxisConfig(&slave_config_);
    master_move_.setVelocity(1);
    master_move_.setAcceleration(2);
    master_move_.setDeceleration(2);
    master_move_.setJerk(20);
    position_gear.setMaster(&master_);
    position_gear.setSlave(&slave_);
    position_gear.setRatioNumerator(1);
    position_gear.setRatioDenominator(2);
    position_gear.setMasterStartDistance(1);
    position_gear.setMasterSyncPosition(3);
    position_gear.setSlaveSyncPosition(1);
    position_gear.setVelocity(velocity);
    position_gear.setAcceleration(20);
    position_gear.setDeceleration(20);
    position_gear.setJerk(1000);
    position_gear.setBufferMode(mcAborting);
  }
};

void GearInCycleTimeTest::checkPositionGearRetrigger(bool during_acquisition,
                                                     double direction)
{
  FbGearInPos position_gear;
  configurePositionGear(position_gear);
  master_move_.setVelocity(direction);
  position_gear.setMasterStartDistance(direction);
  position_gear.setMasterSyncPosition(3 * direction);
  position_gear.setSlaveSyncPosition(direction);
  slave_.setNodeQueueSize(1);
  int retrigger_cycle  = -1;
  double sync_position = 0, slave_sync_position = 0;
  bool replaced = false, synchronized = false;
  for (int cycle = 0; cycle < 8 * GetParam(); ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    if (cycle == 5)
      master_move_.setExecute(mcTRUE);
    if (retrigger_cycle < 0 &&
        (during_acquisition ? position_gear.getStartSync() == mcTRUE &&
                                  fabs(slave_.toUserVelCmd()) > 0.1 :
                              position_gear.getInSync() == mcTRUE))
    {
      retrigger_cycle     = cycle;
      sync_position       = master_.toUserPosCmd() + 3 * direction;
      slave_sync_position = slave_.toUserPosCmd() + 2 * direction;
      position_gear.setMasterSyncPosition(sync_position);
      position_gear.setSlaveSyncPosition(slave_sync_position);
      position_gear.setRatioDenominator(1);
    }
    const bool execute =
        retrigger_cycle < 0 ?
            cycle >= 6 &&
                cycle < 6 + gear_in_pos_execute_pulse_seconds * GetParam() :
            cycle < retrigger_cycle +
                        gear_in_pos_execute_pulse_seconds * GetParam();
    position_gear.setExecute(execute ? mcTRUE : mcFALSE);
    runObservedCycle(position_gear, "position_gear");
    ASSERT_EQ(position_gear.isError(), mcFALSE);
    ASSERT_EQ(position_gear.isAborted(), mcFALSE);
    if (retrigger_cycle < 0)
      continue;
    if (cycle == retrigger_cycle)
    {
      // Input edits without another edge must affect neither relationship.
      position_gear.setRatioNumerator(7);
      position_gear.setMasterSyncPosition(sync_position + 100);
      position_gear.setSlaveSyncPosition(slave_sync_position + 100);
    }
    if (direction * (master_.toUserPosCmd() - sync_position + direction) < 0)
    {
      EXPECT_EQ(position_gear.isActive(), mcTRUE);
      EXPECT_EQ(position_gear.isBusy(), mcTRUE);
      if (!during_acquisition || position_gear.getInSync() == mcTRUE)
      {
        EXPECT_EQ(position_gear.getInSync(), mcTRUE);
        EXPECT_EQ(position_gear.isPositionCoupled(), mcTRUE);
        EXPECT_NEAR(slave_.toUserVelCmd(), 0.5 * direction, 0.001);
        EXPECT_NEAR(slave_.toUserPosCmd(),
                    direction + (master_.toUserPosCmd() - 3 * direction) / 2,
                    1e-6);
      }
    }
    else
    {
      replaced |= position_gear.getStartSync() == mcTRUE;
      ASSERT_LT(fabs(slave_.toUserVelCmd()), 2);
      if (replaced && position_gear.getInSync() == mcTRUE)
      {
        synchronized = true;
        EXPECT_NEAR(slave_.toUserVelCmd(), direction, 1e-8);
        EXPECT_NEAR(
            slave_.toUserPosCmd(),
            slave_sync_position + master_.toUserPosCmd() - sync_position, 1e-8);
      }
    }
  }
  EXPECT_GE(retrigger_cycle, 0);
  EXPECT_TRUE(replaced);
  EXPECT_TRUE(synchronized);
}

TEST_P(GearInCycleTimeTest, PositionGearRetriggerKeepsCouplingUntilReplacement)
{
  checkPositionGearRetrigger(false, 1);
}

TEST_P(GearInCycleTimeTest, PositionGearRetriggerKeepsNegativeDirectionCoupling)
{
  checkPositionGearRetrigger(false, -1);
}

TEST_P(GearInCycleTimeTest, PositionGearRetriggerPreservesActiveAcquisition)
{
  checkPositionGearRetrigger(true, 1);
}

TEST_P(GearInCycleTimeTest, AbortedPositionGearStaysInactiveWithGearSuccessor)
{
  FbGearInPos position_gear;
  configurePositionGear(position_gear);
  gear_.setRatioNumerator(1);
  gear_.setRatioDenominator(1);
  gear_.setAcceleration(20);
  gear_.setDeceleration(20);
  gear_.setJerk(1000);
  bool submitted = false, aborted = false, cleared = false;
  for (int cycle = 0; cycle < 6 * GetParam(); ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    if (cycle == 5)
      master_move_.setExecute(mcTRUE);
    if (!submitted && position_gear.getInSync() == mcTRUE)
    {
      gear_.setExecute(mcTRUE);
      submitted = true;
    }
    runPositionGearCycle(position_gear, cycle);
    aborted |= position_gear.isAborted() == mcTRUE;
    if (!aborted)
      continue;
    cleared |= position_gear.isAborted() == mcFALSE;
    EXPECT_EQ(position_gear.isBusy(), mcFALSE);
    EXPECT_EQ(position_gear.isActive(), mcFALSE);
    EXPECT_EQ(position_gear.isError(), mcFALSE);
    EXPECT_EQ(position_gear.getStartSync(), mcFALSE);
    EXPECT_EQ(position_gear.getInSync(), mcFALSE);
    EXPECT_EQ(position_gear.isPositionCoupled(), mcFALSE);
  }
  EXPECT_TRUE(submitted);
  EXPECT_TRUE(aborted);
  EXPECT_TRUE(cleared);
  EXPECT_EQ(gear_.getInGear(), mcTRUE);
}

TEST_P(GearInCycleTimeTest, ErrorStopTakesOverExistingSuperimposedMotion)
{
  FbGearInPos position_gear;
  configurePositionGear(position_gear, 0.4);
  FbMoveSuperimposed superimposed;
  superimposed.setAxis(&slave_);
  superimposed.setPosition(10);
  superimposed.setVelocity(1);
  superimposed.setAcceleration(10);
  superimposed.setDeceleration(10);
  superimposed.setJerk(100);
  bool submitted = false, fault = false, stopped = false;
  const double dt = 1 / GetParam();
  for (int cycle = 0; cycle < 6 * GetParam(); ++cycle)
  {
    const double position     = slave_.getPosCmd();
    const double velocity     = slave_.toUserVelCmd();
    const double acceleration = slave_.toUserAccCmd();
    ASSERT_NO_FATAL_FAILURE(runCycle());
    if (cycle == 5)
      master_move_.setExecute(mcTRUE);
    runPositionGearCycle(position_gear, cycle);
    if (!submitted && position_gear.getStartSync() == mcTRUE)
    {
      superimposed.setExecute(mcTRUE);
      submitted = true;
    }
    runObservedCycle(superimposed, "superimposed");
    ASSERT_EQ(superimposed.isError(), mcFALSE);
    if (slave_.isStoppingOnError())
    {
      if (!fault)
        EXPECT_GT(fabs(velocity), 0.4);
      fault = true;
      EXPECT_EQ(superimposed.isAborted(), mcTRUE);
      EXPECT_EQ(slave_.getAxisSuperimposedState(), mcFALSE);
      EXPECT_LE(fabs(slave_.toUserAccCmd() - acceleration), 1000 * dt + 1e-8);
      EXPECT_LE(fabs(slave_.toUserVelCmd() - velocity),
                std::max(20.0, fabs(acceleration)) * dt + 1e-8);
      EXPECT_LE(fabs(slave_.getPosCmd() - position - velocity * dt),
                0.5 * std::max(20.0, fabs(acceleration)) * dt * dt +
                    1000 * dt * dt * dt + 1e-8);
    }
    if (fault && slave_.getAxisState() == mcStandstill)
    {
      stopped = true;
      EXPECT_NEAR(slave_.toUserVelCmd(), 0, 1e-10);
      EXPECT_NEAR(slave_.toUserAccCmd(), 0, 1e-10);
      EXPECT_EQ(slave_.getAxisSuperimposedState(), mcFALSE);
    }
  }
  EXPECT_TRUE(submitted);
  EXPECT_TRUE(fault);
  EXPECT_TRUE(stopped);
  EXPECT_EQ(superimposed.isAborted(), mcTRUE);
}

TEST_P(GearInCycleTimeTest, PositionMoveReusesConfiguredGearNode)
{
  const double frequency    = GetParam();
  const double dt           = 1 / frequency;
  master_config_.frequency_ = slave_config_.frequency_ = frequency;
  slave_.setNodeQueueSize(1);
  master_.setAxisConfig(&master_config_);
  slave_.setAxisConfig(&slave_config_);
  master_move_.setVelocity(1);
  master_move_.setAcceleration(10);
  master_move_.setDeceleration(10);
  master_move_.setJerk(100);
  gear_.setRatioNumerator(1);
  gear_.setRatioDenominator(1);
  gear_.setAcceleration(10);
  gear_.setDeceleration(10);
  gear_.setJerk(100);
#ifdef PLOT
  plot_description_ =
      "Gear-to-position node reuse at " + std::to_string(frequency) + " Hz";
#endif
  for (int cycle = 0; cycle < 3 * frequency; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    if (master_power_.getPowerStatus() == mcTRUE &&
        slave_power_.getPowerStatus() == mcTRUE)
      master_move_.setExecute(mcTRUE);
    if (master_move_.isInVelocity() == mcTRUE)
      gear_.setExecute(mcTRUE);
  }
  EXPECT_EQ(gear_.getInGear(), mcTRUE);
  EXPECT_NEAR(slave_.toUserVel(), 1, 0.001);

  const double start_position  = slave_.toUserPos();
  const double destination     = start_position + 1;
  double previous_velocity     = slave_.toUserVelCmd();
  double previous_acceleration = slave_.toUserAccCmd();
  trajectory_processing::AxisPlanner reference;
  reference.setCondition(start_position, destination, previous_velocity, 0,
                         previous_acceleration, 0, NAN, 2, 10, 100, mcRuckig);
  reference.setFrequency(frequency);
  ASSERT_EQ(reference.onReplan(), mcErrorCodeGood);
  int expected_cycles = 0;
  for (int cycle = 1; cycle < 5 * frequency; ++cycle)
  {
    double position, velocity, acceleration;
    ASSERT_EQ(
        reference.onExecution(cycle * dt, &position, &velocity, &acceleration),
        mcErrorCodeGood);
    if (position >= destination - slave_config_.factor_.pos_ &&
        fabs(velocity) <= slave_config_.factor_.vel_)
    {
      expected_cycles = cycle;
      break;
    }
  }
  ASSERT_GT(expected_cycles, 0);

  // One slot forces the aborting position move to reuse GearIn's planner.
  FbMoveRelative next;
  next.setAxis(&slave_);
  next.setPosition(1);
  next.setVelocity(2);
  next.setAcceleration(10);
  next.setDeceleration(10);
  next.setJerk(100);
  next.setBufferMode(mcAborting);
  next.setExecute(mcTRUE);
  runObservedCycle(next, "next");
  ASSERT_EQ(next.isError(), mcFALSE);
  EXPECT_EQ(gear_.isAborted(), mcTRUE);
  int completion_cycles    = 0;
  double peak_acceleration = 0, peak_velocity_step = 0, peak_jerk = 0;
  for (int cycle = 1; cycle < 5 * frequency; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    runObservedCycle(next, "next");
#ifdef PLOT
    gear_plot_.addBlock("Next", next, plot_time_);
#endif
    ASSERT_EQ(next.isError(), mcFALSE);
    const double velocity     = slave_.toUserVelCmd();
    const double acceleration = slave_.toUserAccCmd();
    peak_acceleration         = std::max(peak_acceleration, fabs(acceleration));
    peak_velocity_step =
        std::max(peak_velocity_step, fabs(velocity - previous_velocity) / dt);
    peak_jerk =
        std::max(peak_jerk, fabs(acceleration - previous_acceleration) / dt);
    previous_velocity     = velocity;
    previous_acceleration = acceleration;
    if (next.isDone() == mcTRUE)
    {
      completion_cycles = cycle;
      break;
    }
  }
  ASSERT_GT(completion_cycles, 0);
  EXPECT_NEAR(completion_cycles * dt, expected_cycles * dt, 2 * dt);
  EXPECT_LE(peak_acceleration, 10.000001);
  EXPECT_LE(peak_velocity_step, 10.000001);
  EXPECT_LE(peak_jerk, 100.000001);
  EXPECT_NEAR(slave_.toUserPos(), destination, 0.001);
  EXPECT_NEAR(slave_.toUserVel(), 0, 0.001);
}

INSTANTIATE_TEST_SUITE_P(CycleFrequencies, GearInCycleTimeTest,
                         ::testing::Values(500.0, 1000.0, 2000.0));

struct GearInPosLockCase
{
  double frequency;
  mcINT numerator;
  mcUINT denominator;
};

class GearInPosLockTest
  : public GearInRegressionTest,
    public ::testing::WithParamInterface<GearInPosLockCase>
{
};

TEST_P(GearInCycleTimeTest, EngagementHonorsAsymmetricLimits)
{
  class GearTarget : public FbMoveVelocity
  {
  public:
    mcLREAL getVelocity() override
    {
      return getTargetVelocity();
    }
  };
  const double dt = 1 / GetParam();
  for (const double direction : { -1.0, 1.0 })
  {
    for (const bool stronger_braking : { false, true })
    {
      for (const double jerk : { 20.0, 10000.0 })
      {
        for (const int scenario : { 0, 1, 2, 3 })
        {
          SCOPED_TRACE(::testing::Message()
                       << direction << ", braking=" << stronger_braking
                       << ", scenario=" << scenario << ", jerk=" << jerk);
          const double acceleration   = stronger_braking ? 1 : 100;
          const double deceleration   = stronger_braking ? 100 : 1;
          const double start_velocity = scenario == 0 ? 0 : 2 * direction;
          GearTarget target;
          target.setAxis(&slave_);
          target.setTargetVelocity(direction);
          ExecutionNode node;
          node.setFrequency(GetParam());
          node.setBasicParams(&target, mcGearInMode, NAN, direction,
                              acceleration, deceleration, jerk, mcAborting,
                              mcRuckig);
          node.setStartPos(0);
          node.setStartVel(start_velocity);
          node.setStartAcc(0);
          node.setTerminateCondition(0);
          MC_AXIS_STATES state = mcStandstill;
          node.onActive(&state);
          double position = 0, velocity = start_velocity, acc = 0;
          double peak_acceleration = 0, peak_deceleration = 0, peak_jerk = 0;
          bool synchronized = false;
          const double ramp = stronger_braking ? 0.1 : (jerk < 100 ? 2 : 10);
          for (int cycle = 1; cycle <= 6 * GetParam(); ++cycle)
          {
            const double goal = scenario == 0 ?
                                    direction * (0.1 + ramp * cycle * dt) :
                                    (scenario == 1 ? 0.5 :
                                     scenario == 2 ? -1 :
                                                     0) *
                                        direction;
            target.setTargetVelocity(goal);
            const double previous_velocity = velocity, previous_acc = acc;
            node.onExecution(0, 0);
            node.getCommands(&position, &velocity, &acc);
#ifdef PLOT
            FunctionBlockObservations::commands(position, velocity, acc);
#endif
            ASSERT_EQ(node.isError(), mcFALSE);
            if (!synchronized)
            {
              const double sampled_acc = (velocity - previous_velocity) / dt;
              if (previous_velocity * sampled_acc < 0)
                peak_deceleration =
                    std::max(peak_deceleration, fabs(sampled_acc));
              else
                peak_acceleration =
                    std::max(peak_acceleration, fabs(sampled_acc));
              peak_jerk = std::max(peak_jerk, fabs(acc - previous_acc) / dt);
            }
            synchronized |= node.isGearSynchronized() == mcTRUE;
            if (scenario == 0 && !stronger_braking &&
                cycle == static_cast<int>(GetParam()))
              EXPECT_TRUE(synchronized);
          }
          EXPECT_TRUE(synchronized);
          EXPECT_NEAR(velocity, target.getVelocity(), 1e-8);
          EXPECT_LE(peak_acceleration, acceleration + 1e-6);
          EXPECT_LE(peak_deceleration, deceleration + 1e-6);
          EXPECT_LE(peak_jerk, jerk + 1e-6);
        }
      }
    }
  }
}

TEST_P(GearInCycleTimeTest, AsymmetricGearCatchesAcceleratingMaster)
{
  master_config_.frequency_ = slave_config_.frequency_ = GetParam();
  master_.setAxisConfig(&master_config_);
  slave_.setAxisConfig(&slave_config_);
  master_move_.setVelocity(50);
  master_move_.setAcceleration(10);
  master_move_.setDeceleration(10);
  master_move_.setJerk(10000);
  gear_.setRatioNumerator(-1);
  gear_.setRatioDenominator(1);
  gear_.setAcceleration(100);
  gear_.setDeceleration(1);
  gear_.setJerk(10000);
  bool synchronized = false;
  for (int cycle = 0; cycle < 2 * GetParam(); ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    if (cycle == 5)
      master_move_.setExecute(mcTRUE);
    if (cycle == static_cast<int>(GetParam() / 10))
      gear_.setExecute(mcTRUE);
    synchronized |= gear_.getInGear() == mcTRUE;
    if (cycle == static_cast<int>(GetParam()))
      EXPECT_TRUE(synchronized);
  }
  EXPECT_EQ(gear_.getInGear(), mcTRUE);
  EXPECT_NEAR(slave_.toUserVel(), -master_.toUserVel(), 0.01);
}

TEST_P(GearInPosLockTest, MaintainsPositionRelationshipThroughReversalAndStop)
{
  const auto param   = GetParam();
  const double ratio = static_cast<double>(param.numerator) / param.denominator;
#ifdef PLOT
  record_gear_status_ = false;
  plot_description_   = std::to_string(param.frequency) + " Hz, ratio " +
                      std::to_string(param.numerator) + ":" +
                      std::to_string(param.denominator) + ", pulsed Execute";
#endif
  master_config_.frequency_ = slave_config_.frequency_ = param.frequency;
  master_.setAxisConfig(&master_config_);
  slave_.setAxisConfig(&slave_config_);
  master_move_.setVelocity(1);
  master_move_.setAcceleration(2);
  master_move_.setDeceleration(2);
  master_move_.setJerk(20);
  FbMoveVelocity reverse;
  reverse.setAxis(&master_);
  reverse.setVelocity(-1);
  reverse.setAcceleration(2);
  reverse.setDeceleration(2);
  reverse.setJerk(20);
  reverse.setBufferMode(mcAborting);
  FbHalt halt;
  halt.setAxis(&master_);
  halt.setDeceleration(2);
  halt.setJerk(20);
  halt.setBufferMode(mcAborting);
  FbGearInPos position_gear;
  position_gear.setMaster(&master_);
  position_gear.setSlave(&slave_);
  position_gear.setRatioNumerator(param.numerator);
  position_gear.setRatioDenominator(param.denominator);
  position_gear.setMasterStartDistance(1);
  position_gear.setMasterSyncPosition(3);
  position_gear.setSlaveSyncPosition(1);
  position_gear.setVelocity(50);
  position_gear.setAcceleration(500);
  position_gear.setDeceleration(500);
  position_gear.setPosSyncFactor(0.01);
  position_gear.setVelSyncFactor(0.05);
  position_gear.setBufferMode(mcAborting);
  int first_sync            = -1;
  bool saw_start_sync       = false;
  double peak_command_error = 0, peak_feedback_error = 0;
  for (int cycle = 0; cycle < 9 * param.frequency; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    runObservedCycle(reverse, "reverse");
    runObservedCycle(halt, "halt");
    runPositionGearCycle(position_gear, cycle);
    ASSERT_EQ(position_gear.isError(), mcFALSE) << position_gear.getErrorID();
    ASSERT_EQ(reverse.isError(), mcFALSE);
    ASSERT_EQ(halt.isError(), mcFALSE);
    if (cycle == 4 && param.numerator < 0)
    {
      ASSERT_EQ(master_.setHomePositionOffset(0.25), mcTRUE);
      ASSERT_EQ(slave_.setHomePositionOffset(0.75), mcTRUE);
    }
    if (cycle == 5)
      master_move_.setExecute(mcTRUE);
    if (cycle == 4 * param.frequency)
      reverse.setExecute(mcTRUE);
    if (cycle == 7 * param.frequency)
      halt.setExecute(mcTRUE);
    if (position_gear.getStartSync() == mcTRUE)
      saw_start_sync = true;
    if (position_gear.getInSync() == mcTRUE)
    {
      ASSERT_EQ(position_gear.getStartSync(), mcFALSE);
      if (first_sync < 0)
        first_sync = cycle;
    }
    const double expected = 1 + (master_.toUserPosCmd() - 3) * ratio;
    if (first_sync >= 0 && cycle > first_sync + 2)
    {
      EXPECT_EQ(position_gear.getInSync(), mcTRUE);
      peak_command_error =
          std::max(peak_command_error, fabs(slave_.toUserPosCmd() - expected));
      peak_feedback_error =
          std::max(peak_feedback_error, fabs(slave_.toUserPos() - expected));
    }
#ifdef PLOT
    gear_plot_.addPositionGear(position_gear, master_, slave_, plot_time_,
                               expected, ratio);
#endif
    if (cycle == 6 * param.frequency)
    {
      ASSERT_EQ(position_gear.getInSync(), mcTRUE);
      // Exercise the public command-input path with a deliberately displaced
      // position. InSync must not remain latched on velocity agreement alone.
      slave_.runCycle(slave_.getPosCmd() + 0.02, slave_.toUserVelCmd());
#ifdef PLOT
      FunctionBlockObservations::cycle(slave_, "slave_");
#endif
      runObservedCycle(position_gear, "position_gear");
      EXPECT_EQ(position_gear.getInSync(), mcFALSE);
      EXPECT_EQ(position_gear.getStartSync(), mcFALSE);
      EXPECT_EQ(position_gear.isReadyForBufferedHandoff(), mcFALSE);
#ifdef PLOT
      // The test injects an extra command cycle between scheduled cycles.
      gear_plot_.addPositionGear(position_gear, master_, slave_,
                                 plot_time_ + 0.5 / param.frequency, expected,
                                 ratio);
#endif
    }
  }
  ASSERT_GE(first_sync, 0);
  EXPECT_EQ(position_gear.isEnabled(), mcFALSE);
  EXPECT_TRUE(saw_start_sync);
  EXPECT_LT(first_sync, 4 * param.frequency);
  EXPECT_LE(peak_command_error, 1e-9);
  EXPECT_LE(peak_feedback_error, 2e-6);
  EXPECT_EQ(halt.isDone(), mcTRUE);
  EXPECT_NEAR(slave_.toUserVel(), 0, 0.001);
  FbMoveRelative successor;
  successor.setAxis(&slave_);
  successor.setPosition(0.1);
  successor.setVelocity(1);
  successor.setAcceleration(10);
  successor.setDeceleration(10);
  successor.setJerk(100);
  successor.setBufferMode(mcBuffered);
  successor.setExecute(mcTRUE);
  for (int cycle = 0; cycle < param.frequency; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    runObservedCycle(successor, "successor");
    runObservedCycle(position_gear, "position_gear");
    ASSERT_EQ(successor.isError(), mcFALSE);
#ifdef PLOT
    gear_plot_.addPositionGear(position_gear, master_, slave_, plot_time_,
                               1 + (master_.toUserPosCmd() - 3) * ratio, ratio);
    gear_plot_.addBlock("Successor", successor, plot_time_);
#endif
    if (cycle > 2)
    {
      EXPECT_EQ(position_gear.getInSync(), mcFALSE);
      EXPECT_EQ(position_gear.getStartSync(), mcFALSE);
      EXPECT_EQ(position_gear.isPositionCoupled(), mcFALSE);
    }
  }
  EXPECT_EQ(successor.isDone(), mcTRUE);
}

TEST_P(GearInPosLockTest, AcquisitionPreservesMotionAndStatusContinuity)
{
  const auto param   = GetParam();
  const double ratio = static_cast<double>(param.numerator) / param.denominator;
  const double master_velocity = param.numerator < 0 ? -1.2 : 0.8;
  const double direction       = master_velocity < 0 ? -1 : 1;
  const double dt              = 1 / param.frequency;
#ifdef PLOT
  record_gear_status_ = false;
  plot_description_   = "Acquisition continuity, " +
                      std::to_string(param.frequency) + " Hz, ratio " +
                      std::to_string(param.numerator) + ":" +
                      std::to_string(param.denominator) + ", pulsed Execute";
#endif
  master_config_.frequency_ = slave_config_.frequency_ = param.frequency;
  master_.setAxisConfig(&master_config_);
  slave_.setAxisConfig(&slave_config_);
  master_move_.setVelocity(master_velocity);
  master_move_.setAcceleration(2);
  master_move_.setDeceleration(2);
  master_move_.setJerk(20);
  FbGearInPos position_gear;
  position_gear.setMaster(&master_);
  position_gear.setSlave(&slave_);
  position_gear.setRatioNumerator(param.numerator);
  position_gear.setRatioDenominator(param.denominator);
  position_gear.setMasterStartDistance(direction);
  position_gear.setMasterSyncPosition(3 * direction);
  position_gear.setSlaveSyncPosition(1);
  position_gear.setVelocity(50);
  position_gear.setAcceleration(30);
  position_gear.setDeceleration(30);
  position_gear.setJerk(5000);
  position_gear.setBufferMode(mcAborting);
  bool was_active = false, synchronized = false;
  double previous_position = 0, previous_velocity = 0,
         previous_acceleration  = 0;
  double peak_velocity_residual = 0, peak_acceleration = 0, peak_jerk = 0;
  double peak_feedback_residual = 0;
  for (int cycle = 0; cycle < 6 * param.frequency; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    runPositionGearCycle(position_gear, cycle);
    ASSERT_EQ(position_gear.isError(), mcFALSE) << position_gear.getErrorID();
    if (cycle == 5)
      master_move_.setExecute(mcTRUE);
    const double position     = slave_.toUserPosCmd();
    const double velocity     = slave_.toUserVelCmd();
    const double acceleration = slave_.toUserAccCmd();
    if (was_active)
    {
      EXPECT_EQ(position_gear.isActive(), mcTRUE);
      EXPECT_EQ(position_gear.isBusy(), mcTRUE);
      EXPECT_EQ(position_gear.isAborted(), mcFALSE);
      peak_velocity_residual = std::max(
          peak_velocity_residual, fabs((position - previous_position) / dt -
                                       (velocity + previous_velocity) / 2));
      peak_feedback_residual = std::max(
          peak_feedback_residual,
          fabs(slave_.toUserVel() - (velocity + previous_velocity) / 2));
      peak_acceleration = std::max(peak_acceleration,
                                   fabs((velocity - previous_velocity) / dt));
      peak_jerk         = std::max(peak_jerk,
                           fabs((acceleration - previous_acceleration) / dt));
    }
    if (position_gear.isActive() == mcTRUE)
      was_active = true;
    if (position_gear.getInSync() == mcTRUE)
      synchronized = true;
    const double expected =
        1 + (master_.toUserPosCmd() - 3 * direction) * ratio;
    if (synchronized)
    {
      EXPECT_EQ(position_gear.getInSync(), mcTRUE);
      EXPECT_EQ(position_gear.getStartSync(), mcFALSE);
      EXPECT_NEAR(position, expected, 1e-9);
    }
#ifdef PLOT
    gear_plot_.addPositionGear(position_gear, master_, slave_, plot_time_,
                               expected, ratio);
#endif
    previous_position     = position;
    previous_velocity     = velocity;
    previous_acceleration = acceleration;
  }
  EXPECT_TRUE(synchronized);
  EXPECT_EQ(position_gear.isEnabled(), mcFALSE);
  // Trapezoidal integration error is bounded by jerk * dt^2 / 12.
  EXPECT_LE(peak_velocity_residual, 5000 * dt * dt / 12 + 1e-8);
  EXPECT_LE(peak_feedback_residual, 5000 * dt * dt / 12 + 2e-6 / dt + 1e-8);
  EXPECT_LE(peak_acceleration, 30.000001);
  EXPECT_LE(peak_jerk, 5000.000001);
  printf("GearInPos acquisition: %.0f Hz, ratio %.3f, "
         "velocity residual=%.9g, acceleration=%.9g, jerk=%.9g\n",
         param.frequency, ratio, peak_velocity_residual, peak_acceleration,
         peak_jerk);
}

INSTANTIATE_TEST_SUITE_P(PositionLock, GearInPosLockTest,
                         ::testing::Values(GearInPosLockCase{ 500, 1, 1 },
                                           GearInPosLockCase{ 1000, 1, 2 },
                                           GearInPosLockCase{ 2000, -1, 2 },
                                           GearInPosLockCase{ 1000, 3, 2 }));

TEST_F(GearInRegressionTest,
       PositionGearPreservesSuccessorQueuedDuringAcquisition)
{
#ifdef PLOT
  record_gear_status_ = false;
  plot_description_ = "Pulsed Execute, buffered successor queued before InSync";
#endif
  master_move_.setVelocity(1);
  FbGearInPos position_gear;
  position_gear.setMaster(&master_);
  position_gear.setSlave(&slave_);
  position_gear.setRatioNumerator(1);
  position_gear.setRatioDenominator(2);
  position_gear.setMasterStartDistance(1);
  position_gear.setMasterSyncPosition(3);
  position_gear.setSlaveSyncPosition(1);
  position_gear.setVelocity(50);
  position_gear.setAcceleration(500);
  position_gear.setDeceleration(500);
  position_gear.setBufferMode(mcAborting);
  FbMoveRelative successor;
  successor.setAxis(&slave_);
  successor.setPosition(1);
  successor.setVelocity(1);
  successor.setAcceleration(10);
  successor.setDeceleration(10);
  successor.setJerk(100);
  successor.setBufferMode(mcBuffered);
  bool queued = false, synchronized = false, handed_off = false;
  for (int cycle = 0; cycle < 6000; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    runObservedCycle(successor, "successor");
    runPositionGearCycle(position_gear, cycle);
    ASSERT_EQ(position_gear.isError(), mcFALSE);
    ASSERT_EQ(successor.isError(), mcFALSE);
    ASSERT_EQ(successor.isAborted(), mcFALSE);
    if (cycle == 5)
      master_move_.setExecute(mcTRUE);
    if (!queued && position_gear.getStartSync() == mcTRUE)
    {
      ASSERT_EQ(position_gear.getInSync(), mcFALSE);
      successor.setExecute(mcTRUE);
      queued = true;
    }
    if (position_gear.getInSync() == mcTRUE)
      synchronized = true;
    if (!synchronized)
    {
      EXPECT_EQ(successor.isActive(), mcFALSE);
      EXPECT_EQ(position_gear.isAborted(), mcFALSE);
    }
    if (successor.isActive() == mcTRUE && !handed_off)
    {
      handed_off = true;
      EXPECT_TRUE(synchronized);
      EXPECT_EQ(position_gear.isAborted(), mcTRUE);
      EXPECT_EQ(position_gear.getInSync(), mcFALSE);
      EXPECT_EQ(position_gear.getStartSync(), mcFALSE);
    }
#ifdef PLOT
    gear_plot_.addPositionGear(position_gear, master_, slave_, plot_time_,
                               1 + (master_.toUserPosCmd() - 3) / 2, 0.5);
    gear_plot_.addBlock("Successor", successor, plot_time_);
#endif
  }
  EXPECT_TRUE(queued);
  EXPECT_TRUE(synchronized);
  EXPECT_TRUE(handed_off);
  EXPECT_EQ(position_gear.isEnabled(), mcFALSE);
  EXPECT_EQ(successor.isDone(), mcTRUE);
}

TEST_F(GearInRegressionTest, PositionGearClearsInSyncOnMasterError)
{
#ifdef PLOT
  record_gear_status_ = false;
  plot_description_   = "Master velocity-limit fault after Execute pulse";
#endif
  master_move_.setVelocity(1);
  FbGearInPos position_gear;
  position_gear.setMaster(&master_);
  position_gear.setSlave(&slave_);
  position_gear.setRatioNumerator(1);
  position_gear.setRatioDenominator(1);
  position_gear.setMasterStartDistance(1);
  position_gear.setMasterSyncPosition(3);
  position_gear.setSlaveSyncPosition(3);
  position_gear.setVelocity(50);
  position_gear.setAcceleration(500);
  position_gear.setDeceleration(500);
  position_gear.setBufferMode(mcAborting);
  for (int cycle = 0; cycle < 4500; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    runPositionGearCycle(position_gear, cycle);
    ASSERT_EQ(position_gear.isError(), mcFALSE);
#ifdef PLOT
    gear_plot_.addPositionGear(position_gear, master_, slave_, plot_time_,
                               master_.toUserPosCmd(), 1);
#endif
    if (cycle == 5)
      master_move_.setExecute(mcTRUE);
  }
  ASSERT_EQ(position_gear.getInSync(), mcTRUE);
  ASSERT_EQ(position_gear.isEnabled(), mcFALSE);
  master_config_.sw_vel_limit_ = mcTRUE;
  master_config_.vel_limit_    = 0.5;
  for (int cycle = 0; cycle < 10; ++cycle)
  {
    runObservedCycle(master_, "master_");
    runObservedCycle(slave_, "slave_");
    runObservedCycle(position_gear, "position_gear");
#ifdef PLOT
    recordPlot();
    gear_plot_.addPositionGear(position_gear, master_, slave_, plot_time_,
                               master_.toUserPosCmd(), 1);
#endif
    EXPECT_EQ(position_gear.getInSync(), mcFALSE);
    EXPECT_EQ(position_gear.getStartSync(), mcFALSE);
    EXPECT_EQ(position_gear.isPositionCoupled(), mcFALSE);
    EXPECT_EQ(position_gear.isReadyForBufferedHandoff(), mcFALSE);
    EXPECT_EQ(position_gear.isActive(), mcFALSE);
    EXPECT_EQ(position_gear.isBusy(), mcFALSE);
    EXPECT_NE(position_gear.isError(), mcFALSE);
    EXPECT_EQ(position_gear.getErrorID(), mcErrorCodeVelocityOverLimit);
  }
}

class GearInPosStartSyncTest : public GearInRegressionTest,
                               public ::testing::WithParamInterface<bool>
{
};

TEST_P(GearInPosStartSyncTest, ClearsWhenAcquisitionTerminates)
{
#ifdef PLOT
  record_gear_status_ = false;
  plot_description_   = GetParam() ?
                            "Pulsed Execute, master fault during acquisition" :
                            "Pulsed Execute, aborting halt during acquisition";
#endif
  master_move_.setVelocity(1);
  FbGearInPos position_gear;
  position_gear.setMaster(&master_);
  position_gear.setSlave(&slave_);
  position_gear.setRatioNumerator(1);
  position_gear.setRatioDenominator(1);
  position_gear.setMasterStartDistance(1);
  position_gear.setMasterSyncPosition(3);
  position_gear.setSlaveSyncPosition(3);
  position_gear.setVelocity(50);
  position_gear.setAcceleration(500);
  position_gear.setDeceleration(500);
  position_gear.setBufferMode(mcAborting);
  FbHalt halt;
  halt.setAxis(&slave_);
  halt.setDeceleration(500);
  halt.setJerk(5000);
  halt.setBufferMode(mcAborting);
  bool started = false;
  for (int cycle = 0; cycle < 3000; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    runPositionGearCycle(position_gear, cycle);
    ASSERT_EQ(position_gear.isError(), mcFALSE);
#ifdef PLOT
    gear_plot_.addPositionGear(position_gear, master_, slave_, plot_time_,
                               master_.toUserPosCmd(), 1);
#endif
    if (cycle == 5)
      master_move_.setExecute(mcTRUE);
    if (position_gear.getStartSync() == mcTRUE)
    {
      ASSERT_EQ(position_gear.getInSync(), mcFALSE);
      started = true;
      break;
    }
  }
  ASSERT_TRUE(started);
  ASSERT_EQ(position_gear.isEnabled(), mcFALSE);
  if (GetParam())
  {
    master_config_.sw_vel_limit_ = mcTRUE;
    master_config_.vel_limit_    = 0.5;
  }
  else
    halt.setExecute(mcTRUE);
  bool saw_abort = false;
  for (int cycle = 0; cycle < 10; ++cycle)
  {
    runObservedCycle(master_, "master_");
    runObservedCycle(slave_, "slave_");
    runObservedCycle(halt, "halt");
    runObservedCycle(position_gear, "position_gear");
    if (position_gear.isAborted() == mcTRUE)
      saw_abort = true;
#ifdef PLOT
    recordPlot();
    gear_plot_.addPositionGear(position_gear, master_, slave_, plot_time_,
                               master_.toUserPosCmd(), 1);
#endif
    if (cycle > 1)
    {
      ASSERT_EQ(position_gear.getStartSync(), mcFALSE);
      EXPECT_EQ(position_gear.getInSync(), mcFALSE);
      if (GetParam())
        EXPECT_EQ(position_gear.getErrorID(), mcErrorCodeVelocityOverLimit);
    }
  }
  if (!GetParam())
    EXPECT_TRUE(saw_abort);
}

INSTANTIATE_TEST_SUITE_P(AcquisitionTermination, GearInPosStartSyncTest,
                         ::testing::Bool());

struct GearInPosLimitCase
{
  double frequency;
  double velocity;
  double acceleration;
  double deceleration;
  double jerk;
  double direction;
  bool changing_master = false;
};

class GearInPosLimitTest
  : public GearInRegressionTest,
    public ::testing::WithParamInterface<GearInPosLimitCase>
{
};

TEST_P(GearInPosLimitTest, RejectsInfeasibleAcquisitionAndStopsWithinLimits)
{
  const auto limits = GetParam();
  const double dt   = 1 / limits.frequency;
#ifdef PLOT
  record_gear_status_ = false;
  plot_description_ =
      "Infeasible acquisition: v=" + std::to_string(limits.velocity) +
      ", a=" + std::to_string(limits.acceleration) +
      ", d=" + std::to_string(limits.deceleration) +
      ", j=" + std::to_string(limits.jerk);
#endif
  master_config_.frequency_ = slave_config_.frequency_ = limits.frequency;
  master_.setAxisConfig(&master_config_);
  slave_.setAxisConfig(&slave_config_);
  master_move_.setVelocity(limits.direction);
  master_move_.setAcceleration(2);
  master_move_.setDeceleration(2);
  master_move_.setJerk(20);
  FbMoveVelocity master_change;
  master_change.setAxis(&master_);
  master_change.setVelocity(5);
  master_change.setAcceleration(5);
  master_change.setDeceleration(5);
  master_change.setJerk(1000);
  master_change.setBufferMode(mcAborting);
  FbGearInPos position_gear;
  position_gear.setMaster(&master_);
  position_gear.setSlave(&slave_);
  position_gear.setRatioNumerator(1);
  position_gear.setRatioDenominator(2);
  position_gear.setMasterStartDistance(limits.direction);
  position_gear.setMasterSyncPosition(3 * limits.direction);
  position_gear.setSlaveSyncPosition(limits.direction);
  position_gear.setVelocity(limits.velocity);
  position_gear.setAcceleration(limits.acceleration);
  position_gear.setDeceleration(limits.deceleration);
  position_gear.setJerk(limits.jerk);
  position_gear.setBufferMode(mcAborting);
  FbMoveRelative successor;
  successor.setAxis(&slave_);
  successor.setPosition(limits.direction);
  successor.setVelocity(1);
  successor.setAcceleration(10);
  successor.setDeceleration(10);
  successor.setJerk(100);
  successor.setBufferMode(mcBuffered);
  bool queued = false, successor_aborted = false, saw_error = false;
  bool successor_rejected = false, submission_during_stop = false;
  bool successor_submitted = false;
  bool stopped             = false;
  double velocity = 0, acceleration = 0, position = 0;
  double peak_velocity = 0, peak_acceleration = 0, peak_deceleration = 0;
  double peak_jerk = 0, peak_position_residual = 0;
  double fault_position = 0, fault_master_position = 0, stop_position = 0;
  double fault_velocity = 0;
  bool master_changed   = false;
  for (int cycle = 0; cycle < 8 * limits.frequency; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    runObservedCycle(master_change, "master_change");
    if (queued && !successor_submitted)
    {
      submission_during_stop = slave_.isStoppingOnError();
      successor_submitted    = true;
    }
    runObservedCycle(successor, "successor");
    runPositionGearCycle(position_gear, cycle);
    if (cycle == 5)
      master_move_.setExecute(mcTRUE);
    if (!queued && position_gear.getStartSync() == mcTRUE)
    {
      successor.setExecute(mcTRUE);
      queued = true;
    }
    if (limits.changing_master && !master_changed &&
        fabs(slave_.toUserVelCmd()) > 0.3)
    {
      master_change.setExecute(mcTRUE);
      master_changed = true;
    }
    successor_aborted |= successor.isAborted() == mcTRUE;
    if (successor.isError() != mcFALSE)
    {
      EXPECT_TRUE(submission_during_stop);
      EXPECT_EQ(successor.getErrorID(), mcErrorCodeAxisStateViolation);
      successor_rejected = true;
    }
    EXPECT_EQ(successor.isActive(), mcFALSE);
    EXPECT_EQ(position_gear.getInSync(), mcFALSE);
    const double next_position     = slave_.toUserPosCmd();
    const double next_velocity     = slave_.toUserVelCmd();
    const double next_acceleration = slave_.toUserAccCmd();
    peak_velocity = std::max(peak_velocity, fabs(next_velocity));
    const double velocity_acceleration = (next_velocity - velocity) / dt;
    if (velocity * velocity_acceleration < 0)
      peak_deceleration =
          std::max(peak_deceleration, fabs(velocity_acceleration));
    else
      peak_acceleration =
          std::max(peak_acceleration, fabs(velocity_acceleration));
    peak_jerk =
        std::max(peak_jerk, fabs(next_acceleration - acceleration) / dt);
    peak_position_residual =
        std::max(peak_position_residual, fabs((next_position - position) / dt -
                                              (next_velocity + velocity) / 2));
    EXPECT_LE(fabs(slave_.toUserVel()), limits.velocity + 2e-6 / dt);
    if (position_gear.isError() != mcFALSE)
    {
      EXPECT_EQ(position_gear.getErrorID(), mcErrorCodeSlaveExceedLimit);
      EXPECT_EQ(position_gear.getStartSync(), mcFALSE);
      EXPECT_EQ(position_gear.isActive(), mcFALSE);
      EXPECT_EQ(position_gear.isBusy(), mcFALSE);
      if (!saw_error)
      {
        fault_position        = next_position;
        fault_velocity        = velocity;
        fault_master_position = master_.toUserPosCmd();
      }
      saw_error = true;
    }
    if (saw_error && !stopped && fabs(next_velocity) < 1e-9 &&
        fabs(next_acceleration) < 1e-9 && slave_.getAxisState() == mcStandstill)
    {
      stopped       = true;
      stop_position = next_position;
    }
    if (stopped)
    {
      EXPECT_NEAR(next_position, stop_position, 1e-9);
      EXPECT_NEAR(next_velocity, 0, 1e-9);
    }
#ifdef PLOT
    gear_plot_.addPositionGear(
        position_gear, master_, slave_, plot_time_,
        limits.direction + (master_.toUserPosCmd() - 3 * limits.direction) / 2,
        0.5);
    gear_plot_.addBlock("Successor", successor, plot_time_);
#endif
    position     = next_position;
    velocity     = next_velocity;
    acceleration = next_acceleration;
  }
  EXPECT_TRUE(saw_error);
  EXPECT_TRUE(stopped);
  EXPECT_EQ(successor_rejected, submission_during_stop);
  EXPECT_EQ(successor_aborted, !submission_during_stop);
  EXPECT_EQ(master_changed, limits.changing_master);
  EXPECT_LE(peak_velocity, limits.velocity + 1e-8);
  EXPECT_LE(peak_acceleration, limits.acceleration + 1e-6);
  EXPECT_LE(peak_deceleration, limits.deceleration + 1e-6);
  EXPECT_LE(peak_jerk, limits.jerk + 1e-6);
  EXPECT_LE(peak_position_residual, limits.jerk * dt * dt / 12 + 1e-8);
  EXPECT_GT(fabs(master_.toUserPosCmd() - fault_master_position), 1);
  if (limits.jerk > 5)
  {
    EXPECT_GT(fabs(fault_velocity), 0.001);
    EXPECT_GT(fabs(stop_position - fault_position), 1e-6);
  }
  ASSERT_TRUE(stopped);
  successor.setExecute(mcFALSE);
  runObservedCycle(successor, "successor");
  successor.setBufferMode(mcAborting);
  successor.setExecute(mcTRUE);
  for (int cycle = 0; cycle < 2 * limits.frequency; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    runObservedCycle(master_change, "master_change");
    runObservedCycle(successor, "successor");
    runObservedCycle(position_gear, "position_gear");
    ASSERT_EQ(successor.isError(), mcFALSE);
#ifdef PLOT
    gear_plot_.addPositionGear(
        position_gear, master_, slave_, plot_time_,
        limits.direction + (master_.toUserPosCmd() - 3 * limits.direction) / 2,
        0.5);
    gear_plot_.addBlock("Successor", successor, plot_time_);
#endif
  }
  EXPECT_EQ(successor.isDone(), mcTRUE);
  EXPECT_NEAR(slave_.toUserPosCmd(), stop_position + limits.direction, 1e-6);
}

INSTANTIATE_TEST_SUITE_P(
    InfeasibleLimits, GearInPosLimitTest,
    ::testing::Values(GearInPosLimitCase{ 500, 0.4, 20, 20, 1000, 1 },
                      GearInPosLimitCase{ 1000, 20, 1, 20, 1000, 1 },
                      GearInPosLimitCase{ 2000, 20, 20, 1, 1000, 1 },
                      GearInPosLimitCase{ 1000, 20, 20, 20, 5, 1 },
                      GearInPosLimitCase{ 1000, 1.2, 20, 1, 100, 1 },
                      GearInPosLimitCase{ 2000, 0.4, 20, 20, 1000, -1 },
                      GearInPosLimitCase{ 500, 20, 20, 1, 1000, -1 },
                      GearInPosLimitCase{ 1000, 20, 20, 20, 100, 1, true }));

TEST_P(GearInCycleTimeTest, ErrorStopRejectsReplacementBeforeQueueMutation)
{
  for (const int capacity : { 1, 2 })
  {
    SCOPED_TRACE(capacity);
    AxisConfig config;
    config.frequency_ = GetParam();
    Axis master, slave;
    Servo master_servo, slave_servo;
    master.setAxisConfig(&config);
    slave.setAxisConfig(&config);
    slave.setNodeQueueSize(capacity);
    master.setServo(&master_servo);
    slave.setServo(&slave_servo);
    FbPower master_power, slave_power;
    master_power.setAxis(&master);
    slave_power.setAxis(&slave);
    for (auto* power : { &master_power, &slave_power })
    {
      power->setEnable(mcTRUE);
      power->setEnablePositive(mcTRUE);
      power->setEnableNegative(mcTRUE);
    }
    FbMoveVelocity master_move;
    master_move.setAxis(&master);
    master_move.setVelocity(1);
    master_move.setAcceleration(2);
    master_move.setDeceleration(2);
    master_move.setJerk(20);
    FbGearInPos gear;
    gear.setMaster(&master);
    gear.setSlave(&slave);
    gear.setRatioNumerator(1);
    gear.setRatioDenominator(2);
    gear.setMasterStartDistance(1);
    gear.setMasterSyncPosition(3);
    gear.setSlaveSyncPosition(1);
    gear.setVelocity(0.4);
    gear.setAcceleration(20);
    gear.setDeceleration(20);
    gear.setJerk(1000);
    gear.setBufferMode(mcAborting);
    FbMoveRelative replacement, direct;
    FbMoveSuperimposed superimposed;
    FbStop stop;
    for (auto* block : std::initializer_list<FbAxisMotion*>{
             &replacement, &direct, &superimposed, &stop })
    {
      block->setAxis(&slave);
      block->setPosition(1);
      block->setVelocity(1);
      block->setAcceleration(10);
      block->setDeceleration(10);
      block->setJerk(100);
      block->setBufferMode(mcAborting);
    }
    bool rejected = false, stopped = false;
    double previous_v = 0, previous_a = 0;
    double peak_jerk = 0, peak_acceleration = 0, peak_velocity_step = 0;
    for (int cycle = 0; cycle < 6 * GetParam(); ++cycle)
    {
      runObservedCycle(master, "master");
      runObservedCycle(slave, "slave");
      runObservedCycle(master_power, "master_power");
      runObservedCycle(slave_power, "slave_power");
      master_move.setExecute(cycle >= 5 ? mcTRUE : mcFALSE);
      runObservedCycle(master_move, "master_move");
      gear.setExecute(cycle >= 6 && cycle < 6 + 0.1 * GetParam() ? mcTRUE :
                                                                   mcFALSE);
      runObservedCycle(gear, "gear");
      if (!rejected && slave.isStoppingOnError())
      {
        ASSERT_GT(fabs(slave.toUserVelCmd()), 0.001);
        previous_v = slave.toUserVelCmd();
        previous_a = slave.toUserAccCmd();
        for (const auto mode : { mcAborting, mcBuffered })
        {
          replacement.setBufferMode(mode);
          replacement.setExecute(mcTRUE);
          runObservedCycle(replacement, "replacement");
          EXPECT_EQ(replacement.isError(), mcTRUE);
          EXPECT_EQ(replacement.getErrorID(), mcErrorCodeAxisStateViolation);
          EXPECT_EQ(replacement.isBusy(), mcFALSE);
          replacement.setExecute(mcFALSE);
          runObservedCycle(replacement, "replacement");
        }
        stop.setExecute(mcTRUE);
        runObservedCycle(stop, "stop");
        superimposed.setExecute(mcTRUE);
        runObservedCycle(superimposed, "superimposed");
        EXPECT_EQ(stop.getErrorID(), mcErrorCodeAxisStateViolation);
        EXPECT_EQ(superimposed.getErrorID(), mcErrorCodeAxisStateViolation);
        slave.addFBToQueue(&direct, mcMoveRelativeMode);
        EXPECT_EQ(direct.getErrorID(), mcErrorCodeAxisStateViolation);
        slave.addMoveSupFB(&direct, 1, 1);
        EXPECT_EQ(direct.getErrorID(), mcErrorCodeAxisStateViolation);
        rejected = true;
      }
      if (rejected)
      {
        const double velocity     = slave.toUserVelCmd();
        const double acceleration = slave.toUserAccCmd();
        peak_acceleration = std::max(peak_acceleration, fabs(acceleration));
        peak_jerk =
            std::max(peak_jerk, fabs(acceleration - previous_a) * GetParam());
        peak_velocity_step = std::max(peak_velocity_step,
                                      fabs(velocity - previous_v) * GetParam());
        previous_v         = velocity;
        previous_a         = acceleration;
        if (slave.getAxisState() == mcStandstill && !slave.isStoppingOnError())
        {
          EXPECT_NEAR(velocity, 0, 1e-12);
          EXPECT_NEAR(acceleration, 0, 1e-12);
          stopped = true;
          break;
        }
      }
      ASSERT_EQ(slave.getAxisError(), mcErrorCodeGood);
    }
    ASSERT_TRUE(rejected);
    ASSERT_TRUE(stopped);
    EXPECT_LE(peak_acceleration, 20 + 1e-6);
    EXPECT_LE(peak_velocity_step, 20 + 1e-6);
    EXPECT_LE(peak_jerk, 1000 + 1e-6);
    replacement.setBufferMode(mcAborting);
    replacement.setExecute(mcTRUE);
    for (int cycle = 0; cycle < 2 * GetParam(); ++cycle)
    {
      runObservedCycle(slave, "slave");
      runObservedCycle(replacement, "replacement");
      ASSERT_EQ(replacement.isError(), mcFALSE);
    }
    EXPECT_EQ(replacement.isDone(), mcTRUE);
  }
}

class GearInPosReversalTest : public GearInRegressionTest,
                              public ::testing::WithParamInterface<double>
{
};

TEST_P(GearInPosReversalTest, NoPositionDriftBelowVelocitySyncThreshold)
{
#ifdef PLOT
  record_gear_status_ = false;
  plot_description_ = "Pulsed Execute, defect 3, 1:1 reversal, VelSyncFactor=" +
                      std::to_string(GetParam());
#endif
  master_move_.setVelocity(1);
  master_move_.setAcceleration(2);
  master_move_.setDeceleration(2);
  master_move_.setJerk(20);
  FbMoveVelocity reverse;
  reverse.setAxis(&master_);
  reverse.setVelocity(-1);
  reverse.setAcceleration(2);
  reverse.setDeceleration(2);
  reverse.setJerk(20);
  reverse.setBufferMode(mcAborting);
  FbGearInPos position_gear;
  position_gear.setMaster(&master_);
  position_gear.setSlave(&slave_);
  position_gear.setRatioNumerator(1);
  position_gear.setRatioDenominator(1);
  position_gear.setMasterStartDistance(1);
  position_gear.setMasterSyncPosition(3);
  position_gear.setSlaveSyncPosition(3);
  position_gear.setVelocity(50);
  position_gear.setAcceleration(500);
  position_gear.setDeceleration(500);
  position_gear.setPosSyncFactor(0.01);
  position_gear.setVelSyncFactor(GetParam());
  position_gear.setBufferMode(mcAborting);
  double peak_position_error = 0, peak_velocity_error = 0;
  for (int cycle = 0; cycle < 8500; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    runObservedCycle(reverse, "reverse");
    runPositionGearCycle(position_gear, cycle);
    ASSERT_EQ(position_gear.getErrorID(), mcErrorCodeGood);
    ASSERT_EQ(reverse.isError(), mcFALSE);
    if (cycle == 5)
      master_move_.setExecute(mcTRUE);
    if (cycle == 4000)
    {
      ASSERT_EQ(position_gear.getInSync(), mcTRUE);
      reverse.setExecute(mcTRUE);
    }
    if (cycle >= 4000)
    {
      ASSERT_EQ(position_gear.getInSync(), mcTRUE);
      ASSERT_EQ(position_gear.getStartSync(), mcFALSE);
      ASSERT_EQ(slave_.getAxisState(), mcSynchronizedMotion);
      EXPECT_NEAR(slave_.toUserPosCmd(), master_.toUserPosCmd(), 1e-9);
      EXPECT_NEAR(slave_.toUserVelCmd(), master_.toUserVelCmd(), 1e-9);
      peak_position_error = std::max(
          peak_position_error, fabs(slave_.toUserPos() - master_.toUserPos()));
      peak_velocity_error = std::max(
          peak_velocity_error, fabs(slave_.toUserVel() - master_.toUserVel()));
      if (cycle == 4500 || cycle == 7500 || cycle == 8499)
        printf("GearInPos reversal: VelSyncFactor=%.3f, t=%.3f, "
               "position error=%.9g, velocity error=%.9g\n",
               GetParam(), cycle / 1000.0,
               slave_.toUserPos() - master_.toUserPos(),
               slave_.toUserVel() - master_.toUserVel());
    }
#ifdef PLOT
    gear_plot_.addPositionGear(position_gear, master_, slave_, plot_time_,
                               master_.toUserPosCmd(), 1);
#endif
  }
  EXPECT_LE(peak_position_error, 2e-6);
  EXPECT_EQ(position_gear.isEnabled(), mcFALSE);
  EXPECT_LE(peak_velocity_error, 0.002001);
  EXPECT_NEAR(master_.toUserVel(), -1, 0.001);
  EXPECT_NEAR(slave_.toUserVel(), -1, 0.001);
}

INSTANTIATE_TEST_SUITE_P(VelocityThresholds, GearInPosReversalTest,
                         ::testing::Values(0.05, 0.001));

struct GearRatioCase
{
  mcINT numerator;
  mcUINT denominator;
  double expected_velocity;
};

class GearInFractionalRatioTest
  : public GearInRegressionTest,
    public ::testing::WithParamInterface<GearRatioCase>
{
};

TEST_P(GearInFractionalRatioTest, MaintainsRequestedVelocityRatio)
{
  const auto ratio = GetParam();
#ifdef PLOT
  plot_description_ = "Ratio " + std::to_string(ratio.numerator) + ":" +
                      std::to_string(ratio.denominator);
#endif
  SCOPED_TRACE(::testing::Message()
               << "Ratio " << ratio.numerator << ":" << ratio.denominator);
  gear_.setRatioNumerator(ratio.numerator);
  gear_.setRatioDenominator(ratio.denominator);
  int stable_cycles = 0;
  bool started      = false;
  for (int cycle = 0; cycle < 6000; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    if (!started && master_power_.getPowerStatus() == mcTRUE &&
        slave_power_.getPowerStatus() == mcTRUE)
    {
      master_move_.setExecute(mcTRUE);
      gear_.setExecute(mcTRUE);
      started = true;
    }
    if (master_move_.isInVelocity() == mcTRUE && gear_.getInGear() == mcTRUE &&
        fabs(master_.toUserVel() - 500) < 0.01 &&
        fabs(slave_.toUserVelCmd() - ratio.expected_velocity) < 0.01 &&
        fabs(slave_.toUserVel() - ratio.expected_velocity) < 0.01)
      ++stable_cycles;
    else
      stable_cycles = 0;
    if (stable_cycles >= 100)
      break;
  }
  ASSERT_TRUE(started);
  EXPECT_EQ(master_move_.isInVelocity(), mcTRUE);
  EXPECT_NEAR(master_.toUserVel(), 500, 0.01);
  EXPECT_NEAR(slave_.toUserVelCmd(), ratio.expected_velocity, 0.01);
  EXPECT_NEAR(slave_.toUserVel(), ratio.expected_velocity, 0.01);
  EXPECT_EQ(gear_.getInGear(), mcTRUE);
  EXPECT_EQ(slave_.getAxisState(), mcSynchronizedMotion);
  EXPECT_GE(stable_cycles, 100) << "Requested ratio never stabilized.";
}

INSTANTIATE_TEST_SUITE_P(FractionalRatios, GearInFractionalRatioTest,
                         ::testing::Values(GearRatioCase{ 1, 2, 250 },
                                           GearRatioCase{ 1, 3, 500.0 / 3 },
                                           GearRatioCase{ 3, 2, 750 },
                                           GearRatioCase{ -1, 2, -250 }));

TEST_F(GearInRegressionTest, RejectsUnsetRatioDenominator)
{
  gear_.setRatioNumerator(1);
  const auto result = gear_.onRisingEdgeExecution();
  EXPECT_EQ(result, mcErrorCodeGearRatioDenominatorSetZero);
#ifdef PLOT
  plot_description_ = "Rejected before motion: unset denominator (snapshot)";
  gear_plot_.add("Error code", "Actual", 0, result);
  gear_plot_.add("Error code", "Expected", 0,
                 mcErrorCodeGearRatioDenominatorSetZero);
#endif
}

TEST_F(GearInRegressionTest, FollowsAfterExecuteFallsAndReleasesOnGearOut)
{
  gear_.setRatioNumerator(1);
  gear_.setRatioDenominator(1);
  for (int cycle = 0; cycle < 100; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    if (master_power_.getPowerStatus() == mcTRUE &&
        slave_power_.getPowerStatus() == mcTRUE)
      gear_.setExecute(mcTRUE);
  }
  ASSERT_EQ(gear_.getInGear(), mcTRUE);
  gear_.setExecute(mcFALSE);
  master_move_.setExecute(mcTRUE);
  for (int cycle = 0; cycle < 1500; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    EXPECT_NEAR(slave_.toUserVelCmd(), master_.toUserVel(), 0.01);
  }
  ASSERT_NEAR(slave_.toUserVel(), 500, 0.01);
  ASSERT_EQ(gear_.getInGear(), mcTRUE);

  FbMoveVelocity reverse;
  reverse.setAxis(&master_);
  reverse.setVelocity(-100);
  reverse.setAcceleration(1000);
  reverse.setDeceleration(1000);
  reverse.setJerk(10000);
  reverse.setExecute(mcTRUE);
  for (int cycle = 0; cycle < 1500; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    runObservedCycle(reverse, "reverse");
    ASSERT_EQ(reverse.isError(), mcFALSE);
    EXPECT_NEAR(slave_.toUserVelCmd(), master_.toUserVel(), 0.01);
  }
  ASSERT_NEAR(slave_.toUserVel(), -100, 0.01);
  ASSERT_EQ(gear_.getInGear(), mcTRUE);

  FbGearOut gear_out;
  gear_out.setSlave(&slave_);
  gear_out.setExecute(mcTRUE);
  for (int cycle = 0; cycle < 100; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    runObservedCycle(reverse, "reverse");
    runObservedCycle(gear_out, "gear_out");
#ifdef PLOT
    gear_plot_.addBlock("GearOut", gear_out, plot_time_);
#endif
    ASSERT_EQ(gear_out.isError(), mcFALSE);
  }
  ASSERT_EQ(gear_out.isDone(), mcTRUE);
  EXPECT_EQ(gear_.getInGear(), mcFALSE);
  EXPECT_EQ(gear_.isActive(), mcFALSE);
  EXPECT_EQ(slave_.getAxisState(), mcContinuousMotion);

  master_move_.setExecute(mcFALSE);
  ASSERT_NO_FATAL_FAILURE(runCycle());
  master_move_.setExecute(mcTRUE);
  for (int cycle = 0; cycle < 1500; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    runObservedCycle(reverse, "reverse");
    runObservedCycle(gear_out, "gear_out");
#ifdef PLOT
    gear_plot_.addBlock("GearOut", gear_out, plot_time_);
#endif
    EXPECT_NEAR(slave_.toUserVel(), -100, 0.01);
  }
  EXPECT_NEAR(master_.toUserVel(), 500, 0.01);
}

TEST_F(GearInRegressionTest, ConsecutiveGearInAndHaltTakeOwnership)
{
  gear_.setRatioNumerator(1);
  gear_.setRatioDenominator(1);
  for (int cycle = 0; cycle < 1500; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    if (master_power_.getPowerStatus() == mcTRUE &&
        slave_power_.getPowerStatus() == mcTRUE)
    {
      master_move_.setExecute(mcTRUE);
      gear_.setExecute(mcTRUE);
    }
  }
  ASSERT_EQ(gear_.getInGear(), mcTRUE);
  ASSERT_NEAR(slave_.toUserVel(), 500, 0.01);
  FbGearIn second;
  second.setMaster(&master_);
  second.setSlave(&slave_);
  second.setRatioNumerator(1);
  second.setRatioDenominator(2);
  second.setAcceleration(1000);
  second.setDeceleration(1000);
  second.setJerk(10000);
  second.setInGearThreshold(0.01);
  second.setExecute(mcTRUE);
  for (int cycle = 0; cycle < 1500; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    runObservedCycle(second, "second");
#ifdef PLOT
    gear_plot_.addBlock("SecondGear", second, plot_time_);
    gear_plot_.add("FB signals", "SecondGear.InGear", plot_time_,
                   second.getInGear() == mcTRUE);
#endif
    ASSERT_EQ(second.isError(), mcFALSE);
  }
  EXPECT_EQ(gear_.isAborted(), mcTRUE);
  EXPECT_EQ(gear_.isActive(), mcFALSE);
  EXPECT_EQ(gear_.getInGear(), mcFALSE);
  ASSERT_EQ(second.getInGear(), mcTRUE);
  ASSERT_NEAR(slave_.toUserVel(), 250, 0.01);

  FbHalt halt;
  halt.setAxis(&slave_);
  halt.setDeceleration(1000);
  halt.setJerk(10000);
  halt.setBufferMode(mcAborting);
  halt.setExecute(mcTRUE);
  for (int cycle = 0; cycle < 1500; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    runObservedCycle(second, "second");
    runObservedCycle(halt, "halt");
#ifdef PLOT
    gear_plot_.addBlock("SecondGear", second, plot_time_);
    gear_plot_.add("FB signals", "SecondGear.InGear", plot_time_,
                   second.getInGear() == mcTRUE);
    gear_plot_.addBlock("Halt", halt, plot_time_);
#endif
    ASSERT_EQ(halt.isError(), mcFALSE);
  }
  EXPECT_EQ(second.isAborted(), mcTRUE);
  EXPECT_EQ(second.getInGear(), mcFALSE);
  EXPECT_EQ(halt.isDone(), mcTRUE);
  EXPECT_NEAR(slave_.toUserVel(), 0, 0.01);
  EXPECT_NEAR(master_.toUserVel(), 500, 0.01);
}

TEST_F(GearInRegressionTest, TracksMasterStartingFromStandstill)
{
  gear_.setRatioNumerator(1);
  gear_.setRatioDenominator(1);
  int stable_cycles         = 0;
  int tracking_cycles       = 0;
  int out_of_gear_cycles    = 0;
  bool started              = false;
  double peak_command_error = 0;
  double peak_actual_error  = 0;
  // Five cycles of master acceleration plus feedback quantization.
  const double tracking_tolerance =
      5 * master_move_.getAcceleration() / master_config_.frequency_ + 0.01;
  for (int cycle = 0; cycle < 6000; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    if (master_power_.getPowerStatus() == mcTRUE &&
        slave_power_.getPowerStatus() == mcTRUE)
      gear_.setExecute(mcTRUE);
    const double command_error =
        fabs(slave_.toUserVelCmd() - master_.toUserVel());
    const double actual_error = fabs(slave_.toUserVel() - master_.toUserVel());
    if (!started)
    {
      if (gear_.getInGear() == mcTRUE && fabs(master_.toUserVel()) < 0.01 &&
          fabs(slave_.toUserVel()) < 0.01 && command_error < 0.01)
        ++stable_cycles;
      else
        stable_cycles = 0;
      if (stable_cycles >= 100)
      {
        started = true;
        master_move_.setExecute(mcTRUE);
      }
    }
    else
    {
      ASSERT_EQ(gear_.isEnabled(), mcTRUE);
      ASSERT_EQ(slave_.getAxisState(), mcSynchronizedMotion);
      ++tracking_cycles;
      if (gear_.getInGear() == mcFALSE)
        ++out_of_gear_cycles;
      if (command_error > peak_command_error)
        peak_command_error = command_error;
      if (actual_error > peak_actual_error)
        peak_actual_error = actual_error;
    }
    if (tracking_cycles >= 4000)
      break;
  }
  printf("GearIn stationary start: peak command error=%.6f, "
         "peak actual error=%.6f, InGear false=%d/%d cycles, tolerance=%.6f\n",
         peak_command_error, peak_actual_error, out_of_gear_cycles,
         tracking_cycles, tracking_tolerance);
  ASSERT_TRUE(started) << "Stationary gearing never stabilized.";
  ASSERT_EQ(tracking_cycles, 4000);
  EXPECT_EQ(master_move_.isInVelocity(), mcTRUE);
  EXPECT_NEAR(master_.toUserVel(), 500, 0.01);
  EXPECT_NEAR(slave_.toUserVelCmd(), 500, 0.01);
  EXPECT_NEAR(slave_.toUserVel(), 500, 0.01);
  EXPECT_EQ(gear_.getInGear(), mcTRUE);
  EXPECT_LE(peak_command_error, tracking_tolerance);
  EXPECT_LE(peak_actual_error, tracking_tolerance);
}

TEST_F(GearInRegressionTest, EngagesDuringSustainedMasterAcceleration)
{
  master_config_.encoder_count_per_unit_ = 10000000;
  slave_config_.encoder_count_per_unit_  = 10000000;
  master_move_.setVelocity(1000);
  master_move_.setAcceleration(10);
  master_move_.setDeceleration(10);
  master_move_.setJerk(1000);
  gear_.setRatioNumerator(1);
  gear_.setRatioDenominator(1);
  gear_.setAcceleration(100);
  gear_.setDeceleration(100);
  gear_.setJerk(1000);
  gear_.setInGearThreshold(0.5);
  double previous_velocity = 0, previous_acceleration = 0;
  double peak_acceleration = 0, peak_velocity_step = 0, peak_jerk = 0;
  int engagement_cycles = 0;
  for (int cycle = 0; cycle < 4000 && engagement_cycles < 2500; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    if (master_power_.getPowerStatus() == mcTRUE &&
        slave_power_.getPowerStatus() == mcTRUE)
      master_move_.setExecute(mcTRUE);
    if (master_.toUserVel() >= 1)
      gear_.setExecute(mcTRUE);
    const double velocity     = slave_.toUserVelCmd();
    const double acceleration = slave_.toUserAccCmd();
    peak_acceleration         = std::max(peak_acceleration, fabs(acceleration));
    peak_velocity_step =
        std::max(peak_velocity_step, fabs(velocity - previous_velocity));
    peak_jerk =
        std::max(peak_jerk, fabs(acceleration - previous_acceleration) * 1000);
    previous_velocity     = velocity;
    previous_acceleration = acceleration;
    if (gear_.isEnabled() == mcTRUE)
    {
      ++engagement_cycles;
      if (engagement_cycles > 2300)
        EXPECT_NEAR(velocity, master_.toUserVel(), 0.00001);
    }
  }
  ASSERT_EQ(engagement_cycles, 2500);
  EXPECT_LE(peak_acceleration, 100.00001);
  EXPECT_LE(peak_velocity_step * 1000, 100.00001);
  EXPECT_LE(peak_jerk, 1000.00001);
  EXPECT_EQ(gear_.getInGear(), mcTRUE);
  ASSERT_EQ(master_move_.isInVelocity(), mcFALSE);
  ASSERT_NEAR(master_.toUserAccCmd(), 10, 1e-9);

  FbMoveVelocity next;
  next.setAxis(&slave_);
  next.setVelocity(slave_.toUserVelCmd());
  next.setAcceleration(100);
  next.setDeceleration(100);
  next.setJerk(1000);
  next.setBufferMode(mcBuffered);
  next.setExecute(mcTRUE);
  for (int cycle = 0; cycle < 100; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    runObservedCycle(next, "next");
#ifdef PLOT
    gear_plot_.addBlock("Next", next, plot_time_);
#endif
    ASSERT_EQ(next.isError(), mcFALSE);
    if (gear_.isAborted() == mcTRUE)
      break;
  }
  EXPECT_EQ(gear_.isAborted(), mcTRUE);
  EXPECT_TRUE(next.isActive() == mcTRUE || next.isInVelocity() == mcTRUE);
  EXPECT_EQ(master_move_.isInVelocity(), mcFALSE);
  EXPECT_NEAR(master_.toUserAccCmd(), 10, 1e-9);
}

TEST_F(GearInRegressionTest, EngagesWithAlternatingMasterVelocity)
{
  for (const double direction : { 1.0, -1.0 })
  {
    SCOPED_TRACE(::testing::Message() << "direction=" << direction);
    FbMoveVelocity target;
    target.setAxis(&slave_);
    target.setVelocity(direction * 0.001);
    ExecutionNode node;
    node.setBasicParams(&target, mcGearInMode, NAN, direction * 0.001, 0.1, 0.1,
                        10, mcAborting, mcOffLine);
    node.setStartPos(0);
    node.setStartVel(0);
    node.setStartAcc(0);
    node.setTerminateCondition(0);
    node.setReplan();
    MC_AXIS_STATES state = mcStandstill;
    node.onActive(&state);
    double position = 0, velocity = 0, acceleration = 0;
    double peak_acceleration = 0, peak_velocity_step = 0, peak_jerk = 0;
    int synchronized_cycles = 0;
#ifdef PLOT
    GearInTestPlot plot;
#endif
    for (int cycle = 0; cycle < 500; ++cycle)
    {
      const double target_velocity =
          direction * (0.001 + (cycle % 2 == 0 ? 0.000001 : -0.000001));
      target.setVelocity(target_velocity);
      const double previous_velocity     = velocity;
      const double previous_acceleration = acceleration;
      node.onExecution(0, 0);
      ASSERT_EQ(node.isError(), mcFALSE);
      node.getCommands(&position, &velocity, &acceleration);
#ifdef PLOT
      FunctionBlockObservations::commands(position, velocity, acceleration);
#endif
      peak_acceleration = std::max(peak_acceleration, fabs(acceleration));
      peak_velocity_step =
          std::max(peak_velocity_step, fabs(velocity - previous_velocity));
      peak_jerk = std::max(peak_jerk,
                           fabs(acceleration - previous_acceleration) * 1000);
#ifdef PLOT
      const double time = (cycle + 1) * 0.001;
      plot.add("Velocity", "Commanded", time, velocity);
      plot.add("Velocity", "Target", time, target_velocity);
      plot.add("Acceleration", "Commanded", time, acceleration);
      plot.add("Jerk", "Commanded (finite difference)", time,
               (acceleration - previous_acceleration) * 1000);
      plot.add("Synchronization", "Command synchronized", time,
               node.isGearSynchronized() == mcTRUE);
#endif
      if (node.isGearSynchronized() == mcTRUE)
      {
        ++synchronized_cycles;
        EXPECT_DOUBLE_EQ(velocity, target_velocity);
      }
    }
    EXPECT_GE(synchronized_cycles, 100);
    EXPECT_LE(peak_acceleration, 0.1000001);
    EXPECT_LE(peak_velocity_step * 1000, 0.1000001);
    EXPECT_LE(peak_jerk, 10.000001);
#ifdef PLOT
    plot.plot(direction > 0 ? "_positive" : "_negative",
              "Alternating master velocity feedback");
#endif
  }
}

TEST_F(GearInRegressionTest, PreservesEngagementRamp)
{
  for (int cycle = 0; cycle < 1000; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    if (master_power_.getPowerStatus() == mcTRUE)
      master_move_.setExecute(mcTRUE);
  }
  ASSERT_NEAR(master_.toUserVel(), 500, 0.01);
  ASSERT_NEAR(slave_.toUserVel(), 0, 0.01);
  gear_.setRatioNumerator(1);
  gear_.setRatioDenominator(1);
  gear_.setJerk(10000);
  gear_.setExecute(mcTRUE);
  double previous_acceleration = 0;
  bool ramp_seen               = false;
  for (int cycle = 0; cycle < 1500; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    const double acceleration = slave_.toUserAccCmd();
    EXPECT_LE(fabs(acceleration), 1000.01);
    EXPECT_LE(fabs(acceleration - previous_acceleration) * 1000, 10000.01);
    previous_acceleration = acceleration;
    if (slave_.toUserVelCmd() > 0.01 && slave_.toUserVelCmd() < 499.99)
      ramp_seen = true;
  }
  EXPECT_TRUE(ramp_seen);
  EXPECT_EQ(gear_.getInGear(), mcTRUE);
  EXPECT_NEAR(slave_.toUserVel(), 500, 0.01);
}

void GearInRegressionTest::checkAxisLimitError(bool master_error,
                                               ExecuteAtError execute_at_error)
{
  auto& fault_config         = master_error ? master_config_ : slave_config_;
  auto& fault_axis           = master_error ? master_ : slave_;
  fault_config.sw_vel_limit_ = mcTRUE;
  fault_config.vel_limit_    = 100;
  gear_.setRatioNumerator(1);
  gear_.setRatioDenominator(1);
  for (int cycle = 0; cycle < 100; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    if (master_power_.getPowerStatus() == mcTRUE &&
        slave_power_.getPowerStatus() == mcTRUE)
      gear_.setExecute(mcTRUE);
  }
  ASSERT_EQ(gear_.getInGear(), mcTRUE);
  if (execute_at_error == ExecuteAtError::Low)
  {
    gear_.setExecute(mcFALSE);
    for (int cycle = 0; cycle < 20; ++cycle)
      ASSERT_NO_FATAL_FAILURE(runCycle());
    ASSERT_EQ(gear_.getInGear(), mcTRUE);
  }
  master_move_.setExecute(mcTRUE);
  int error_cycles            = 0;
  bool outputs_stayed_cleared = true;
  for (int cycle = 0; cycle < 1000; ++cycle)
  {
    runObservedCycle(master_, "master_");
    runObservedCycle(slave_, "slave_");
    runObservedCycle(master_power_, "master_power_");
    runObservedCycle(slave_power_, "slave_power_");
    runObservedCycle(master_move_, "master_move_");
    if (fault_axis.getAxisError() != mcErrorCodeGood &&
        execute_at_error == ExecuteAtError::Falling)
      gear_.setExecute(mcFALSE);
    runObservedCycle(gear_, "gear_");
#ifdef PLOT
    recordPlot();
    gear_plot_.add("Axis state / error code", "Faulted axis error", plot_time_,
                   fault_axis.getAxisError());
    gear_plot_.add("Velocity", "Software velocity limit", plot_time_,
                   fault_config.vel_limit_);
#endif
    if (fault_axis.getAxisError() != mcErrorCodeGood)
    {
      if (error_cycles == 0)
      {
        EXPECT_EQ(gear_.getInGear(), mcFALSE);
        EXPECT_EQ(gear_.isActive(), mcFALSE);
        EXPECT_EQ(gear_.isBusy(), mcFALSE);
      }
      outputs_stayed_cleared =
          outputs_stayed_cleared && gear_.getInGear() == mcFALSE &&
          gear_.isActive() == mcFALSE && gear_.isBusy() == mcFALSE &&
          gear_.isReadyForBufferedHandoff() == mcFALSE &&
          gear_.isError() != mcFALSE &&
          gear_.getErrorID() == mcErrorCodeVelocityOverLimit;
      if (++error_cycles == 100)
        break;
    }
  }
  EXPECT_EQ(error_cycles, 100);
  EXPECT_TRUE(outputs_stayed_cleared);
  EXPECT_EQ(fault_axis.getAxisError(), mcErrorCodeVelocityOverLimit);
  EXPECT_EQ(fault_axis.getAxisState(), mcErrorStop);
  EXPECT_EQ(gear_.getInGear(), mcFALSE);
  EXPECT_EQ(gear_.isActive(), mcFALSE);
  EXPECT_EQ(gear_.isBusy(), mcFALSE);
  EXPECT_NE(gear_.isError(), mcFALSE);
  EXPECT_EQ(gear_.getErrorID(), mcErrorCodeVelocityOverLimit);
}

TEST_F(GearInRegressionTest, CoupledVelocityStillHonorsAxisLimit)
{
  ASSERT_NO_FATAL_FAILURE(checkAxisLimitError(false, ExecuteAtError::High));
}

TEST_F(GearInRegressionTest, MasterAxisErrorClearsGearStatus)
{
  ASSERT_NO_FATAL_FAILURE(checkAxisLimitError(true, ExecuteAtError::High));
}

TEST_F(GearInRegressionTest, SlaveAxisErrorAfterExecuteFallsClearsGearStatus)
{
  ASSERT_NO_FATAL_FAILURE(checkAxisLimitError(false, ExecuteAtError::Low));
}

TEST_F(GearInRegressionTest, MasterAxisErrorAfterExecuteFallsClearsGearStatus)
{
  ASSERT_NO_FATAL_FAILURE(checkAxisLimitError(true, ExecuteAtError::Low));
}

TEST_F(GearInRegressionTest, SlaveAxisErrorOnExecuteFallingEdgeClearsGearStatus)
{
  ASSERT_NO_FATAL_FAILURE(checkAxisLimitError(false, ExecuteAtError::Falling));
}

TEST_F(GearInRegressionTest,
       MasterAxisErrorOnExecuteFallingEdgeClearsGearStatus)
{
  ASSERT_NO_FATAL_FAILURE(checkAxisLimitError(true, ExecuteAtError::Falling));
}

class GearInBufferedHandoffTest
  : public GearInRegressionTest,
    public ::testing::WithParamInterface<MC_BUFFER_MODE>
{
protected:
#ifdef PLOT
  void SetUp() override
  {
    GearInRegressionTest::SetUp();
    const std::map<MC_BUFFER_MODE, std::string> names{
      { mcBuffered, "mcBuffered" },
      { mcBlendingLow, "mcBlendingLow" },
      { mcBlendingPrevious, "mcBlendingPrevious" },
      { mcBlendingNext, "mcBlendingNext" },
      { mcBlendingHigh,
        "mcBlendingHigh" }
    };
    plot_description_ = names.at(GetParam());
  }
#endif

  void startMaster()
  {
    master_move_.setVelocity(100);
    for (int cycle = 0; cycle < 1000; ++cycle)
    {
      ASSERT_NO_FATAL_FAILURE(runCycle());
      if (master_power_.getPowerStatus() == mcTRUE &&
          slave_power_.getPowerStatus() == mcTRUE)
        master_move_.setExecute(mcTRUE);
    }
    ASSERT_NEAR(master_.toUserVel(), 100, 0.01);
    gear_.setRatioNumerator(1);
    gear_.setRatioDenominator(1);
    gear_.setJerk(10000);
    gear_.setExecute(mcTRUE);
  }

  void checkRelativeHandoff(bool queue_during_ramp)
  {
    ASSERT_NO_FATAL_FAILURE(startMaster());
    ASSERT_NO_FATAL_FAILURE(runCycle());
    if (!queue_during_ramp)
    {
      for (int cycle = 0; cycle < 1000; ++cycle)
        ASSERT_NO_FATAL_FAILURE(runCycle());
      ASSERT_EQ(gear_.getInGear(), mcTRUE);
    }
    else
      ASSERT_EQ(gear_.getInGear(), mcFALSE);

    FbMoveRelative next;
    next.setAxis(&slave_);
    next.setPosition(20);
    next.setVelocity(100);
    next.setAcceleration(1000);
    next.setDeceleration(1000);
    next.setJerk(10000);
    next.setBufferMode(GetParam());
    next.setExecute(mcTRUE);
    runObservedCycle(next, "next");
    ASSERT_EQ(next.isError(), mcFALSE);
    ASSERT_EQ(next.isActive(), mcFALSE);

    bool handed_off         = false;
    double handoff_position = 0;
    for (int cycle = 0; cycle < 2000; ++cycle)
    {
      const double previous_position = slave_.toUserPos();
      const double previous_velocity = slave_.toUserVel();
      ASSERT_NO_FATAL_FAILURE(runCycle());
      runObservedCycle(next, "next");
#ifdef PLOT
      gear_plot_.addBlock("Next", next, plot_time_);
#endif
      ASSERT_EQ(next.isError(), mcFALSE);
      if (!handed_off && gear_.isAborted() == mcTRUE)
      {
        handed_off       = true;
        handoff_position = previous_position;
        EXPECT_NEAR(previous_velocity, 100, 0.01);
        EXPECT_EQ(gear_.getInGear(), mcFALSE);
        EXPECT_EQ(gear_.isActive(), mcFALSE);
      }
      if (!handed_off)
      {
        EXPECT_EQ(next.isActive(), mcFALSE);
        EXPECT_LE(fabs(slave_.toUserAccCmd()), 1000.01);
      }
      if (next.isDone() == mcTRUE)
        break;
    }
    ASSERT_TRUE(handed_off);
    EXPECT_EQ(next.isDone(), mcTRUE);
    EXPECT_NEAR(slave_.toUserPos(), handoff_position + 20, 0.01);
    EXPECT_NEAR(slave_.toUserVel(), 0, 0.01);
    EXPECT_NEAR(master_.toUserVel(), 100, 0.01);
  }
};

TEST_P(GearInBufferedHandoffTest, RelativeMoveQueuedDuringEngagement)
{
  ASSERT_NO_FATAL_FAILURE(checkRelativeHandoff(true));
}

TEST_P(GearInBufferedHandoffTest, RelativeMoveQueuedAfterSynchronization)
{
  ASSERT_NO_FATAL_FAILURE(checkRelativeHandoff(false));
}

TEST_P(GearInBufferedHandoffTest, VelocityMoveQueuedAfterSynchronization)
{
  ASSERT_NO_FATAL_FAILURE(startMaster());
  for (int cycle = 0; cycle < 1000; ++cycle)
    ASSERT_NO_FATAL_FAILURE(runCycle());
  ASSERT_EQ(gear_.getInGear(), mcTRUE);
  FbMoveVelocity next;
  next.setAxis(&slave_);
  next.setVelocity(50);
  next.setAcceleration(1000);
  next.setDeceleration(1000);
  next.setJerk(10000);
  next.setBufferMode(GetParam());
  next.setExecute(mcTRUE);
  for (int cycle = 0; cycle < 1500; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    runObservedCycle(next, "next");
#ifdef PLOT
    gear_plot_.addBlock("Next", next, plot_time_);
#endif
    ASSERT_EQ(next.isError(), mcFALSE);
  }
  EXPECT_EQ(next.isInVelocity(), mcTRUE);
  EXPECT_NEAR(slave_.toUserVel(), 50, 0.01);
  EXPECT_EQ(gear_.isAborted(), mcTRUE);
  EXPECT_EQ(gear_.getInGear(), mcFALSE);
}

INSTANTIATE_TEST_SUITE_P(BufferModes, GearInBufferedHandoffTest,
                         ::testing::Values(mcBuffered, mcBlendingLow,
                                           mcBlendingPrevious, mcBlendingNext,
                                           mcBlendingHigh));

TEST_F(GearInRegressionTest, PreservesConfiguredQueueCapacity)
{
  slave_.setNodeQueueSize(5);
  gear_.setRatioNumerator(1);
  gear_.setRatioDenominator(1);
  for (int cycle = 0; cycle < 100; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    if (master_power_.getPowerStatus() == mcTRUE &&
        slave_power_.getPowerStatus() == mcTRUE)
      gear_.setExecute(mcTRUE);
  }
  ASSERT_EQ(gear_.getInGear(), mcTRUE);
  FbMoveVelocity moves[3];
  for (int i = 0; i < 3; ++i)
  {
    moves[i].setAxis(&slave_);
    moves[i].setVelocity((i + 1) * 100);
    moves[i].setAcceleration(1000);
    moves[i].setDeceleration(1000);
    moves[i].setJerk(10000);
    moves[i].setBufferMode(mcBuffered);
    moves[i].setExecute(mcTRUE);
    runObservedCycle(moves[i], "moves");
    ASSERT_EQ(slave_.getAxisError(), mcErrorCodeGood);
  }
  for (int cycle = 0; cycle < 3000; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    for (auto& move : moves)
    {
      runObservedCycle(move, "move");
#ifdef PLOT
      gear_plot_.addBlock("Move" + std::to_string(&move - moves + 1), move,
                          plot_time_);
#endif
      ASSERT_EQ(move.isError(), mcFALSE);
    }
  }
  EXPECT_EQ(moves[2].isInVelocity(), mcTRUE);
  EXPECT_NEAR(slave_.toUserVel(), 300, 0.01);
}

TEST_F(GearInRegressionTest, GearOutAbortsFullBufferedQueue)
{
  slave_.setNodeQueueSize(2);
  gear_.setRatioNumerator(1);
  gear_.setRatioDenominator(1);
  for (int cycle = 0; cycle < 100; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    if (master_power_.getPowerStatus() == mcTRUE &&
        slave_power_.getPowerStatus() == mcTRUE)
      gear_.setExecute(mcTRUE);
  }
  ASSERT_EQ(gear_.getInGear(), mcTRUE);
  FbMoveVelocity next;
  next.setAxis(&slave_);
  next.setVelocity(100);
  next.setAcceleration(1000);
  next.setDeceleration(1000);
  next.setJerk(10000);
  next.setBufferMode(mcBuffered);
  next.setExecute(mcTRUE);
  runObservedCycle(next, "next");
  FbGearOut gear_out;
  gear_out.setSlave(&slave_);
  gear_out.setExecute(mcTRUE);
  runObservedCycle(gear_out, "gear_out");
  ASSERT_EQ(slave_.getAxisError(), mcErrorCodeGood);
  for (int cycle = 0; cycle < 100; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    runObservedCycle(next, "next");
    runObservedCycle(gear_out, "gear_out");
#ifdef PLOT
    gear_plot_.addBlock("Next", next, plot_time_);
    gear_plot_.addBlock("GearOut", gear_out, plot_time_);
#endif
    ASSERT_EQ(gear_out.isError(), mcFALSE);
  }
  EXPECT_EQ(next.isAborted(), mcTRUE);
  EXPECT_EQ(gear_.isAborted(), mcTRUE);
  EXPECT_EQ(gear_out.isDone(), mcTRUE);
  EXPECT_NEAR(slave_.toUserVel(), 0, 0.01);
}

TEST_P(GearInBufferedHandoffTest, RelativeSequenceUsesActualHandoffPosition)
{
  slave_.setNodeQueueSize(5);
  gear_.setRatioNumerator(1);
  gear_.setRatioDenominator(1);
  master_move_.setVelocity(100);
  for (int cycle = 0; cycle < 1000; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    if (master_power_.getPowerStatus() == mcTRUE)
      master_move_.setExecute(mcTRUE);
  }
  gear_.setExecute(mcTRUE);
  ASSERT_NO_FATAL_FAILURE(runCycle());
  FbMoveRelative moves[2];
  for (int i = 0; i < 2; ++i)
  {
    auto& move = moves[i];
    move.setAxis(&slave_);
    move.setPosition(20);
    move.setVelocity(100);
    move.setAcceleration(1000);
    move.setDeceleration(1000);
    move.setJerk(10000);
    move.setBufferMode(i == 0 ? mcBuffered : GetParam());
    move.setExecute(mcTRUE);
    runObservedCycle(move, "move");
  }
  bool handed_off         = false;
  bool first_completed    = false;
  double handoff_position = 0;
  for (int cycle = 0; cycle < 2000; ++cycle)
  {
    const double previous_position = slave_.toUserPos();
    ASSERT_NO_FATAL_FAILURE(runCycle());
    for (auto& move : moves)
    {
      runObservedCycle(move, "move");
#ifdef PLOT
      gear_plot_.addBlock("Move" + std::to_string(&move - moves + 1), move,
                          plot_time_);
#endif
      ASSERT_EQ(move.isError(), mcFALSE);
    }
    if (!handed_off && gear_.isAborted() == mcTRUE)
    {
      handed_off       = true;
      handoff_position = previous_position;
    }
    if (!first_completed && moves[0].isDone() == mcTRUE)
    {
      first_completed = true;
      EXPECT_NEAR(slave_.toUserVel(), GetParam() == mcBuffered ? 0 : 100, 0.1);
    }
    if (moves[1].isDone() == mcTRUE)
      break;
  }
  ASSERT_TRUE(handed_off);
  EXPECT_TRUE(first_completed);
  EXPECT_EQ(moves[1].isDone(), mcTRUE);
  EXPECT_NEAR(slave_.toUserPos(), handoff_position + 40, 0.01);
}

TEST_F(GearInRegressionTest, AbortingAdditiveDestinationDoesNotDependOnCapacity)
{
  for (const mcUSINT capacity : { 1, 2 })
  {
    SCOPED_TRACE(::testing::Message() << "capacity=" << int(capacity));
    AxisConfig config;
    Servo servo;
    Axis axis;
    axis.setNodeQueueSize(capacity);
    axis.setAxisConfig(&config);
    axis.setServo(&servo);
    FbPower power;
    power.setAxis(&axis);
    power.setEnable(mcTRUE);
    power.setEnablePositive(mcTRUE);
    power.setEnableNegative(mcTRUE);
    FbMoveRelative first;
    first.setAxis(&axis);
    first.setPosition(600);
    first.setVelocity(100);
    first.setAcceleration(1000);
    first.setDeceleration(1000);
    first.setJerk(10000);
    first.setBufferMode(mcAborting);
    FbMoveAdditive next;
    next.setAxis(&axis);
    next.setPosition(400);
    next.setVelocity(100);
    next.setAcceleration(1000);
    next.setDeceleration(1000);
    next.setJerk(10000);
    next.setBufferMode(mcAborting);
    bool started = false;
#ifdef PLOT
    GearInTestPlot plot;
#endif
    for (int cycle = 0; cycle < 15000; ++cycle)
    {
      runObservedCycle(axis, "axis");
      runObservedCycle(power, "power");
      runObservedCycle(first, "first");
      runObservedCycle(next, "next");
#ifdef PLOT
      const double time = cycle / static_cast<double>(config.frequency_);
      plot.add("Position", "Actual", time, axis.toUserPos());
      plot.add("Position", "Expected destination", time, 1000);
      plot.add("Velocity", "Commanded", time, axis.toUserVelCmd());
      plot.add("Acceleration", "Commanded", time, axis.toUserAccCmd());
      plot.addBlock("First", first, time);
      plot.addBlock("Additive", next, time);
#endif
      ASSERT_EQ(axis.getAxisError(), mcErrorCodeGood);
      ASSERT_EQ(first.isError(), mcFALSE);
      ASSERT_EQ(next.isError(), mcFALSE);
      if (power.getPowerStatus() == mcTRUE)
        first.setExecute(mcTRUE);
      if (!started && axis.toUserPos() >= 100)
      {
        next.setExecute(mcTRUE);
        started = true;
      }
      if (next.isDone() == mcTRUE)
        break;
    }
    ASSERT_TRUE(started);
    EXPECT_EQ(next.isDone(), mcTRUE);
    EXPECT_NEAR(axis.toUserPos(), 1000, 0.01);
#ifdef PLOT
    plot.plot("_capacity_" + std::to_string(capacity),
              "Queue capacity = " + std::to_string(capacity));
#endif
  }
}

TEST_F(GearInRegressionTest, SmallEngagementLimitsAreNotBypassed)
{
  // A fixed target isolates engagement limits from encoder quantization.
  for (const double start_velocity : { 0.0, 0.00091, 0.00109, 0.002 })
  {
    SCOPED_TRACE(::testing::Message() << "start_velocity=" << start_velocity);
    FbMoveVelocity target;
    target.setAxis(&slave_);
    target.setVelocity(0.001);
    ExecutionNode node;
    node.setBasicParams(&target, mcGearInMode, NAN, 0.001, 0.01, 0.01, 0.1,
                        mcAborting, mcOffLine);
    node.setStartPos(0);
    node.setStartVel(start_velocity);
    node.setStartAcc(0);
    node.setTerminateCondition(0);
    node.setReplan();
    MC_AXIS_STATES state = mcStandstill;
    node.onActive(&state);
    double peak_acceleration     = 0;
    double peak_velocity_step    = 0;
    double peak_jerk             = 0;
    double previous_acceleration = 0;
    double previous_velocity     = start_velocity;
    double position = 0, velocity = 0, acceleration = 0;
#ifdef PLOT
    GearInTestPlot plot;
#endif
    for (int cycle = 0; cycle < 500; ++cycle)
    {
      node.onExecution(0, 0);
      ASSERT_EQ(node.isError(), mcFALSE);
      node.getCommands(&position, &velocity, &acceleration);
#ifdef PLOT
      FunctionBlockObservations::commands(position, velocity, acceleration);
#endif
      peak_acceleration = std::max(peak_acceleration, fabs(acceleration));
      peak_velocity_step =
          std::max(peak_velocity_step, fabs(velocity - previous_velocity));
      peak_jerk = std::max(peak_jerk,
                           fabs(acceleration - previous_acceleration) * 1000);
#ifdef PLOT
      const double time = (cycle + 1) * 0.001;
      plot.add("Velocity", "Commanded", time, velocity);
      plot.add("Velocity", "Target", time, 0.001);
      plot.add("Acceleration", "Commanded", time, acceleration);
      plot.add("Acceleration", "Upper limit", time, 0.01);
      plot.add("Acceleration", "Lower limit", time, -0.01);
      plot.add("Jerk", "Commanded (finite difference)", time,
               (acceleration - previous_acceleration) * 1000);
      plot.add("Jerk", "Upper limit", time, 0.1);
      plot.add("Jerk", "Lower limit", time, -0.1);
#endif
      previous_acceleration = acceleration;
      previous_velocity     = velocity;
    }
    EXPECT_LE(peak_acceleration, 0.0100001);
    EXPECT_LE(peak_velocity_step, 0.0100001 / 1000);
    EXPECT_LE(peak_jerk, 0.100001);
    EXPECT_NEAR(velocity, 0.001, 1e-12);
#ifdef PLOT
    plot.plot("_start_" + std::to_string(start_velocity),
              "Initial velocity = " + std::to_string(start_velocity));
#endif
  }
}

class DelayedVelocityServo : public Servo
{
public:
  mcDINT vel() override
  {
    return release_feedback ? Servo::vel() : 0;
  }
  bool release_feedback = false;
};

TEST_F(GearInRegressionTest, BufferedHandoffWaitsForPublicInGear)
{
  DelayedVelocityServo delayed_servo;
  slave_.setServo(&delayed_servo);
  master_move_.setVelocity(100);
  gear_.setRatioNumerator(1);
  gear_.setRatioDenominator(1);
  FbMoveVelocity next;
  next.setAxis(&slave_);
  next.setVelocity(50);
  next.setAcceleration(1000);
  next.setDeceleration(1000);
  next.setJerk(10000);
  next.setBufferMode(mcBuffered);
  bool queued            = false;
  bool premature_handoff = false;
  bool observed_in_gear  = false;
  for (int cycle = 0; cycle < 2000; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    runObservedCycle(next, "next");
#ifdef PLOT
    gear_plot_.addBlock("Next", next, plot_time_);
    gear_plot_.add("FB signals", "Feedback released", plot_time_,
                   delayed_servo.release_feedback);
#endif
    ASSERT_EQ(next.isError(), mcFALSE);
    if (gear_.getInGear() == mcTRUE)
      observed_in_gear = true;
    if (next.isActive() == mcTRUE)
      EXPECT_TRUE(observed_in_gear);
    if (master_power_.getPowerStatus() == mcTRUE)
      master_move_.setExecute(mcTRUE);
    if (!queued && master_move_.isInVelocity() == mcTRUE)
    {
      gear_.setExecute(mcTRUE);
      queued = true;
    }
    if (gear_.isActive() == mcTRUE)
      next.setExecute(mcTRUE);
    if (cycle < 1000)
    {
      EXPECT_EQ(gear_.getInGear(), mcFALSE);
      if (next.isActive() == mcTRUE || gear_.isAborted() == mcTRUE)
        premature_handoff = true;
    }
    else
      delayed_servo.release_feedback = true;
    if (cycle == 999)
      EXPECT_NEAR(slave_.toUserVelCmd(), 100, 0.01);
  }
  EXPECT_FALSE(premature_handoff);
  EXPECT_TRUE(observed_in_gear);
  EXPECT_EQ(next.isInVelocity(), mcTRUE);
  EXPECT_NEAR(slave_.toUserVel(), 50, 0.01);
}

class GearInEqualSpeedHandoffTest : public GearInRegressionTest,
                                    public ::testing::WithParamInterface<double>
{
};

TEST_P(GearInEqualSpeedHandoffTest, ActivatesAndAppliesOverride)
{
#ifdef PLOT
  plot_description_ = "Velocity override = " + std::to_string(GetParam());
#endif
  master_move_.setVelocity(100);
  gear_.setRatioNumerator(1);
  gear_.setRatioDenominator(1);
  FbSetOverride override;
  override.setAxis(&slave_);
  override.setVelFactor(GetParam());
  override.setEnable(mcTRUE);
  for (int cycle = 0; cycle < 1000; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    runObservedCycle(override, "override");
    if (master_power_.getPowerStatus() == mcTRUE &&
        slave_power_.getPowerStatus() == mcTRUE)
    {
      master_move_.setExecute(mcTRUE);
      gear_.setExecute(mcTRUE);
    }
  }
  ASSERT_EQ(gear_.getInGear(), mcTRUE);
  ASSERT_NEAR(slave_.toUserVel(), 100, 0.01);
  FbMoveVelocity next;
  next.setAxis(&slave_);
  next.setVelocity(100);
  next.setAcceleration(1000);
  next.setDeceleration(1000);
  next.setJerk(10000);
  next.setBufferMode(mcBuffered);
  next.setExecute(mcTRUE);
  for (int cycle = 0; cycle < 1000; ++cycle)
  {
    ASSERT_NO_FATAL_FAILURE(runCycle());
    runObservedCycle(override, "override");
    runObservedCycle(next, "next");
#ifdef PLOT
    gear_plot_.addBlock("Next", next, plot_time_);
    gear_plot_.add("Velocity", "Successor target with override", plot_time_,
                   next.getVelocity() * GetParam());
#endif
    ASSERT_EQ(next.isError(), mcFALSE);
  }
  EXPECT_EQ(next.isInVelocity(), mcTRUE);
  EXPECT_EQ(slave_.getAxisState(), mcContinuousMotion);
  EXPECT_NEAR(slave_.toUserVel(), 100 * GetParam(), 0.01);
}

INSTANTIATE_TEST_SUITE_P(Overrides, GearInEqualSpeedHandoffTest,
                         ::testing::Values(1.0, 0.5));

// Test MC_GearInPos
TEST_F(FunctionBlockTest, MC_GearInPos)
{
#ifdef PLOT
  GearInTestPlot position_plot;
  fb_profile_.reset();
  axis_profile_.reset();
#endif
  RTmotion::AxisConfig config1;
  RTmotion::AxisConfig config2;
  RTmotion::AXIS_REF axis1;
  axis1 = new RTmotion::Axis();
  axis1->setAxisId(1);
  RTmotion::AXIS_REF axis2;
  axis2 = new RTmotion::Axis();
  axis2->setAxisId(2);

  axis1->setAxisConfig(&config1);
  printf("Axis1 initialized.\n");
  axis2->setAxisConfig(&config2);
  printf("Axis2 initialized.\n");

  RTmotion::Servo* servo1;
  servo1 = new RTmotion::Servo();
  axis1->setServo(servo1);

  RTmotion::Servo* servo2;
  servo2 = new RTmotion::Servo();
  axis2->setServo(servo2);

  RTmotion::FbPower fb_power1;
  fb_power1.setAxis(axis1);
  fb_power1.setEnable(mcTRUE);
  fb_power1.setEnablePositive(mcTRUE);
  fb_power1.setEnableNegative(mcTRUE);

  RTmotion::FbPower fb_power2;
  fb_power2.setAxis(axis2);
  fb_power2.setEnable(mcTRUE);
  fb_power2.setEnablePositive(mcTRUE);
  fb_power2.setEnableNegative(mcTRUE);

  RTmotion::FbMoveVelocity fb_move_vel;
  fb_move_vel.setAxis(axis1);
  fb_move_vel.setVelocity(1);
  fb_move_vel.setAcceleration(10);
  fb_move_vel.setDeceleration(10);
  fb_move_vel.setJerk(50);
  fb_move_vel.setBufferMode(RTmotion::mcAborting);

  RTmotion::FbGearInPos fb_gear_in_pos;
  fb_gear_in_pos.setMaster(axis1);
  fb_gear_in_pos.setSlave(axis2);
  fb_gear_in_pos.setMasterStartDistance(1);
  fb_gear_in_pos.setMasterSyncPosition(3);
  fb_gear_in_pos.setRatioNumerator(1);
  fb_gear_in_pos.setRatioDenominator(2);
  fb_gear_in_pos.setSlaveSyncPosition(1);
  fb_gear_in_pos.setVelocity(50);
  fb_gear_in_pos.setAcceleration(500);
  fb_gear_in_pos.setDeceleration(500);
  fb_gear_in_pos.setPosSyncFactor(0.01);
  fb_gear_in_pos.setVelSyncFactor(0.05);
  fb_gear_in_pos.setBufferMode(mcAborting);

#ifdef PLOT
  fb_profile_.addFB("fbGearInPos");
  fb_profile_.addItemName("fbGearInPos.isEnabled");
  fb_profile_.addItemName("fbGearInPos.StartSync");
  fb_profile_.addItemName("fbGearInPos.InSync");
#endif
  double time_out         = 5;
  double t                = 0;
  bool gear_started       = false;
  int execute_high_cycles = 0;
  constexpr int pulse_cycles =
      static_cast<int>(gear_in_pos_execute_pulse_seconds * 1000);
  while (t < time_out)
  {
    runObservedCycle(*axis1, "axis1");
    runObservedCycle(*axis2, "axis2");
    runObservedCycle(fb_power1, "fb_power1");
    runObservedCycle(fb_power2, "fb_power2");
    runObservedCycle(fb_move_vel, "fb_move_vel");
    if (!gear_started && fb_power1.getPowerStatus() == mcTRUE &&
        fb_power2.getPowerStatus() == mcTRUE)
    {
      fb_move_vel.setExecute(mcTRUE);
      gear_started = true;
    }
    fb_gear_in_pos.setExecute(
        gear_started && execute_high_cycles < pulse_cycles ? mcTRUE : mcFALSE);
    runObservedCycle(fb_gear_in_pos, "fb_gear_in_pos");
    if (fb_gear_in_pos.isEnabled() == mcTRUE)
      ++execute_high_cycles;

#ifdef PLOT
    axis_profile_.addState(axis2->toUserPos(), axis2->toUserVel(),
                           axis2->toUserAccCmd(), t);
    fb_profile_.addState("fbGearInPos.isEnabled",
                         fb_gear_in_pos.isEnabled() == mcTRUE);
    fb_profile_.addState("fbGearInPos.StartSync",
                         fb_gear_in_pos.getStartSync() == mcTRUE);
    fb_profile_.addState("fbGearInPos.InSync",
                         fb_gear_in_pos.getInSync() == mcTRUE);
    fb_profile_.addTime(t);
    position_plot.addPositionGear(fb_gear_in_pos, *axis1, *axis2, t,
                                  1 + (axis1->toUserPosCmd() - 3) * 0.5, 0.5);
#endif
    // printf("Axis 1: Run time: %f, pos: %f, vel: %f\n", t,
    // axis1->toUserPos(), axis1->toUserVel());
    // printf("Axis 2: Run time: %f, pos: %f, vel: %f, axis state: %d\n", t,
    // axis2->toUserPos(), axis2->toUserVel(), axis2->getAxisState());

    t += 0.001;
  }
#ifdef PLOT
  plotProfile(axis_profile_, "mc_gear_in_pos_axis");
  plotProfile(fb_profile_, "mc_gear_in_pos_fb");
  position_plot.plot("", "1:2 position coupling, pulsed Execute");
#endif
  EXPECT_EQ(execute_high_cycles, pulse_cycles);
  EXPECT_EQ(fb_gear_in_pos.isEnabled(), mcFALSE);
  EXPECT_EQ(fb_gear_in_pos.getInSync(), mcTRUE);
  ASSERT_LT(fabs(axis2->toUserVel() - 0.5), 0.1);
  delete servo1;
  delete servo2;
  delete axis1;
  delete axis2;
  servo1 = nullptr;
  servo2 = nullptr;
  axis1  = nullptr;
  axis2  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_ReadMotionState
TEST_F(FunctionBlockTest, DemoReadMotionState)
{
// plot
#ifdef PLOT
  fb_profile_.reset();
  axis_profile_.reset();
#endif
  // initialize the axes object
  AXIS_REF axis;
  axis = new Axis();
  AxisConfig config;
  axis->setAxisConfig(&config);
  axis->setAxisId(1);
  printf("Axis initialized.\n");

  // initialize the servo object
  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  // initialize the MC_Power FB
  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  // initialize the move FB
  FbMoveVelocity fb_move_vel;
  fb_move_vel.setAxis(axis);
  fb_move_vel.setExecute(mcFALSE);
  fb_move_vel.setContinuousUpdate(mcFALSE);
  fb_move_vel.setVelocity(20);
  fb_move_vel.setAcceleration(50);
  fb_move_vel.setDeceleration(50);
  fb_move_vel.setJerk(100);

  // initialize the test FB
  FbReadMotionState fb_read_motion_state;
  fb_read_motion_state.setAxis(axis);
  fb_read_motion_state.setEnable(mcTRUE);
  fb_read_motion_state.setSource(mcCommandedValue);
  printf("Function block initialized.\n");

#ifdef PLOT
  fb_profile_.addFB("fbReadMotionState");
  fb_profile_.addItemName("fbReadMotionState.constantVelocity");
  fb_profile_.addItemName("fbReadMotionState.accelerating");
  fb_profile_.addItemName("fbReadMotionState.directionPositive");
#endif
  // set test cycle
  double timeout      = 0;
  mcBOOL reverse_flag = mcFALSE;
  while (timeout < 4.0)
  {
    // cyclic execution
    runObservedCycle(*axis, "axis");
    runObservedCycle(fb_power, "fb_power");
    runObservedCycle(fb_move_vel, "fb_move_vel");
    runObservedCycle(fb_read_motion_state, "fb_read_motion_state");
    timeout += 0.001;
    // check power state
    if (fb_power.getPowerStatus() == mcTRUE)
    {
      fb_move_vel.setExecute(mcTRUE);
      // printf("Axis powered on %d\n", fb_power.getPowerStatus() == mcTRUE);
    }
    // check the axis state and MC_ReadMotionState outputs
    if (timeout > 0.5)
    {
      if (fb_move_vel.isInVelocity() == mcTRUE && timeout > 2.5)
      {
        // printf("Axis in velocity.\n");
        ASSERT_TRUE(fb_read_motion_state.getConstantVelocity() == mcTRUE);
      }
      else if (reverse_flag == mcFALSE && timeout < 0.8)
      {
        // printf("Axis is accelerating.\n");
        ASSERT_TRUE(fb_read_motion_state.getConstantVelocity() == mcFALSE);
        ASSERT_TRUE(fb_read_motion_state.getAccelerating() == mcTRUE);
        ASSERT_TRUE(fb_read_motion_state.getDecelerating() == mcFALSE);
      }
      else if (reverse_flag == mcTRUE && timeout > 3.2)
      {
        // printf("Axis is decelerating.\n");
        ASSERT_TRUE(fb_read_motion_state.getConstantVelocity() == mcFALSE);
        ASSERT_TRUE(fb_read_motion_state.getAccelerating() == mcFALSE);
        ASSERT_TRUE(fb_read_motion_state.getDecelerating() == mcTRUE);
      }
      ASSERT_TRUE((fb_read_motion_state.getDirectionPositive() == mcTRUE &&
                   reverse_flag == mcFALSE) ||
                  (fb_read_motion_state.getDirectionPositive() == mcFALSE &&
                   reverse_flag == mcTRUE));
      ASSERT_TRUE((fb_read_motion_state.getDirectionNegative() == mcFALSE &&
                   reverse_flag == mcFALSE) ||
                  (fb_read_motion_state.getDirectionPositive() == mcTRUE &&
                   reverse_flag == mcTRUE));
    }

    // reverse velocity
    if (timeout == 3)
    {
      fb_move_vel.setVelocity(-20);
      fb_move_vel.setExecute(mcFALSE);
      reverse_flag = mcTRUE;
    }

    // printf("Run time: %f, pos: %lf, vel: %lf, acc: %lf, ConsVel:%d, Acc:%d,
    // Dirt:%d\n",
    //       timeout, axis->toUserPosCmd(), axis->toUserVelCmd(),
    //       axis->toUserAccCmd(), fb_read_motion_state.getConstantVelocity(),
    //       fb_read_motion_state.getAccelerating(),
    //       fb_read_motion_state.getDirectionPositive());

#ifdef PLOT
    axis_profile_.addState(axis->toUserPosCmd(), axis->toUserVelCmd(),
                           axis->toUserAccCmd(), timeout);
    fb_profile_.addState("fbReadMotionState.constantVelocity",
                         fb_read_motion_state.getConstantVelocity() == mcTRUE);
    fb_profile_.addState("fbReadMotionState.accelerating",
                         fb_read_motion_state.getAccelerating() == mcTRUE);
    fb_profile_.addState("fbReadMotionState.directionPositive",
                         fb_read_motion_state.getDirectionPositive() == mcTRUE);
    fb_profile_.addTime(timeout);
#endif
  }

#ifdef PLOT
  plotProfile(axis_profile_, "mc_read_motion_state_axis");
  plotProfile(fb_profile_, "mc_read_motion_state_fb");
#endif

  // posprocessing
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_SetOverride
TEST_F(FunctionBlockTest, MC_SetOverride)
{
  // plot
#ifdef PLOT
  fb_profile_.reset();
  axis_profile_.reset();
#endif

  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbMoveVelocity mov_vel;
  mov_vel.setAxis(axis);
  mov_vel.setVelocity(200);
  mov_vel.setAcceleration(500);
  mov_vel.setDeceleration(500);
  mov_vel.setJerk(5000);
  mov_vel.setBufferMode(mcAborting);

  FbSetOverride fb_set_override;
  fb_set_override.setAxis(axis);
  fb_set_override.setVelFactor(0.5);
  fb_set_override.setAccFactor(0.5);
  fb_set_override.setJerkFactor(0.5);

#ifdef PLOT
  fb_profile_.addFB("fbSetOverride");
  fb_profile_.addItemName("fbSetOverride.isEnabled");
#endif
  double time_out = 9;
  double t        = 0;
  while (t < time_out)
  {
    runObservedCycle(*axis, "axis");
    runObservedCycle(fb_power, "fb_power");
    runObservedCycle(mov_vel, "mov_vel");
    runObservedCycle(fb_set_override, "fb_set_override");

    if (mov_vel.isEnabled() == mcFALSE)
    {
      mov_vel.setExecute(mcTRUE);
      std::cout << "axis poweron, set start velocity to 500\n";
    }

    if (fabs(t - 1.0) < 0.0001)
    {
      fb_set_override.setEnable(mcTRUE);
      std::cout << "enable overriding, set vel, acc, and jerk factors all to "
                   "1/2\n";
    }

    if (fabs(t - 4.0) < 0.0001)
    {
      ASSERT_LT(fabs(axis->toUserVel() - 100), 1);
      fb_set_override.setEnable(mcFALSE);
      fb_set_override.setVelFactor(0);
      fb_set_override.setAccFactor(1);
      fb_set_override.setJerkFactor(1);
      std::cout << "disable overriding\n";
    }

    if (fabs(t - 6.0) < 0.0001)
    {
      ASSERT_LT(fabs(axis->toUserVel() - 100), 1);
    }

    t += 0.001;
    // printf("Axis: Run time: %f,\tvel: %f,\tacc:%f\n", t, axis->toUserVel(),
    // axis->toUserAcc());

#ifdef PLOT
    axis_profile_.addState(axis->toUserPosCmd(), axis->toUserVelCmd(),
                           axis->toUserAccCmd(), t);
    fb_profile_.addState("fbSetOverride.isEnabled",
                         fb_set_override.isEnabled() == mcTRUE);
    fb_profile_.addTime(t);
#endif
  }

#ifdef PLOT
  plotProfile(axis_profile_, "mc_set_override_axis");
  plotProfile(fb_profile_, "mc_set_override_fb");
#endif

  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

TEST_F(FunctionBlockTest, MC_DigitalCamSwitch)
{
#ifdef PLOT
  fb_profile_.reset();
  axis_profile_.reset();
#endif

  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbMoveVelocity fb_move_vel;
  fb_move_vel.setAxis(axis);
  fb_move_vel.setExecute(mcFALSE);
  fb_move_vel.setContinuousUpdate(mcFALSE);
  fb_move_vel.setVelocity(1);
  fb_move_vel.setAcceleration(50);
  fb_move_vel.setDeceleration(50);
  fb_move_vel.setJerk(500);
  printf("Function block initialized.\n");

  McCamSwitch cam_switch[4] = { { 1, 2.0, 3.0, 1, 0, NAN },
                                { 1, 2.5, 3.0, 2, 0, NAN },
                                { 1, 4.0, 1.0, 0, 0, NAN },
                                { 2, 3.0, NAN, 0, 1, 1350 } };

  McCamSwitchRef switches;
  switches.switch_number_      = 4;
  switches.cam_switch_pointer_ = cam_switch;

  McTrack tracks[2] = { { mcTRUE, 5, 0.5, 0.5, 0 },
                        { mcTRUE, 5, 0.5, 0.5, 0 } };

  mcDWORD output;
  FbDigitalCamSwitch fb_digital_cam_switch;
  fb_digital_cam_switch.setAxis(axis);
  fb_digital_cam_switch.setEnable(mcFALSE);
  fb_digital_cam_switch.setSwitches(switches);
  fb_digital_cam_switch.setOutputs(&output);
  fb_digital_cam_switch.setTrackOptions(tracks);
  fb_digital_cam_switch.setEnableMask(0x3);
  fb_digital_cam_switch.setValueSource(mcSetValue);

#ifdef PLOT
  fb_profile_.addFB("fbDigitalCamSwitch");
  fb_profile_.addItemName("fbDigitalCamSwitch.Track1");
  fb_profile_.addItemName("fbDigitalCamSwitch.Track2");
  fb_profile_.addItemName("fbDigitalCamSwitch.inOperation");
#endif

  double timeout = 0;
  while (timeout < 10.0)
  {
    runObservedCycle(*axis, "axis");
    runObservedCycle(fb_power, "fb_power");
    runObservedCycle(fb_move_vel, "fb_move_vel");
    runObservedCycle(fb_digital_cam_switch, "fb_digital_cam_switch");
    timeout += 0.001;

#ifdef PLOT
    axis_profile_.addState(axis->toUserPos(), axis->toUserVel(),
                           axis->toUserAccCmd(), timeout);
    fb_profile_.addState("fbDigitalCamSwitch.Track1", output & 0x1);
    fb_profile_.addState("fbDigitalCamSwitch.Track2", output & 0x2);
    fb_profile_.addState("fbDigitalCamSwitch.inOperation",
                         fb_digital_cam_switch.isInOperation() == mcTRUE);
    fb_profile_.addTime(timeout);
#endif

    if (fb_move_vel.isEnabled() == mcFALSE &&
        fb_power.getPowerStatus() == mcTRUE)
    {
      fb_move_vel.setExecute(mcTRUE);
      fb_digital_cam_switch.setEnable(mcTRUE);
    }
  }
#ifdef PLOT
  plotProfile(axis_profile_, "mc_digital_cam_switch_axis");
  plotProfile(fb_profile_, "mc_digital_cam_switch_fb");
#endif
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_MoveSuperimposed without underlying motion
TEST_F(FunctionBlockTest, MC_MoveSuperimposed1)
{
#ifdef PLOT
  fb_profile_.reset();
  axis_profile_.reset();
#endif
  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbMoveSuperimposed fb_move_sup;
  fb_move_sup.setAxis(axis);
  fb_move_sup.setContinuousUpdate(mcFALSE);
  fb_move_sup.setDistance(600);
  fb_move_sup.setVelocityDiff(300);
  fb_move_sup.setAcceleration(500);
  fb_move_sup.setDeceleration(500);
  fb_move_sup.setJerk(5000);
  fb_move_sup.setExecute(mcFALSE);
#ifdef PLOT
  fb_profile_.addFB("fb_move_sup");
  fb_profile_.addItemName("fb_move_sup.go");
  fb_profile_.addItemName("fb_move_sup.done");
#endif
  double time_out = 5;
  double t        = 0;
  while (t < time_out)
  {
    runObservedCycle(*axis, "axis");
    runObservedCycle(fb_power, "fb_power");
    runObservedCycle(fb_move_sup, "fb_move_sup");

    if (1 < t && fb_power.isEnabled() == mcTRUE)
      fb_move_sup.setExecute(mcTRUE);

#ifdef PLOT
    axis_profile_.addState(axis->toUserPos(), axis->toUserVel(),
                           axis->toUserAccCmd(), t);
    fb_profile_.addState("fb_move_sup.go", fb_move_sup.isEnabled() == mcTRUE);
    fb_profile_.addState("fb_move_sup.done", fb_move_sup.isDone() == mcTRUE);
    fb_profile_.addTime(t);
#endif
    t += 0.001;
  }
#ifdef PLOT
  plotProfile(axis_profile_, "mc_mov_sup1_axis");
  plotProfile(fb_profile_, "mc_mov_sup1_fb");
#endif
  ASSERT_LT(fabs(axis->toUserVel() - 0.0), 0.01);
  ASSERT_LT(fabs(axis->toUserPos() - 600), 0.01);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test two MC_MoveSuperimposed with underlying motion
TEST_F(FunctionBlockTest, MC_MoveSuperimposed2)
{
#ifdef PLOT
  fb_profile_.reset();
  axis_profile_.reset();
#endif
  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbMoveRelative fb_move_rel;
  fb_move_rel.setAxis(axis);
  fb_move_rel.setContinuousUpdate(mcFALSE);
  fb_move_rel.setDistance(900);
  fb_move_rel.setVelocity(300);
  fb_move_rel.setAcceleration(500);
  fb_move_rel.setDeceleration(500);
  fb_move_rel.setJerk(5000);
  fb_move_rel.setBufferMode(mcAborting);

  FbMoveSuperimposed fb_move_sup1;
  fb_move_sup1.setAxis(axis);
  fb_move_sup1.setContinuousUpdate(mcFALSE);
  fb_move_sup1.setDistance(600);
  fb_move_sup1.setVelocityDiff(300);
  fb_move_sup1.setAcceleration(300);
  fb_move_sup1.setDeceleration(300);
  fb_move_sup1.setJerk(5000);
  fb_move_sup1.setExecute(mcFALSE);

  FbMoveSuperimposed fb_move_sup2;
  fb_move_sup2.setAxis(axis);
  fb_move_sup2.setContinuousUpdate(mcFALSE);
  fb_move_sup2.setDistance(100);
  fb_move_sup2.setVelocityDiff(200);
  fb_move_sup2.setAcceleration(100);
  fb_move_sup2.setDeceleration(100);
  fb_move_sup2.setJerk(5000);
  fb_move_sup2.setExecute(mcFALSE);

#ifdef PLOT
  fb_profile_.addFB("fb_move_rel");
  fb_profile_.addFB("fb_move_sup1");
  fb_profile_.addFB("fb_move_sup2");
  fb_profile_.addItemName("fb_move_rel.go");
  fb_profile_.addItemName("fb_move_rel.done");
  fb_profile_.addItemName("fb_move_rel.aborted");
  fb_profile_.addItemName("fb_move_sup1.go");
  fb_profile_.addItemName("fb_move_sup1.done");
  fb_profile_.addItemName("fb_move_sup1.aborted");
  fb_profile_.addItemName("fb_move_sup2.go");
  fb_profile_.addItemName("fb_move_sup2.done");
  fb_profile_.addItemName("fb_move_sup2.aborted");
#endif
  double time_out = 4;
  double t        = 0;
  while (t < time_out)
  {
    runObservedCycle(*axis, "axis");
    runObservedCycle(fb_power, "fb_power");
    runObservedCycle(fb_move_rel, "fb_move_rel");
    runObservedCycle(fb_move_sup1, "fb_move_sup1");
    runObservedCycle(fb_move_sup2, "fb_move_sup2");

    // After enabled, move_relative_1 start to move
    if (fb_power.isEnabled() == mcTRUE && t < 1)
      fb_move_rel.setExecute(mcTRUE);

    if (0.5 < t && fb_move_rel.isEnabled() == mcTRUE)
      fb_move_sup1.setExecute(mcTRUE);

    if (1.0 < t && fb_move_rel.isEnabled() == mcTRUE)
      fb_move_sup2.setExecute(mcTRUE);

#ifdef PLOT
    axis_profile_.addState(axis->toUserPos(), axis->toUserVel(),
                           axis->toUserAccCmd(), t);
    fb_profile_.addState("fb_move_rel.go", fb_move_rel.isEnabled() == mcTRUE);
    fb_profile_.addState("fb_move_rel.done", fb_move_rel.isDone() == mcTRUE);
    fb_profile_.addState("fb_move_rel.aborted",
                         fb_move_rel.isAborted() == mcTRUE);
    fb_profile_.addState("fb_move_sup1.go", fb_move_sup1.isEnabled() == mcTRUE);
    fb_profile_.addState("fb_move_sup1.done", fb_move_sup1.isDone() == mcTRUE);
    fb_profile_.addState("fb_move_sup1.aborted",
                         fb_move_sup1.isAborted() == mcTRUE);
    fb_profile_.addState("fb_move_sup2.go", fb_move_sup2.isEnabled() == mcTRUE);
    fb_profile_.addState("fb_move_sup2.done", fb_move_sup2.isDone() == mcTRUE);
    fb_profile_.addState("fb_move_sup2.aborted",
                         fb_move_sup2.isAborted() == mcTRUE);
    fb_profile_.addTime(t);
#endif
    t += 0.001;
  }
#ifdef PLOT
  plotProfile(axis_profile_, "mc_mov_sup2_axis");
  plotProfile(fb_profile_, "mc_mov_sup2_fb");
#endif
  ASSERT_LT(fabs(axis->toUserVel() - 0.0), 0.01);
  ASSERT_GE(fabs(axis->toUserPos()), 1000);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test one MC_MoveSuperimposed with underlying motion,
// align with the example in Part 1.
TEST_F(FunctionBlockTest, MC_MoveSuperimposed3)
{
#ifdef PLOT
  fb_profile_.reset();
  axis_profile_.reset();
#endif
  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbMoveRelative fb_move_rel;
  fb_move_rel.setAxis(axis);
  fb_move_rel.setContinuousUpdate(mcFALSE);
  fb_move_rel.setDistance(10000);
  fb_move_rel.setVelocity(300);
  fb_move_rel.setAcceleration(100);
  fb_move_rel.setDeceleration(100);
  fb_move_rel.setJerk(1000);
  fb_move_rel.setBufferMode(mcAborting);

  FbMoveSuperimposed fb_move_sup;
  fb_move_sup.setAxis(axis);
  fb_move_sup.setContinuousUpdate(mcFALSE);
  fb_move_sup.setDistance(1000);
  fb_move_sup.setVelocityDiff(200);
  fb_move_sup.setAcceleration(100);
  fb_move_sup.setDeceleration(100);
  fb_move_sup.setJerk(1000);
  fb_move_sup.setExecute(mcFALSE);
#ifdef PLOT
  fb_profile_.addFB("fb_move_rel");
  fb_profile_.addFB("fb_move_sup");
  fb_profile_.addItemName("fb_move_rel.go");
  fb_profile_.addItemName("fb_move_rel.done");
  fb_profile_.addItemName("fb_move_rel.aborted");
  fb_profile_.addItemName("fb_move_sup.go");
  fb_profile_.addItemName("fb_move_sup.done");
#endif
  double time_out = 40;
  double t        = 0;
  while (t < time_out)
  {
    runObservedCycle(*axis, "axis");
    runObservedCycle(fb_power, "fb_power");
    runObservedCycle(fb_move_rel, "fb_move_rel");
    runObservedCycle(fb_move_sup, "fb_move_sup");

    // After enabled, move_relative_1 start to move
    if (fb_power.isEnabled() == mcTRUE && t < 1)
      fb_move_rel.setExecute(mcTRUE);

    if (fabs(t - 4) <= 0.001 && fb_move_rel.isEnabled() == mcTRUE)
      fb_move_sup.setExecute(mcTRUE);

    if (fabs(t - 11) <= 0.001 && fb_move_sup.isEnabled() == mcTRUE)
      fb_move_sup.setExecute(mcFALSE);

    if (fabs(t - 12) <= 0.001 && fb_move_sup.isEnabled() == mcFALSE)
      fb_move_sup.setExecute(mcTRUE);

    if (fabs(t - 14) <= 0.001 && fb_move_sup.isEnabled() == mcTRUE)
      fb_move_sup.setExecute(mcFALSE);

    if (fabs(t - 20) <= 0.001 && fb_move_sup.isEnabled() == mcFALSE)
      fb_move_sup.setExecute(mcTRUE);

    if (t > 30 && fb_move_sup.isDone() == mcTRUE)
      fb_move_sup.setExecute(mcFALSE);

#ifdef PLOT
    axis_profile_.addState(axis->toUserPos(), axis->toUserVel(),
                           axis->toUserAccCmd(), t);
    fb_profile_.addState("fb_move_rel.go", fb_move_rel.isEnabled() == mcTRUE);
    fb_profile_.addState("fb_move_rel.done", fb_move_rel.isDone() == mcTRUE);
    fb_profile_.addState("fb_move_rel.aborted",
                         fb_move_rel.isAborted() == mcTRUE);
    fb_profile_.addState("fb_move_sup.go", fb_move_sup.isEnabled() == mcTRUE);
    fb_profile_.addState("fb_move_sup.done", fb_move_sup.isDone() == mcTRUE);
    fb_profile_.addTime(t);
#endif
    t += 0.001;
  }
#ifdef PLOT
  plotProfile(axis_profile_, "mc_mov_sup3_axis");
  plotProfile(fb_profile_, "mc_mov_sup3_fb");
#endif
  ASSERT_LT(fabs(axis->toUserVel() - 0.0), 0.01);
  ASSERT_GE(fabs(axis->toUserPos()), 12000);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

int main(int argc, char** argv)
{
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
