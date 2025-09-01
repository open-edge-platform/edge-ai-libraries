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
 * @file motionentry.c
 * 
 */

#include <stdio.h>
#include <string.h>
#include <ctype.h>
#include <time.h>

#include "motionentry.h"
#include "motionutils.h"
#include "debug.h"
#include "../esiconfig/esiconfig.h"
#include "../eniconfig/eniconfig.h"

#include <ecrt.h>

#include <libxml/parser.h>
#include <libxml/tree.h>
#include <libxml/xmlmemory.h>

#define MOTIONENTRY_LOG "MOTION_ENTRY: "
#define SLAVE_PHYS_ADDR_OFFSET 1001

static void motion_slave_free_pdo(servo_pdo_info_t* pdo_info);
static void motion_slave_free_pdo_entry(servo_pdo_entry_info_t* entry_info);

int motion_servo_load_config(servo_master* servomaster, char* name)
{
    if (!servomaster) {
        MOTION_CONSOLE_ERR(MOTIONENTRY_LOG "motion master is NULL!\n");
        return ECAT_FAIL;
    }
    if (!name) {
        MOTION_CONSOLE_ERR(MOTIONENTRY_LOG "ENI/XML name is NULL!\n");
        return ECAT_FAIL;
    }

    servomaster->eni_info = (void*)ecat_load_eni(name);
    if (!servomaster->eni_info) {
        MOTION_CONSOLE_ERR(MOTIONENTRY_LOG "ENI/XML parser failed\n");
        return ECAT_FAIL;
    }
    return ECAT_OKAY;
}

servo_master* motion_servo_master_create(char* name)
{
    ecat_eni* info;
    MOTION_CONSOLE_INFO(MOTIONENTRY_LOG "Requesting master index 0:...\n");
    servo_master* servomaster = ecat_malloc(sizeof(servo_master));
    if (!servomaster){
        MOTION_CONSOLE_ERR(MOTIONENTRY_LOG "servo master alloc fail\n");
        return NULL;
    }
    memset(servomaster, 0, sizeof(servo_master));

    if (motion_servo_load_config(servomaster, name)) {
        goto Init_Fail;
    }

    if (!servomaster->eni_info) {
        MOTION_CONSOLE_ERR(MOTIONENTRY_LOG "ENI infomation is NULL\n");
        goto Init_Fail;
    }
    info = (ecat_eni*)servomaster->eni_info;

    servomaster->master = ecat_malloc(sizeof(servo_master_t));
    if (!servomaster->master) {
        MOTION_CONSOLE_ERR(MOTIONENTRY_LOG "servo master point alloc failed\n");
        goto Init_Master_Fail;
    }
    memset(servomaster->master, 0, sizeof(servo_master_t));

    servo_master_t* master = servomaster->master;
    master->master = ecrt_request_master(0);
    if (!master->master) {
        MOTION_CONSOLE_ERR(MOTIONENTRY_LOG "Requesting master index 0:Failed\n");
        goto Init_Master_Fail;
    }

    return servomaster;

Init_Master_Fail:
    if (info) {
        eni_config_free(info);
        info = NULL;
    }
Init_Fail:
    if (servomaster) {
        if (servomaster->master) {
            ecat_free(servomaster->master);
            servomaster->master = NULL;
        }
        ecat_free(servomaster);
        servomaster = NULL;
    }
    return NULL;
}

static uint32_t motion_servo_eni_slave_size(eni_config* info)
{
    uint32_t size = 0;
    eni_config_slave* slave = NULL;
    if (!info) {
        return 0;
    }

    if (list_empty(&info->slave_list)) {
        return 0;
    }

    list_for_each_entry(slave, &info->slave_list, list) {
        if (slave) {
            size++;
        }
    }
    return size;
}

static int motion_get_slave_syncs_pdo(ec_pdo_info_t* slave_pdos, eni_slave_processdata* processdata, uint8_t sm_id, uint32_t index)
{
    eni_slave_processdata_pdo* pdo_info;
    eni_entry_type* entry = NULL;
    ec_pdo_entry_info_t* entry_info;
    uint32_t loop = 0;
    if ((!slave_pdos)||(!processdata)) {
        return ECAT_FAIL;
    }

    pdo_info = ecat_get_pdo_info_by_index(processdata, sm_id, index);
    if (!pdo_info) {
        return ECAT_FAIL;
    }
    slave_pdos->index = index;
    slave_pdos->n_entries = ecat_eni_slave_entry_size(&pdo_info->pdo_type.entry_list);
    if (slave_pdos->n_entries == 0) {
        return ECAT_FAIL;
    }
    entry_info = (ec_pdo_entry_info_t*)ecat_malloc(sizeof(ec_pdo_entry_info_t)*slave_pdos->n_entries);
    if (!entry_info) {
        return ECAT_FAIL;
    }
    memset(entry_info, 0, sizeof(ec_pdo_entry_info_t)*slave_pdos->n_entries);
    list_for_each_entry(entry, &pdo_info->pdo_type.entry_list, list) {
        if (entry) {
            entry_info[loop].index = entry->index;
            entry_info[loop].subindex = entry->subindex;
            entry_info[loop].bit_length = entry->bitlen;
        }
        loop++;
        if (loop == slave_pdos->n_entries) {
            break;
        }
    }
    slave_pdos->entries = entry_info;
    return ECAT_OKAY;
}

