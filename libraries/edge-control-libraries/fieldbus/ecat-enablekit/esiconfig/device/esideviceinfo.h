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
 * @file esideviceinfo.h
 * 
 */

#ifndef __ESI_DEVICEINFO_H__
#define __ESI_DEVICEINFO_H__

#include "../esicommon.h"

typedef struct {
	uint32_t RequestTimeout;
	uint32_t ResponseTimeout;
} esi_MailboxTimeout;

typedef struct {
	esi_MailboxTimeout timeout;
} esi_Mailbox;

typedef struct {
	esi_Mailbox mailbox;
} esi_InfoType;

void ecat_esi_parse_device_info(xmlNodePtr ptr, esi_InfoType* info);
#endif
