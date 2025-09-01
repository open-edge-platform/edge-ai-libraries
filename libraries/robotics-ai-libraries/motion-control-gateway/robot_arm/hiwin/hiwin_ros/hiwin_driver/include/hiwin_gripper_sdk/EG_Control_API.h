// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#ifndef EG_CONTROL_API_EG_CONTROL_API_H_
#define EG_CONTROL_API_EG_CONTROL_API_H_

#ifdef EG_CONTROL_API_EG_CONTROL_API_H_
#define EG_API __declspec(dllexport)
#else
#define EG_API __declspec(dllimport)
#endif

enum Error_Code {
	// Error representation
	EGErrorINT			  =	1000,
	// Com Port Error
	ComConnectFail		  =	1001,
	ComNumOverLimit		  =	1002,
	ComHardwareDisConnect = 1003,
	ComClosed			  =	1004,
	RetryConnectFail	  = 1005,
	ComRepeatConnectError = 1006,
	// Setting Error
	EGTypeError			  = 2001,
	EGidError			  =	2002,
	EGCmdRepeated		  =	2003,
	MoveStrokeMaxError	  = 2011,
	MoveStrokeMinError	  = 2012,
	MoveSpeedMaxError	  =	2013,
	MoveSpeedMinError	  =	2014,
	GripDirError		  = 2021,
	GripStrokeMaxError	  = 2022,
	GripStrokeMinError	  = 2023,
	GripSpeedMaxError	  =	2024,
	GripSpeedMinError	  =	2025,
	GripForceMaxError	  =	2026,
	GripForceMinError	  =	2027,
	ExpertStrokeMaxError  = 2031,
	ExpertStrokeMinError  = 2032,
	ExpertSpeedSetError   = 2033,

	// Alarm Signal
	AlarmPosition		  = 3001,
	AlarmReset			  = 3003,
	// Timeout Error
	ConnectTimeout		  = 4001,
	GetFWVerTimeout		  = 4002,
	StopMotionTimeout	  = 4003,
	ResetMotionTimeout	  = 4004,
	RunMoveTimeout		  = 4005,
	RunGripTimeout		  = 4006,
	RunExpertTimeout	  = 4007,
	WorkStateTimeout	  = 4008,
};

typedef int HEG;

#ifdef __cplusplus
extern "C" {
#endif

// Software Version
EG_API void __stdcall CurSoftwareVersion(unsigned int &Ver1, unsigned int &Ver2, unsigned int &Ver3, unsigned int &Ver4);

// Single Gripper APIs
EG_API int __stdcall StartConnect(int SettingComPort, int SelectModelType);
EG_API int __stdcall DetectConnect();
EG_API int __stdcall CloseConnect();
EG_API int __stdcall CurFirmwareVersion(int &Ver1, int &Ver2, int &Ver3);

EG_API double __stdcall CurrentPos();
EG_API void __stdcall IOStatus(unsigned int &InputData, unsigned int &OutputData);
EG_API bool __stdcall WorkState();
EG_API bool __stdcall HoldState();
EG_API int __stdcall AlarmState();

EG_API int __stdcall ResetMotion();
EG_API void __stdcall StopMotion();
EG_API int __stdcall RunMove(double MovPosition, int MovSpeed);
EG_API int __stdcall RunGrip(char Dir, int Str, char GriSpeed, char GriForce);
EG_API int __stdcall RunExpert(char Dir, double MovStr, int MovSpeed, double GriStr, int GriSpeed, int GriForce);

// Mutiple Gripper APIs
EG_API HEG __stdcall StartConnectMulti(int SettingComPort, int SelectModelType); // Return id or ErrorCode
EG_API int __stdcall DetectConnectMulti(HEG id); // Return ErrorCode
EG_API int __stdcall CloseConnectMulti(HEG id); // Return ErrorCode
EG_API int __stdcall CurFirmwareVersionMulti(HEG id, int &Ver1, int &Ver2, int &Ver3); // Return ErrorCode

EG_API double __stdcall CurrentPosMulti(HEG id, int &ErrorCode);
EG_API int __stdcall IOStatusMulti(HEG id, unsigned int &InputData, unsigned int &OutputData); // Return ErrorCode
EG_API bool __stdcall WorkStateMulti(HEG id, int &ErrorCode);
EG_API bool __stdcall HoldStateMulti(HEG id, int &ErrorCode);
EG_API int __stdcall AlarmStateMulti(HEG id); // Return ErrorCode

EG_API int __stdcall ResetMotionMulti(HEG id); // Return ErrorCode
EG_API int __stdcall StopMotionMulti(HEG id); // Return ErrorCode
EG_API int __stdcall RunMoveMulti(HEG id, double MovPosition, int MovSpeed); // Return ErrorCode
EG_API int __stdcall RunGripMulti(HEG id, char Dir, int Str, char GriSpeed, char GriForce); // Return ErrorCode
EG_API int __stdcall RunExpertMulti(HEG id, char Dir, double MovStr, int MovSpeed, double GriStr, int GriSpeed, int GriForce); // Return ErrorCode

#ifdef __cplusplus
}
#endif

#endif // EG_CONTROL_API_EG_CONTROL_API_H_