static int motion_config_initial_slave_syncs(ec_sync_info_t* slave_syncs, uint32_t index)
{
    if (!slave_syncs) {
        return ECAT_FAIL;
    }
    slave_syncs->index = index;
    slave_syncs->dir = EC_DIR_OUTPUT;
    slave_syncs->n_pdos = 0;
    slave_syncs->pdos = NULL;
    slave_syncs->watchdog_mode = EC_WD_DEFAULT;
    return ECAT_OKAY;
}

static int motion_config_slave_syncs(ec_sync_info_t* slave_syncs, uint8_t index, eni_slave_processdata_sm* sm, eni_slave_processdata* processdata)
{
    uint32_t loop = 0;
    ec_pdo_info_t* slave_pdos;
    if (!slave_syncs) {
        return ECAT_FAIL;
    }
    if (sm) {
        if (sm->type == ENI_SM_INVAILD_TYPE) {
            motion_config_initial_slave_syncs(slave_syncs, index);
        } 
        else if (sm->type == ENI_SM_OUTPUTS_TYPE) {
            eni_slave_pdo_indices* pdo = NULL;
            slave_syncs->index = index;
            slave_syncs->dir = EC_DIR_OUTPUT;
            if(sm->watchdog) {
                if(*sm->watchdog > 0) {
                    slave_syncs->watchdog_mode = EC_WD_ENABLE;
                }
                else {
                    slave_syncs->watchdog_mode = EC_WD_DISABLE;
                }
            }
            else {
                slave_syncs->watchdog_mode = EC_WD_ENABLE;
            }
            slave_syncs->n_pdos = ecat_eni_slave_sm_pdolist_size(&sm->pdo_list);
            if (slave_syncs->n_pdos) {
                slave_pdos = (ec_pdo_info_t*)ecat_malloc(sizeof(ec_pdo_info_t)*slave_syncs->n_pdos);
                if (slave_pdos) {
                    memset(slave_pdos, 0, sizeof(ec_pdo_info_t));
                    list_for_each_entry(pdo, &sm->pdo_list, list) {
                        motion_get_slave_syncs_pdo(&slave_pdos[loop], processdata, index, pdo->index);
                        loop++;
                        if (loop == slave_syncs->n_pdos) {
                            break;
                        }
                    }
                    slave_syncs->pdos = slave_pdos;
                }
            } 
            else {
                slave_syncs->pdos = NULL;
            }
        } 
        else if (sm->type == ENI_SM_INPUTS_TYPE) {
            eni_slave_pdo_indices* pdo = NULL;
            slave_syncs->index = index;
            slave_syncs->dir = EC_DIR_INPUT;
            if(sm->watchdog) {
                if(*sm->watchdog > 0) {
                    slave_syncs->watchdog_mode = EC_WD_ENABLE;
                }
                else {
                    slave_syncs->watchdog_mode = EC_WD_DISABLE;
                }
            }
            else {
                slave_syncs->watchdog_mode = EC_WD_DISABLE;
            }
            slave_syncs->n_pdos = ecat_eni_slave_sm_pdolist_size(&sm->pdo_list);
            if (slave_syncs->n_pdos) {
                slave_pdos = (ec_pdo_info_t*)ecat_malloc(sizeof(ec_pdo_info_t)*slave_syncs->n_pdos);
                if (slave_pdos) {
                    memset(slave_pdos, 0, sizeof(ec_pdo_info_t));
                    list_for_each_entry(pdo, &sm->pdo_list, list) {
                        motion_get_slave_syncs_pdo(&slave_pdos[loop], processdata, index, pdo->index);
                        loop++;
                        if (loop == slave_syncs->n_pdos) {
                            break;
                        }
                    }
                    slave_syncs->pdos = slave_pdos;
                }
            } 
            else {
                slave_syncs->pdos = NULL;
            }
        }
    } 
    else {
        motion_config_initial_slave_syncs(slave_syncs, index);
    }
    return ECAT_OKAY;
}

static ec_sync_info_t* motion_get_slave_syncs(eni_config_slave* slave, uint32_t* n_sync)
{
    uint8_t sm_size;
    ec_sync_info_t* slave_syncs;
    eni_slave_processdata_sm* sm;
    uint32_t loop = 0;
    if ((!slave)||(!slave->processdata)) {
        return NULL;
    }

    sm_size = ecat_eni_slave_smlist_size(&slave->processdata->sm_list);
    if (sm_size == 0) {
        return NULL;
    }

    slave_syncs = (ec_sync_info_t*)ecat_malloc(sizeof(ec_sync_info_t)*(sm_size+1));
    if (!slave_syncs) {
          MOTION_CONSOLE_ERR(MOTIONENTRY_LOG "slave syncs malloc failed\n");
          return NULL;
    }
    memset(slave_syncs, 0, sizeof(ec_sync_info_t)*(sm_size+1));
    memset(&slave_syncs[sm_size], 0xff, sizeof(ec_sync_info_t));
    list_for_each_entry(sm, &slave->processdata->sm_list, list) {
        motion_config_slave_syncs(&slave_syncs[loop], loop, sm, slave->processdata);
        loop++;
    }
    if (n_sync) {
        *n_sync = loop;
    }
    return slave_syncs;
}

