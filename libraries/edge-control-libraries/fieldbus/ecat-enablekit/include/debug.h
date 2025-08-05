// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
// http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing,
// software distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions
// and limitations under the License.
/**
 * 
 * @file debug.h
 * 
 */

#ifndef __DEBUG_H__
#define __DEBUG_H__

#define CONSOLE_LEVEL 5
#if CONSOLE_LEVEL > 0
#define MOTION_CONSOLE_ERR printf
#else
#define MOTION_CONSOLE_ERR(fmt, argv...)
#endif
#if CONSOLE_LEVEL > 1
#define MOTION_CONSOLE_WARN printf
#else
#define MOTION_CONSOLE_WARN(fmt, argv...)
#endif
#if CONSOLE_LEVEL > 2
#define MOTION_CONSOLE_INFO printf
#else
#define MOTION_CONSOLE_INFO(fmt, argv...)
#endif
#if CONSOLE_LEVEL > 3
#define MOTION_CONSOLE_NOTICE printf
#else
#define MOTION_CONSOLE_NOTICE(fmt, argv...)
#endif
#if CONSOLE_LEVEL > 4
#define MOTION_CONSOLE_DEBUG printf
#else
#define MOTION_CONSOLE_DEBUG(fmt, argv...)
#endif

#endif
