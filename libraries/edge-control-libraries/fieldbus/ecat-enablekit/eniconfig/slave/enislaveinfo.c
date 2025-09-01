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
 * @file enislaveinfo.c
 * 
 */

#include "enislaveinfo.h"

#define ENI_SLAVE_INFO_LOG "ENI_SLAVE_INFO"

/**
*@brief This function is responsible for parsing EtherCAT ENI slave information
*@param ptr is used to point at certain row of ENI file for parsing
*@param info is pointing at ENI slave info object to collect parsing results
*/

void ecat_eni_parse_slaveinfo(xmlNodePtr ptr, eni_slave_info* info)
{
    if (!info) {
        return;
    }

    while (ptr != NULL) {
        if (!xmlStrcmp(ptr->name, BAD_CAST"Name")) {
            xmlChar* key;
            key = xmlNodeGetContent(ptr);
            if (key) {                
                char len = strlen((const char*)key);
                if (info->name) {
                    ecat_free(info->name);
                }
                info->name = ecat_malloc(len+1);
                if (info->name) {
                    memset(info->name, 0, len+1);
                    memcpy(info->name, (const char*)key, len);
                }
                xmlFree(key);
            }
        }

        if (!xmlStrcmp(ptr->name, BAD_CAST"PhysAddr")) {
            xmlChar* id;
            id = xmlNodeGetContent(ptr);
            if (id) {
                info->physAddr = atoi((const char*)id);
                xmlFree(id);
            }
        }

        if(!xmlStrcmp(ptr->name, BAD_CAST"AutoIncAddr")){
            xmlChar* id;
            id = xmlNodeGetContent(ptr);
            if (id) {
                info->autoIncAddr = atoi((const char*)id);
                xmlFree(id);
            }
        }

        if(!xmlStrcmp(ptr->name, BAD_CAST"Identification")){
            //FIXME add identification and identification Ado later on
        }

        if(!xmlStrcmp(ptr->name, BAD_CAST"Physics")){
            //FIXME add physics layer on				
        }

        if(!xmlStrcmp(ptr->name, BAD_CAST"VendorId")){
            xmlChar* id;
            id = xmlNodeGetContent(ptr);
            if (id) {
                info->vendorId = atoi((const char*)id);
                xmlFree(id);
            }
        }

        if(!xmlStrcmp(ptr->name, BAD_CAST"ProductCode")){
            xmlChar* id;
            id = xmlNodeGetContent(ptr);
            if (id) {
                info->productCode = atoi((const char*)id);
                xmlFree(id);
            }
        }

        if(!xmlStrcmp(ptr->name, BAD_CAST"RevisionNo")){
            xmlChar* id;
            id = xmlNodeGetContent(ptr);
            if (id) {
                info->revisionNo = atoi((const char*)id);
                xmlFree(id);
            }
        }

        if(!xmlStrcmp(ptr->name, BAD_CAST"SerialNo")){
            xmlChar* id;
            id = xmlNodeGetContent(ptr);
            if (id) {
                info->serialNo = atoi((const char*)id);
                xmlFree(id);
            }
        }

        if(!xmlStrcmp(ptr->name, BAD_CAST"ProductRevision")){
             //FIXME add product revision later on            
        }

        ptr = ptr->next;
    }
}

void ecat_eni_free_slave_info(eni_slave_info* info)
{
    if (!info) {
        return;
    }
    if (info->name) {
        ecat_free(info->name);
        info->name = NULL;
    }
    if (info->identification) {
        ecat_free(info->identification);
        info->identification = NULL;
    }
    if (info->productRevision) {
        ecat_free(info->productRevision);
        info->productRevision = NULL;
    }
}