static int motion_get_pdo_entry_info(servo_pdo_entry_info_t* entry_info, eni_entry_type* eni_entry)
{
    if ((!entry_info)||(!eni_entry)) {
        return ECAT_FAIL;
    }

    entry_info->index = eni_entry->index;
    entry_info->subindex = eni_entry->subindex;
    entry_info->bit_length = eni_entry->bitlen;
    /* get pdo entry name*/
    if (!eni_entry->name.name) {
        return ECAT_FAIL;
    }
    char len = strlen(eni_entry->name.name);
    entry_info->name = ecat_malloc(len+1);
    if (entry_info->name) {
        memset(entry_info->name, 0, len+1);
        memcpy(entry_info->name, eni_entry->name.name, len);
    }
    return ECAT_OKAY;
}

static int motion_get_pdo_info(servo_pdo_info_t* pdo_info, eni_slave_processdata* processdata, uint8_t sm_id, uint32_t pdo_id)
{
    if ((!pdo_info)||(!processdata)) {
        return ECAT_FAIL;
    }

    eni_slave_processdata_pdo* eni_pdo_info;
    eni_entry_type* eni_entry = NULL;
    servo_pdo_entry_info_t* entry_info;
    uint32_t loop = 0;
    int ret = 0;

    /* get pdo info by sm index and pdo index */
    eni_pdo_info = ecat_get_pdo_info_by_index(processdata, sm_id, pdo_id);
    if (!eni_pdo_info) {
        return ECAT_FAIL;
    }
    /* get pdo name */
    if (!eni_pdo_info->pdo_type.name.name) {
        return ECAT_FAIL;
    }
    char len = strlen(eni_pdo_info->pdo_type.name.name);
    pdo_info->name = ecat_malloc(len+1);
    if (pdo_info->name) {
        memset(pdo_info->name, 0, len+1);
        memcpy(pdo_info->name, eni_pdo_info->pdo_type.name.name, len);
    }
    pdo_info->index = pdo_id;
    pdo_info->n_entries = ecat_eni_slave_entry_size(&eni_pdo_info->pdo_type.entry_list);
    if (pdo_info->n_entries == 0) {
        return ECAT_FAIL;
    }
    entry_info = (servo_pdo_entry_info_t*)ecat_malloc(sizeof(servo_pdo_entry_info_t)*pdo_info->n_entries);
    if (!entry_info) {
        return ECAT_FAIL;
    }
    memset(entry_info, 0, sizeof(servo_pdo_entry_info_t)*pdo_info->n_entries);
    /* loop all pdo entries*/
    list_for_each_entry(eni_entry, &eni_pdo_info->pdo_type.entry_list, list) {
        ret = motion_get_pdo_entry_info(&entry_info[loop], eni_entry);
        if(ret < 0) {
            motion_slave_free_pdo_entry(entry_info);
	    ecat_free(entry_info);
	    entry_info = NULL;
            return ECAT_FAIL;
        }
        loop++;
    }
    pdo_info->pdo_entry_info = entry_info;
    return ECAT_OKAY;
}

servo_pdo_info_t* motion_get_sm_pdo_info(eni_slave_processdata_sm* eni_sm, uint8_t sm_id, eni_slave_processdata* processdata, uint16_t n_pdos)
{
    if ((!eni_sm) || (!processdata)) {
        return NULL;
    }

    eni_slave_pdo_indices* eni_pdo_index = NULL;
    servo_pdo_info_t* pdo_info;
    uint32_t loop = 0;
    int ret = 0;
    
    if (n_pdos) {
        pdo_info = (servo_pdo_info_t*)ecat_malloc(sizeof(servo_pdo_info_t)*n_pdos);
        if (pdo_info) {
            memset(pdo_info, 0, sizeof(servo_pdo_info_t)*n_pdos);
            /* loop all pdos */
            list_for_each_entry(eni_pdo_index, &eni_sm->pdo_list, list) {
                ret = motion_get_pdo_info(&pdo_info[loop], processdata, sm_id, eni_pdo_index->index);
                if(ret < 0) {
                    for (int idx = loop; idx >= 0; idx--) {
                        motion_slave_free_pdo(&pdo_info[idx]);
                    }
                    ecat_free(pdo_info);
                    return NULL;
                }
                loop++;
            }
        }
    }
    else {
        pdo_info = NULL;
    }
    return pdo_info;
}


static int motion_get_sm_info(servo_sm_info_t* sm_info, eni_slave_processdata_sm* eni_sm, uint8_t sm_id, eni_slave_processdata* processdata)
{
    if ((!sm_info) || (!eni_sm) || (!processdata)) {
        return ECAT_FAIL;
    }

    if (eni_sm) {
        if (eni_sm->type == ENI_SM_INVAILD_TYPE) {
            sm_info->n_pdos = 0;
            sm_info->pdo_info = NULL;
            sm_info->sm_type = ENI_SM_INVAILD_TYPE;
        }
        else if (eni_sm->type == ENI_SM_OUTPUTS_TYPE) {
            sm_info->sm_type = ENI_SM_OUTPUTS_TYPE;
            sm_info->n_pdos = ecat_eni_slave_sm_pdolist_size(&eni_sm->pdo_list);
            sm_info->pdo_info = motion_get_sm_pdo_info(eni_sm, sm_id, processdata, sm_info->n_pdos);
        }
        else if (eni_sm->type == ENI_SM_INPUTS_TYPE) {
            sm_info->sm_type = ENI_SM_INPUTS_TYPE;
            sm_info->n_pdos = ecat_eni_slave_sm_pdolist_size(&eni_sm->pdo_list);
            sm_info->pdo_info = motion_get_sm_pdo_info(eni_sm, sm_id, processdata, sm_info->n_pdos);
        }
        else {
            return ECAT_FAIL;
        }
    }
    return ECAT_OKAY;
}

