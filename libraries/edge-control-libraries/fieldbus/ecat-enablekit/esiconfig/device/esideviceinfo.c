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
 * @file esideviceinfo.c
 * 
 */


#include "esideviceinfo.h"

static void ecat_esi_parse_device_info_mailbox_timeout(xmlNodePtr ptr, esi_MailboxTimeout* timeout)
{
	if (!timeout) {
		return;
	}
	while (ptr != NULL) {
		if ((!xmlStrcmp(ptr->name, BAD_CAST"RequestTimeout"))) {
			xmlChar* key;
        	key = xmlNodeGetContent(ptr);
        	if (key) {
            	timeout->RequestTimeout = atoi((const char*)key);
            	xmlFree(key);
        	}
		}
		if ((!xmlStrcmp(ptr->name, BAD_CAST"ResponseTimeout"))) {
			xmlChar* key;
        	key = xmlNodeGetContent(ptr);
        	if (key) {
            	timeout->ResponseTimeout = atoi((const char*)key);
            	xmlFree(key);
        	}
		}
		ptr = ptr->next;
	}
}

static void ecat_esi_parse_device_info_mailbox(xmlNodePtr ptr, esi_Mailbox* mailbox)
{
	if (!mailbox) {
		return;
	}
	while (ptr != NULL) {
		if ((!xmlStrcmp(ptr->name, BAD_CAST"Timeout"))) {
			ecat_esi_parse_device_info_mailbox_timeout(ptr, &mailbox->timeout);
		}
		ptr = ptr->next;
	}
}

void ecat_esi_parse_device_info(xmlNodePtr ptr, esi_InfoType* info)
{
	if (!info) {
		return;
	}
	while (ptr != NULL) {
		if ((!xmlStrcmp(ptr->name, BAD_CAST"Mailbox"))) {
			ecat_esi_parse_device_info_mailbox(ptr, &info->mailbox);
		}
		ptr = ptr->next;
	}
}
