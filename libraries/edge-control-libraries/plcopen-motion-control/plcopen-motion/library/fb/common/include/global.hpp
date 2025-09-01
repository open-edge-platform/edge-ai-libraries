// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file global.hpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#pragma once

#include <memory>
#include <stdint.h>
#include <string>
#include <time.h>

#define __EPSILON 0.01

#define NSEC_PER_SEC (1000000000L)
#define NSEC_PER_MILLI_SEC (1000000L)
#define NSEC_PER_MICRO_SEC (1000L)
#ifndef DIFF_NS
#define DIFF_NS(A, B)                                                          \
  (((B).tv_sec - (A).tv_sec) * NSEC_PER_SEC + ((B).tv_nsec) - (A).tv_nsec)
#endif
#ifdef _WIN32
#include <intrin.h>
#else
#include <x86intrin.h>
#endif

namespace RTmotion
{
#define VAR_IN_OUT
#define VAR_INPUT
#define VAR_OUTPUT

// clang-format off
// Declare mcBOOL as enum class to avoid
// other enums are recognized as true or false
enum class mcBool: uint8_t
{ 
  mcFalse = 0,
  mcTrue =1
};
#ifndef mcBOOL
typedef mcBool mcBOOL;
#else
#error "mcBOOL has already been defined elsewhere!"
#endif

#ifndef mcFALSE
#define mcFALSE mcBool::mcFalse
#else
#error "mcFALSE has already been defined elsewhere!"
#endif

#ifndef mcTRUE
#define mcTRUE mcBool::mcTrue
#else
#error "mcTRUE has already been defined elsewhere!"
#endif

#ifndef mcUSINT
typedef uint8_t mcUSINT;
#else
#error "mcUSINT has already been defined elsewhere!"
#endif

#ifndef mcBYTE
typedef mcUSINT mcBYTE;
#else
#error "mcBYTE has already been defined elsewhere!"
#endif

#ifndef mcSINT
typedef int8_t mcSINT;
#else
#error "mcSINT has already been defined elsewhere!"
#endif

#ifndef mcWORD
typedef uint16_t mcWORD;
#else
#error "mcWORD has already been defined elsewhere!"
#endif

#ifndef mcUINT
typedef uint16_t mcUINT;
#else
#error "mcUINT has already been defined elsewhere!"
#endif

#ifndef mcINT
typedef int16_t mcINT;
#else
#error "mcINT has already been defined elsewhere!"
#endif

#ifndef mcDWORD
typedef uint32_t mcDWORD;
#else
#error "mcDWORD has already been defined elsewhere!"
#endif

#ifndef mcUDINT
typedef uint32_t mcUDINT;
#else
#error "mcUDINT has already been defined elsewhere!"
#endif

#ifndef mcDINT
typedef int32_t mcDINT;
#else
#error "mcDINT has already been defined elsewhere!"
#endif

#ifndef mcLWORD
typedef uint64_t mcLWORD;
#else
#error "mcLWORD has already been defined elsewhere!"
#endif

#ifndef mcULINT
typedef uint64_t mcULINT;
#else
#error "mcULINT has already been defined elsewhere!"
#endif

#ifndef mcLINT
typedef int64_t mcLINT;
#else
#error "mcLINT has already been defined elsewhere!"
#endif

#ifndef mcREAL
typedef float mcREAL;
#else
#error "mcREAL has already been defined elsewhere!"
#endif

#ifndef mcLREAL
typedef double mcLREAL;
#else
#error "mcLREAL has already been defined elsewhere!"
#endif

#ifndef mcSTRING
typedef char* mcSTRING;
#else
#error "mcSTRING has already been defined elsewhere!"
#endif
// clang-format on

typedef enum
{
  mcServoNoError            = 0,
  mcServoFieldbusInitError  = 1,
  mcServoPowerError         = 2,
  mcServoPoweringOnError    = 3,
  mcServoErrorWhenPoweredOn = 4,
  mcServoPoweringOffError   = 5
} MC_SERVO_ERROR_CODE;

/* Servo control mode */
typedef enum
{
  mcServoControlModePosition  = 0,
  mcServoControlModeVelocity  = 1,
  mcServoControlModeTorque    = 2,
  mcServoControlModeHomeServo = 3
} MC_SERVO_CONTROL_MODE;

/* IO error code */
typedef enum
{
  mcIONoError             = 0,  // IO has no error
  mcIOInvalidOffsetError  = 1,  // Get IO offset error
  mcIONumberError         = 2,  // Invalid IO number
  mcIODataBitLengthError  = 3,  // Invalid bit length
  mcIOEtherCATStateError  = 4,  // Wrong EtherCAT state
  mcIOEtherCATConfigError = 5,  // No IO PDO due to EtherCAT config error
  mcIOSegmentationError   = 6,  // malloc() failed
  mcIOTypeError           = 7   // input or Output tpye error
} MC_IO_ERROR_CODE;

/* MC error code */
typedef enum
{
  mcErrorCodeGood                   = 0x00,  // Success
  mcErrorCodeExceedNodeQueueSize    = 0x01,  // Node queue size not enough
  mcErrorCodeUnsupportedBufferMode  = 0x02,  // Unsupported buffer mode for FB
  mcErrorCodeScurveNotFeasible      = 0x10,  // Not feasible to compute Scurve
  mcErrorCodeScurveMaxVelNotReached = 0x21,  // Maximum velocity is not
                                             // reached
  mcErrorCodeScurveMaxAccNotReached = 0x22,  // Maximum acceleration is
                                             // not reached
  mcErrorCodeScurveFailToFindMaxAcc = 0x23,  // Fail to find max velocity
  mcErrorCodeScurveInvalidInput     = 0x24,  // Invalid constraints for Scurve
                                             // planning
  mcErrorCodeAxisStateViolation = 0x30,      // General invalid state transition
  mcErrorCodePowerOnOffFromErrorStop  = 0x31,   // Try to power on at ErrorStop
  mcErrorCodeInvalidStateFromStopping = 0x32,   // Invalid state transition at
                                                // Stopping
  mcErrorCodeInvalidStateFromErrorStop = 0x33,  // Invalid state transition at
                                                // ErrorStop
  mcErrorCodeInvalidStateFromDisabled = 0x34,   // Invalid state transition at
                                                // Disabled
  mcErrorCodeInvalidStateFromHoming = 0x35,     // Invalid state transition at
                                                // Homing
  mcErrorCodeMotionLimitError = 0x40,           // Velocity, Acceleration or
                                                // Position over Limit
  mcErrorCodeInvalidDirectionPositive = 0x41,   // Velocity in forbiden
                                                // direction
  mcErrorCodeInvalidDirectionNegative = 0x42,   // Velocity in forbiden
                                                // direction
  mcErrorCodeVelocityOverLimit         = 0x43,  // Velocity over limit
  mcErrorCodeAccelerationOverLimit     = 0x44,  // Acceleration over limit
  mcErrorCodePositionOverPositiveLimit = 0x45,  // Position over positive
                                                // limit
  mcErrorCodePositionOverNegativeLimit = 0x46,  // Position over negative
                                                // limit
  mcErrorCodeVelocitySetValueError = 0x47,      // Set velocity to zero value
  mcErrorCodeAccelerationSetValueError =
      0x48,  // Set acceleration to zero value
  mcErrorCodeDecelerationSetValueError =
      0x49,                                 // Set deceleration to zero value
  mcErrorCodeJerkSetValueError     = 0x50,  // Set jerk to zero value
  mcErrorCodeDurationSetValueError = 0x51,  // Set duration to zero value
  mcErrorCodeAxisErrorStop         = 0x52,  // Axis error stopped
  mcErrorCodeMotionLimitUnset      = 0x53,  // Motion limit not initialized
  mcErrorCodeVelocityOverrideValueInvalid =
      0x54,  // Set velocity factor beyond [0,1] for MC_SetOverride
  mcErrorCodeAccelerationOverrideValueInvalid =
      0x55,  // Set acceleration factor beyond (0,1] for MC_SetOverride
  mcErrorCodeJerkOverrideValueInvalid =
      0x56,  // Set jerk factor beyond (0,1] for MC_SetOverride
  mcErrorCodeServoNoError           = 0x60,    // Servo has no error
  mcErrorCodeServoFieldbusInitError = 0x61,    // Servo fieldbus initialize
                                               // error
  mcErrorCodeServoPowerError      = 0x62,      // Servo power error
  mcErrorCodeServoPoweringOnError = 0x63,      // Servo has error during
                                               // powering on
  mcErrorCodeServoErrorWhenPoweredOn = 0x64,   // Servo has error after
                                               // powered on
  mcErrorCodeServoPoweringOffError = 0x65,     // Servo has error during
                                               // powering off
  mcErrorCodeSetPositionInvalidState = 0x70,   // Set position when axis in
                                               // "Disabled" or "ErrorStop"
  mcErrorCodeSetControllerModeSuccess = 0x80,  // Set controller mode success
  mcErrorCodeSetControllerModeTimeout = 0x81,  // Set controller mode over
                                               // 1000 cycles
  mcErrorCodeSetControllerModeInvalidState =
      0x82,  // Set controller mode when axis in
             // "mcStopping" or "mcErrorStop" or "mcHoming"
  mcErrorCodeSetControllerModeInvalid = 0x83,  // Invalid controller mode
  mcErrorCodeHomeServoModeError  = 0x84,  // execute home FB without home mode
  mcErrorCodeHomeStateError      = 0x85,  // execute absolute FB without home
  mcErrorCodeSetSourceError      = 0x86,  // Invalid relevant data source
  mcErrorCodeSetAxisError        = 0x87,  // Invalid axis object
  mcErrorCodeCamTableWrongNumber = 0x90,  // Number of elements in cam
                                          // table array mismatch nElement
  mcErrorCodeMasterOutOfRange = 0x91,     // Master position is out of
                                          // range in cam table
  mcErrorCodeSlaveExceedLimit = 0x92,     // Slave's jerk or acceleration
                                          // or velocity over limit
  mcErrorCodeCamTableEndPointTypeError = 0x93,  // Cam table must set end point
                                                // type as noNextSegment
  mcErrorCodeCamTableElementNumberOverLimit = 0x94,  // Cam table element number
                                                     // over limit
  mcErrorCodeCamSlaveUnmatch = 0x95,       // Slave axis inconsistent between
                                           // CamTableId and CamIn
  mcErrorCodeIOInvalidOffsetError = 0xA1,  // Get IO offset error
  mcErrorCodeIONumberError        = 0xA2,  // Invalid IO number
  mcErrorCodeIODataBitLengthError = 0xA3,  // Invalid bit length
  mcErrorCodeIOEtherCATStateError = 0xA4,  // Wrong EtherCAT state
  mcErrorCodeIOEtherCATConfigError =
      0xA5,  // No IO PDO due to EtherCAT config error
  mcErrorCodeIOSegmentationError     = 0xA6,  // malloc() failed
  mcErrorCodeIOTypeError             = 0xA7,  // input or Output tpye error
  mcErrorCodeInGearThresholdSetError = 0xB1,  // Set Gear RatioDenominator to 0
  mcErrorCodeGearRatioDenominatorSetZero =
      0xB2,  // Set Gear RatioDenominator to 0
  mcErrorCodeGearInPosOutOfSyncRange   = 0xB3,  // Invalid velocity direction
  mcErrorCodeGearInPosInvalidDirection = 0xB4,  // Master position is our of
                                                // gearInPos sync range
  mcErrorCodeOutputRefNotInitialized = 0xC1,    // Output_Ref not initialized
                                                // and is nullptr
  mcErrorCodeFaultyTrackOptions = 0xC2,         // Faulty Track Options data
  mcErrorCodeFaultyCamSwitch    = 0xC3,         // Faulty Cam Switch data
  mcErrorCodeEdgePositionOutOfTwoModuloRanges =
      0xC4,  // Cam switch edge position is out of two modulo ranges
} MC_ERROR_CODE;

/**
 * Axis states
 */
typedef enum
{
  /**
   * The state ‘Disabled’ describes the initial state of the axis.
   * In this state the movement of the axis is not influenced by the FBs. Power
   * is off and there is no error
   * in the axis.
   * If the MC_Power FB is called with ‘Enable’=mcTrue while being in
   * ‘Disabled’, the state changes to ‘Standstill’. The axis feedback is
   * operational before entering the state ‘Standstill’. Calling MC_Power with
   * ‘Enable’=mcFalse in any state except ‘ErrorStop’ transfers the axis to the
   * state ‘Disabled’, either directly or via any other state. Any on-going
   * motion commands on the axis are
   * aborted (‘CommandAborted’).
   */
  mcDisabled = 0,

  /**
   * Power is on, there is no error in the axis, and there are no motion
   * commands active on the axis.
   */
  mcStandstill         = 1,
  mcHoming             = 2,  /// Homing
  mcDiscreteMotion     = 3,  /// DiscreteMotion
  mcContinuousMotion   = 4,  /// ContinuousMotion
  mcSynchronizedMotion = 5,  /// SynchronizedMotion
  mcStopping           = 6,  /// Stopping

  /**
   * ‘ErrorStop’ is valid as highest priority and applicable in case of an
   * error. The axis can have either
   * power enabled or disabled and can be changed via MC_Power. However, as long
   * as the error is pend-
   * ing the state remains ‘ErrorStop’.
   * The intention of the ‘ErrorStop’ state is that the axis goes to a stop, if
   * possible. There is no further
   * motion command accepted until a reset has been done from the ‘ErrorStop’
   * state.
   * The transition to ‘ErrorStop’ refers to errors from the axis and axis
   * control, and not from the Function
   * Block instances. These axis errors may also be reflected in the output of
   * the Function Blocks ‘FB
   * instances errors’.
   */
  mcErrorStop = 7,
} MC_AXIS_STATES;

/* Motion direction */
typedef enum
{
  mcPositiveDirection = 1,
  mcShortestWay       = 2,
  mcNegativeDirection = 3,
  mcCurrentDirection  = 4,
} MC_DIRECTION;

/* Network error code */
typedef enum
{
  mcNetworkGood            = 0,
  mcNetworkConnectionBreak = 1,
} MC_NETWORK_ERROR_CODE;

/**
 * MC_BUFFER_MODE
 *
 */
typedef enum
{
  /**
   * @brief Start FB immediately (default mode).
   * The next FB aborts an ongoing motion and the command
   * affects the axis immediately. The buffer is cleared.
   */
  mcAborting = 0,
  /**
   * @brief Start FB after current motion has finished.
   * The next FB affects the axis as soon as the previous movement is ‘Done’.
   * There is no blending.
   */
  mcBuffered = 1,
  /**
   * @brief The velocity is blended with the lowest velocity of both FBs.
   *
   */
  mcBlendingLow = 2,  /// The velocity is blended with the lowest velocity of
                      /// both FBs
  mcBlendingPrevious = 3,  /// The velocity is blended with the velocity of
                           /// the first FB
  mcBlendingNext = 4,  /// The velocity is blended with velocity of the second
                       /// FB
  mcBlendingHigh = 5   /// The velocity is blended with highest velocity of
                       /// both FBs
} MC_BUFFER_MODE;

typedef enum
{
  mcNoMoveType        = 0,
  mcMoveAbsoluteMode  = 1,
  mcMoveRelativeMode  = 2,
  mcMoveAdditiveMode  = 3,
  mcMoveVelocityMode  = 4,
  mcHaltMode          = 5,
  mcStopMode          = 6,
  mcHomingMode        = 7,
  mcTorqueControlMode = 8,
  mcCamInMode         = 9,
  mcMoveChaseMode     = 10,
  mcGearInMode        = 11,
  mcGearInPosMode     = 12,
  mcSyncOutMode       = 13,
  mcMoveSupMode       = 14
} MC_MOTION_MODE;

typedef enum
{
  mcNoModeSwitch = 0,
  mcPosToVel,
  mcPosToToq,
  mcPosToHome,
  mcVelToPos,
  mcVelToToq,
  mcVelToHome,
  mcToqToPos,
  mcToqToVel,
  mcToqToHome,
  mcHomeToPos,
  mcHomeToVel,
  mcHomeToToq
} MC_MODE_SWITCH;

/* MC_SetPosition mode */
typedef enum
{
  mcSetPositionModeRelative = 0,
  mcSetPositionModeAbsolute = 1,
} MC_SET_POSITION_MODE;

/* CIA402 servo driver mode */
typedef enum
{
  mcServoDriveModePP   = 1,
  mcServoDriveModePV   = 3,
  mcServoDriveModePT   = 4,
  mcServoDriveModeNULL = 5,
  mcServoDriveModeHM   = 6,
  mcServoDriveModeIP   = 7,
  mcServoDriveModeCSP  = 8,
  mcServoDriveModeCSV  = 9,
  mcServoDriveModeCST  = 10
} MC_SERVO_DRIVE_MODE;

typedef enum
{
  mcOffLine = 0,
  mcOnLine  = 1,
  mcRuckig  = 2,
  mcPoly5   = 3,
  mcLine    = 4
} PLANNER_TYPE;

typedef enum
{
  mcNullValue      = 0,
  mcSetValue       = 1,
  mcActualValue    = 2,
  mcCommandedValue = 3
} MC_SOURCE;

}  // namespace RTmotion