/* get slave info by index*/
servo_slave_info_t* motion_servo_get_slave_info(servo_master* master, uint32_t slave_index)
{
    if (!master) {
        MOTION_CONSOLE_ERR(MOTIONENTRY_LOG "no master is created\n");
        return NULL;
    }
    servo_slave_info_t* servo_slave_info;
    eni_config_slave* slave = NULL;
    eni_config* info;
    eni_slave_processdata_sm* eni_sm;
    servo_sm_info_t* sm_info;
    uint32_t* n_sync = 0;
    uint32_t slave_loop = 0, sm_loop = 0;
    int ret = 0;
    uint8_t sm_size;

    info = master->eni_info;
    if (list_empty(&info->slave_list)) {
        return NULL;
    }
    servo_slave_info = (servo_slave_info_t*)ecat_malloc(sizeof(servo_slave_info_t));
    if (!servo_slave_info) {
          MOTION_CONSOLE_ERR(MOTIONENTRY_LOG "slave info malloc failed\n");
          return NULL;
    }
    memset(servo_slave_info, 0, sizeof(servo_slave_info_t));

    list_for_each_entry(slave, &info->slave_list, list) {
        if(slave_loop == slave_index) {
            if (slave) {
                servo_slave_info->alias = 0;
                servo_slave_info->position = slave->info.physAddr-SLAVE_PHYS_ADDR_OFFSET;
                sm_size = ecat_eni_slave_smlist_size(&slave->processdata->sm_list);
                if (sm_size == 0) {
                    goto FailureParse;
                }
                servo_slave_info->sm_size = sm_size;
                servo_slave_info->sm_info = (servo_sm_info_t*)ecat_malloc(sizeof(servo_sm_info_t)*(sm_size));
                sm_info = servo_slave_info->sm_info;
                if (!sm_info) {
                    MOTION_CONSOLE_ERR(MOTIONENTRY_LOG "slave sm info malloc failed\n");
                    goto FailureParse;
                }
                memset(sm_info, 0, sizeof(servo_sm_info_t)*sm_size);
                /* loop all sm */
                list_for_each_entry(eni_sm, &slave->processdata->sm_list, list) {
                    sm_info->index = sm_loop;
                    ret = motion_get_sm_info(&sm_info[sm_loop], eni_sm, sm_loop, slave->processdata);
                    if(ret < 0) {
                        goto FailureParse;
                    }
                    sm_loop++;
                }
            }
            break;
        }
	slave_loop++;
    }
    return servo_slave_info;
FailureParse:
    if (servo_slave_info)
        motion_servo_free_slave_info(servo_slave_info);
    return NULL;
}

static void motion_slave_free_pdo_entry(servo_pdo_entry_info_t* entry_info)
{
    if(!entry_info) {
        return;
    }
    if(entry_info->name) {
        ecat_free(entry_info->name);
        entry_info->name = NULL;
    }
}

static void motion_slave_free_pdo(servo_pdo_info_t* pdo_info)
{
    if(!pdo_info) {
        return;
    }
    if(pdo_info->pdo_entry_info) {
        uint16_t idx;
        for (idx = pdo_info->n_entries; idx > 0; idx--) {
            motion_slave_free_pdo_entry(&pdo_info->pdo_entry_info[idx-1]);
        }
	ecat_free(pdo_info->pdo_entry_info);
	pdo_info->pdo_entry_info = NULL;
    }
    if(pdo_info->name) {
        ecat_free(pdo_info->name);
        pdo_info->name = NULL;
    }
}

static void motion_slave_free_sm(servo_sm_info_t* sm_info)
{
    if(!sm_info) {
        return;
    }
    if(sm_info->pdo_info) {
        uint16_t idx;
        for (idx = sm_info->n_pdos; idx > 0; idx-- ) {
            motion_slave_free_pdo(&sm_info->pdo_info[idx-1]);
        }
        if (sm_info->pdo_info) {
            ecat_free(sm_info->pdo_info);
            sm_info->pdo_info = NULL;
        }
    }
    ecat_free(sm_info);
    sm_info = NULL;
}

void motion_servo_free_slave_info(servo_slave_info_t* servo_slave_info)
{
    if(!servo_slave_info) {
        return;
    }
    if(servo_slave_info->sm_info) {
        motion_slave_free_sm(servo_slave_info->sm_info);
    }
    ecat_free(servo_slave_info);
    servo_slave_info = NULL;
}

static void motion_slave_sync_free_pdo_entries(ec_pdo_entry_info_t* entries)
{
    if (!entries) {
        return;
    }
    ecat_free(entries);
    entries = NULL;
}

static void motion_slave_sync_free_pdo(ec_pdo_info_t* info)
{
    if (!info) {
        return;
    }
    if (info->entries) {
        motion_slave_sync_free_pdo_entries(info->entries);
    }
    ecat_free(info);
    info = NULL;
}

static void motion_slave_free_syncs(ec_sync_info_t* slave_syncs)
{
    if (!slave_syncs) {
        return;
    }
    if (slave_syncs->pdos) {
        motion_slave_sync_free_pdo(slave_syncs->pdos);
    }
    ecat_free(slave_syncs);
    slave_syncs = NULL;
}

static int motion_slave_dump_slave_syncs(ec_sync_info_t* slave_syncs, uint8_t n_syncs)
{
    uint16_t loop;
    uint16_t index;
    ec_sync_info_t* sync_info;
    if (!slave_syncs) {
        MOTION_CONSOLE_ERR(MOTIONENTRY_LOG "slave syncs is Null\n");
        return ECAT_FAIL;
    }
    for (loop=0; loop < n_syncs; loop++) {
        sync_info = &slave_syncs[loop];
        if (sync_info->index == (uint8_t) EC_END) {
            break;
        }
        printf("|%2s|%2d\n","SM",sync_info->index);
        if (!sync_info->pdos) {
            printf("-n_pdo %4d|%8s\n", 0, "NULL");
            continue;
        }
        printf("-n_pdo %4d\n", sync_info->n_pdos);
        for (index=0; index < sync_info->n_pdos; index++) {
            uint16_t i;
            ec_pdo_info_t* pdos = &sync_info->pdos[index];
            printf("--pdo 0x%04x, entry_size %2d\n", pdos->index, pdos->n_entries);
            if (!pdos->entries) {
                continue;
            }
            for (i = 0; i < pdos->n_entries; i++) {
                ec_pdo_entry_info_t* entry;
                entry = &pdos->entries[i];
                printf("---entry: index 0x%04x, subindex %02d\n", entry->index, entry->subindex);
            }
        }
    }
    return ECAT_OKAY;
}

static ec_sync_info_t* motion_slave_pdo_remap(ec_slave_config_t* sc, eni_config_slave* slave, uint32_t* n_sync)
{
    ec_sync_info_t* slave_syncs;
    if (!sc) {
        MOTION_CONSOLE_ERR(MOTIONENTRY_LOG "slave config is Null\n");
        return NULL;
    }
    if (!slave) {
        MOTION_CONSOLE_ERR(MOTIONENTRY_LOG "slave device is Null\n");
        return NULL;
    }
    slave_syncs = motion_get_slave_syncs(slave, n_sync);
    //motion_slave_dump_slave_syncs(slave_syncs, EC_END);
    if (ecrt_slave_config_pdos(sc, EC_END, slave_syncs)) {
        MOTION_CONSOLE_ERR(MOTIONENTRY_LOG "Failed to configure PDOS\n");
    }
    return slave_syncs;
}

static int motion_servo_slave_config_register(servo_master_t* master, eni_config* info, ec_domain_t* domain, struct list_head* list)
{
    if ((!master)||(!info)||(!domain)||(!list)) {
        return ECAT_FAIL;
    }
    eni_config_slave* slave = NULL;
    uint32_t n_sync = 0;
    INIT_LIST_HEAD(&master->sc_list);
    if (list_empty(&info->slave_list)) {
        return ECAT_FAIL;
    }
    list_for_each_entry(slave, &info->slave_list, list) {
        servo_slave_t* slave_t;
        ec_sync_info_t* slave_syncs;
        if (slave) {
            slave_t = (servo_slave_t*)ecat_malloc(sizeof(servo_slave_t));
            if (slave_t) {
                uint32_t loop;
                memset(slave_t, 0, sizeof(servo_slave_t));
                INIT_LIST_HEAD(&slave_t->list);
                slave_t->sc = ecrt_master_slave_config(master->master, 0, slave->info.physAddr-SLAVE_PHYS_ADDR_OFFSET, \
                    slave->info.vendorId, slave->info.productCode);
                list_add_tail(&slave_t->list, &master->sc_list);
                slave_syncs = motion_slave_pdo_remap(slave_t->sc, slave, &n_sync);
                /* Configure register for PDO entries */
                if (slave_syncs) {
                    uint32_t idx;
                    for (idx = 0; idx < n_sync; idx++) {
                        ec_sync_info_t* sync = &slave_syncs[idx];
                        if (sync->pdos) {
                            for (loop = 0; loop < sync->n_pdos; loop++) {
                                uint32_t index;
                                ec_pdo_info_t pdos = sync->pdos[loop];
                                if (!pdos.entries) {
                                    continue;
                                }
                                for (index = 0; index < pdos.n_entries; index++) {
                                    ecat_pdo_entries* entry;
                                    entry = (ecat_pdo_entries*)ecat_malloc(sizeof(ecat_pdo_entries));
                                    if (entry) {
                                        memset(entry, 0, sizeof(ecat_pdo_entries));
                                        entry->entry.alias = 0;
                                        entry->entry.position = slave->info.physAddr-SLAVE_PHYS_ADDR_OFFSET;
                                        INIT_LIST_HEAD(&entry->list);
                                        entry->entry.index = pdos.entries[index].index;
                                        entry->entry.subindex = pdos.entries[index].subindex;
                                        entry->offset = ecrt_slave_config_reg_pdo_entry(slave_t->sc, \
                                            entry->entry.index, entry->entry.subindex, domain, NULL);
                                        list_add_tail(&entry->list, list);
                                    }
                                }
                            }
                        }
                    }
                    motion_slave_free_syncs(slave_syncs);
                }
            }
        }
    }
    return ECAT_OKAY;
}

static servo_slave_t* motion_servo_get_slave_by_index(servo_master_t* master, uint32_t index)
{
    if (!master) {
        return NULL;
    }
    if (list_empty(&master->sc_list)) {
        return NULL;
    }
    servo_slave_t* slave = NULL;
    uint32_t loop = 0;
    list_for_each_entry(slave, &master->sc_list, list) {
        if (loop == index) {
            return slave;
        }
        loop++;
    }
    return NULL;
}

servo_master_t* motion_servo_driver_register(servo_master* servomaster, void* domain)
{
    servo_master_t* master;
    int n_slave;
    MOTION_CONSOLE_INFO(MOTIONENTRY_LOG "Register servo driver...\n");
    if ((!servomaster)||(!servomaster->master)) {
        MOTION_CONSOLE_ERR(MOTIONENTRY_LOG "master have not requested\n");
        return NULL;
    }
    /* Create configuration for bus coupler */
    if (!servomaster->eni_info) {
        MOTION_CONSOLE_ERR(MOTIONENTRY_LOG "ENI/XML info is Null\n");
        return NULL;
    }
    eni_config* info = (eni_config*)servomaster->eni_info;

    master = servomaster->master;
    if (!master) {
        MOTION_CONSOLE_ERR(MOTIONENTRY_LOG "master id cannot be found in servomaster\n");
        return NULL;
    }
    master->domain = (ecat_domain*)ecat_malloc(sizeof(ecat_domain));
    if (!master->domain) {
        return NULL;
    }
    memset(master->domain, 0, sizeof(ecat_domain));
    INIT_LIST_HEAD(&master->domain->pdo_list);

    /* Create configuration for bus coupler */
    motion_servo_slave_config_register(master, info, (ec_domain_t*)domain, &master->domain->pdo_list);

    n_slave = motion_servo_eni_slave_size(info);
    if (n_slave == 0) {
        MOTION_CONSOLE_ERR(MOTIONENTRY_LOG "no slaves are found in servomaster\n");
        return master;
    }

    return master;
}

int motion_servo_domain_entry_register(servo_master* servomaster, void** domain)
{
    servo_master_t *master;
    MOTION_CONSOLE_INFO(MOTIONENTRY_LOG "Creating domain...\n");
    if ((!servomaster)||(!servomaster->master)) {
        MOTION_CONSOLE_ERR(MOTIONENTRY_LOG "master have not requested\n");
        return ECAT_FAIL;
    }
    if (!domain) {
        MOTION_CONSOLE_ERR(MOTIONENTRY_LOG "domain point is NULL\n");
        return ECAT_FAIL;
    }
    master = servomaster->master;
    if (!master) {
        MOTION_CONSOLE_ERR(MOTIONENTRY_LOG "master cannot be found in servomaster\n");
        return ECAT_FAIL;
    }

    *domain = (void*)ecrt_master_create_domain(master->master);
    if (!(*domain)) {
        MOTION_CONSOLE_ERR(MOTIONENTRY_LOG "Domain create fail\n");
        return ECAT_FAIL;
    }
    return ECAT_OKAY;
}

int motion_servo_slave_config_sdo8(servo_master* servomaster, uint16_t alias, uint16_t position, uint16_t sdo_index, uint8_t sdo_subindex, uint8_t value)
{
    servo_slave_t* slave_sc;
    if ((!servomaster)||(!servomaster->master)) {
        MOTION_CONSOLE_ERR("master have not requested\n");
        return ECAT_FAIL;
    }
    slave_sc = motion_servo_get_slave_by_index(servomaster->master, position);
    if (slave_sc) {
        if (slave_sc->sc) {
            return ecrt_slave_config_sdo8(slave_sc->sc, sdo_index, sdo_subindex, value);
        }
    }
    return ECAT_FAIL;
}

int motion_servo_slave_config_sdo16(servo_master* servomaster, uint16_t alias, uint16_t position, uint16_t sdo_index, uint8_t sdo_subindex, uint16_t value)
{
    servo_slave_t* slave_sc;
    if ((!servomaster)||(!servomaster->master)) {
        MOTION_CONSOLE_ERR("master have not requested\n");
        return ECAT_FAIL;
    }
    slave_sc = motion_servo_get_slave_by_index(servomaster->master, position);
    if (slave_sc) {
        if (slave_sc->sc) {
            return ecrt_slave_config_sdo16(slave_sc->sc, sdo_index, sdo_subindex, value);
        }
    }
    return ECAT_FAIL;
}

int motion_servo_slave_config_sdo32(servo_master* servomaster, uint16_t alias, uint16_t position, uint16_t sdo_index, uint8_t sdo_subindex, uint32_t value)
{
    servo_slave_t* slave_sc;
    if ((!servomaster)||(!servomaster->master)) {
        MOTION_CONSOLE_ERR("master have not requested\n");
        return ECAT_FAIL;
    }
    slave_sc = motion_servo_get_slave_by_index(servomaster->master, position);
    if (slave_sc) {
        if (slave_sc->sc) {
            return ecrt_slave_config_sdo32(slave_sc->sc, sdo_index, sdo_subindex, value);
        }
    }
    return ECAT_FAIL;
}

int motion_servo_slave_config_idn(servo_master* servomaster, uint16_t alias, uint16_t position, uint8_t drv_no, uint16_t idn, const uint8_t *data, size_t size)
{
    servo_slave_t* slave_sc;
    if ((!servomaster)||(!servomaster->master)) {
        MOTION_CONSOLE_ERR("master have not requested\n");
        return ECAT_FAIL;
    }
    slave_sc = motion_servo_get_slave_by_index(servomaster->master, position);
    if (slave_sc) {
        if (slave_sc->sc) {
            return ecrt_slave_config_idn(slave_sc->sc, drv_no, idn, EC_AL_STATE_PREOP, data, size);
        }
    }
    return ECAT_FAIL;
}


int motion_servo_recv_process(servo_master_t* master, void* domain)
{
    if (!master) {
        MOTION_CONSOLE_ERR(MOTIONENTRY_LOG "no master is created\n");
        return ECAT_FAIL;
    }
    if (!domain) {
        MOTION_CONSOLE_ERR(MOTIONENTRY_LOG "domain have not created\n");
        return ECAT_FAIL;
    }

    ecrt_master_receive(master->master);
    ecrt_domain_process(domain);
    return ECAT_OKAY;
}

int motion_servo_send_process(servo_master_t* master, void* domain)
{
    if (!master) {
        MOTION_CONSOLE_ERR(MOTIONENTRY_LOG "no master is created\n");
        return ECAT_FAIL;
    }
    if (!domain) {
        MOTION_CONSOLE_ERR(MOTIONENTRY_LOG "domain have not created\n");
        return ECAT_FAIL;
    }

    ecrt_domain_queue(domain);
    ecrt_master_send(master->master);
    return ECAT_OKAY;
}

uint32_t motion_servo_sync_monitor_process(servo_master_t *master)
{
    if (!master) {
        MOTION_CONSOLE_ERR(MOTIONENTRY_LOG "no master is created\n");
        return DC_INVAILD_OFFSET;
    }
    return ecrt_master_sync_monitor_process(master->master);
}

int motion_servo_get_domain_state(void* domain, servo_domain_state_t* domain_state)
{
    if (!domain) {
        MOTION_CONSOLE_ERR(MOTIONENTRY_LOG "domain have not created\n");
        return ECAT_FAIL;
    }
    if (!domain_state) {
        return ECAT_FAIL;
    }
    ecrt_domain_state(domain, &domain_state->d_state);
    return ECAT_OKAY;
}

int motion_servo_get_master_state(servo_master_t *master, servo_master_state_t* master_state)
{
    if (!master) {
        MOTION_CONSOLE_ERR(MOTIONENTRY_LOG "no master is created\n");
        return ECAT_FAIL;
    }
    if (!master_state) {
        return ECAT_FAIL;
    }
    ecrt_master_state(master->master, &master_state->m_state);
    return ECAT_OKAY;
}

uint8_t* motion_servo_domain_data(void* domain)
{
    if (!domain) {
        return NULL;
    }
    return ecrt_domain_data(domain);
}

uint32_t motion_servo_domain_size(void* domain)
{
    if (!domain) {
        return 0;
    }
    return ecrt_domain_size(domain);
}

uint32_t motion_servo_get_domain_offset(servo_master_t* master, uint16_t alias, uint16_t position, uint16_t index, uint8_t subindex)
{
    if (!master) {
        MOTION_CONSOLE_ERR(MOTIONENTRY_LOG "no master is created\n");
        return DOMAIN_INVAILD_OFFSET;
    }
    if (!master->domain) {
        MOTION_CONSOLE_ERR(MOTIONENTRY_LOG "domain have not created\n");
        return DOMAIN_INVAILD_OFFSET;
    }

    ecat_pdo_entries* entry = NULL;
    list_for_each_entry(entry, &master->domain->pdo_list, list) {
        if (entry) {
            if ((entry->entry.alias == alias) && (entry->entry.position == position) \
                && (entry->entry.index == index) && (entry->entry.subindex == subindex)) {
                return entry->offset;
            }
        }
    }
    MOTION_CONSOLE_ERR(MOTIONENTRY_LOG "The offset of PDO 0x%04X:0x%02x cannot been found\n", index, subindex);
    return DOMAIN_INVAILD_OFFSET;
}

int motion_servo_set_mode(servo_master* servomaster, uint16_t alias, uint16_t position, unsigned char mode)
{
    servo_slave_t* slave_sc;
    if ((!servomaster)||(!servomaster->master)) {
        MOTION_CONSOLE_ERR("master have not requested\n");
        return ECAT_FAIL;
    }
    slave_sc = motion_servo_get_slave_by_index(servomaster->master, position);
    if (slave_sc) {
        if (slave_sc->sc) {
            return ecrt_slave_config_sdo8(slave_sc->sc, 0x6060, 0x00, mode);
        }
    }
    return ECAT_FAIL;
}

uint32_t motion_servo_get_cyclic_cycletime(servo_master* servomaster)
{
    ecat_eni* info;
    if ((!servomaster)||(servomaster->master)) {
        return 0;
    }

    info = (ecat_eni*)servomaster->eni_info;
    if (info) {
        return ecat_eni_get_cycletime(&info->config);
    } else {
        return 0;
    }
}

int motion_servo_set_send_interval_with_time(servo_master* servomaster, unsigned int send_interval)
{
    MOTION_CONSOLE_INFO("Motion register send interval time...\n");
    if ((!servomaster)||(!servomaster->master)) {
        MOTION_CONSOLE_ERR("master have not requested\n");
        return ECAT_FAIL;
    }
    ecrt_master_set_send_interval(servomaster->master->master, send_interval);
    return ECAT_OKAY;
}

int motion_servo_set_send_interval(servo_master* servomaster)
{
    uint32_t cycle;
    ecat_eni* eni;
    if ((!servomaster)||(!servomaster->master)) {
        MOTION_CONSOLE_ERR("master have not requested\n");
        return ECAT_FAIL;
    }
    eni = (ecat_eni*)servomaster->eni_info;
    if (!eni) {
        return ECAT_FAIL;
    }
    cycle = ecat_eni_get_cycletime(&eni->config);
    if (cycle == 0) {
        cycle = MOTION_DEFAULT_CYCLIC_US_TIME;   //set default cycle time to 1ms
    }
    ecrt_master_set_send_interval(servomaster->master->master, cycle);
    return ECAT_OKAY;
}

int motion_master_set_application_time(servo_master* servomaster, uint64_t time)
{
    if ((!servomaster)||(!servomaster->master)) {
        MOTION_CONSOLE_ERR("master have not requested\n");
        return ECAT_FAIL;
    }
    ecrt_master_application_time(servomaster->master->master, time);
    return ECAT_OKAY;
}

int motion_servo_register_dc(servo_master* servomaster)
{
    if ((!servomaster)||(!servomaster->master)) {
        MOTION_CONSOLE_ERR("master have not requested\n");
        return ECAT_FAIL;
    }
    ecat_eni* info;
    eni_config_slave* slave = NULL;
    uint32_t loop = 0;
    uint16_t assign_activate = 0x0300;

    info = (ecat_eni*)servomaster->eni_info;
    if (!info) {
        return ECAT_FAIL;
    }

    if (list_empty(&info->config.slave_list)) {
        return ECAT_FAIL;
    }
    list_for_each_entry(slave, &info->config.slave_list, list) {
        if (slave) {
            servo_slave_t* slave_sc = motion_servo_get_slave_by_index(servomaster->master, loop);
            if (slave->dc) {
                if (slave->dc->referenceClock) {
                    if (slave_sc) {
                        ecrt_master_select_reference_clock(servomaster->master->master, slave_sc->sc);
                    }
                }
                if ((slave->dc->cycleTime0)&&(*(slave->dc->cycleTime0) != 0)) {
                    if (slave->dc->cycleTime1) {
                        if(*(slave->dc->cycleTime1) != 0) {
                            assign_activate = 0x700;
                        }
                    }
                    if (slave_sc) {
                        ecrt_slave_config_dc(slave_sc->sc, assign_activate, *(slave->dc->cycleTime0),(*(slave->dc->cycleTime0))/2, 0, 0);
                    }
                }
            }
        }
        loop++;
    }
    return ECAT_OKAY;
}

int motion_servo_sync_dc(servo_master_t* servomaster, uint64_t time)
{
    if ((!servomaster)||(!servomaster->master)) {
        MOTION_CONSOLE_ERR("master have not requested\n");
        return ECAT_FAIL;
    }
    ecrt_master_application_time(servomaster->master, time);
    ecrt_master_sync_reference_clock(servomaster->master);
    ecrt_master_sync_slave_clocks(servomaster->master);
    ecrt_master_sync_monitor_queue(servomaster->master);
    return ECAT_OKAY;
}

int motion_servo_master_activate(servo_master_t* servomaster)
{
    if ((!servomaster)||(!servomaster->master)){
        MOTION_CONSOLE_ERR("master have not requested\n");
        return ECAT_FAIL;
    }

    MOTION_CONSOLE_INFO("Activating master...\n");
    if(ecrt_master_activate(servomaster->master)) {
        return ECAT_FAIL;
    }
    return ECAT_OKAY;
}

static int motion_servo_free_ecat_domain(ecat_domain* domain)
{
    if (!domain) {
        return ECAT_FAIL;
    }

    ecat_pdo_entries* entry = NULL;
    ecat_pdo_entries* next = NULL;
    list_for_each_entry_safe(entry, next, &domain->pdo_list, list) {
        if (entry) {
            list_del(&entry->list);
            ecat_free(entry);
            entry = NULL;
        }
    }
    return ECAT_OKAY;
}

static int motion_servo_free_sc_list(struct list_head* list)
{
    if (!list) {
        return ECAT_FAIL;
    }

    servo_slave_t* slave = NULL;
    servo_slave_t* next = NULL;
    list_for_each_entry_safe(slave, next, list, list) {
        if (slave) {
            list_del(&slave->list);
            if (slave->sc) {
                ecat_free(slave->sc);
                slave->sc = NULL;
            }
            ecat_free(slave);
            slave = NULL;
        }
    }
    return ECAT_OKAY;
}

int motion_servo_master_release(servo_master* servomaster)
{
    if ((!servomaster)||(!servomaster->master)) {
        MOTION_CONSOLE_ERR("master have not requested\n");
        return ECAT_FAIL;
    }
    if (servomaster->eni_info) {
        eni_config_free((ecat_eni*)servomaster->eni_info);
        servomaster->eni_info = NULL;
    }
    ecrt_release_master(servomaster->master->master);
    if (servomaster->master->domain) {
        motion_servo_free_ecat_domain(servomaster->master->domain);
        ecat_free(servomaster->master->domain);
        servomaster->master->domain = NULL;
    }
    motion_servo_free_sc_list(&servomaster->master->sc_list);
    ecat_free(servomaster->master);
    servomaster->master = NULL;
    ecat_free(servomaster);
    servomaster = NULL;
    return ECAT_OKAY;
}

void test_console(void)
{
    //MOTION_CONSOLE_ERR("motion library console test pass!\n");
}
