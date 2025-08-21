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
 * @file motionentry.h
 * 
 */

#ifndef __MOTION_ENTRY_H__
#define __MOTION_ENTRY_H__

#ifdef __cplusplus
extern "C" {
#endif

#include <ecrt.h>

#ifndef NSEC_PER_SEC
#define NSEC_PER_SEC        (1000000000L)
#endif
#ifndef TIMESPEC2NS
#define TIMESPEC2NS(T)      ((uint64_t) (T).tv_sec * NSEC_PER_SEC + (T).tv_nsec)
#endif
#ifndef DIFF_NS
#define DIFF_NS(A,B)        (((B).tv_sec - (A).tv_sec)*NSEC_PER_SEC + ((B).tv_nsec)-(A).tv_nsec)
#endif

#define DOMAIN_INVAILD_OFFSET	(0xFFFFFFFF)
#define DC_INVAILD_OFFSET	(0xFFFFFFFF)


#define MOTION_DEFAULT_CYCLIC_US_TIME	(1000)
#define ECAT_FAIL   -1
#define ECAT_OKAY   0


enum{
    MODE_PP		= 1,
    MODE_PV		= 3,
    MODE_PT		= 4,
    MODE_NULL	= 5,
    MODE_HM		= 6,
    MODE_IP		= 7,
    MODE_CSP	= 8,
    MODE_CSV	= 9,
    MODE_CST	= 10
};

struct list_head {
    struct list_head *next;
    struct list_head *prev;
};

typedef struct {
    struct list_head list;  /**< EtherCAT slave list */
    ec_slave_config_t* sc;  /**< EtherCAT slave configuration */
} servo_slave_t;

typedef struct {
    uint16_t alias; /**< Slave alias address. */
    uint16_t position; /**< Slave position. */
    uint16_t index; /**< PDO entry index. */
    uint8_t subindex; /**< PDO entry subindex. */
} ecat_pdo_entry_reg_t;

typedef struct {
    struct list_head list; /**< EtherCAT slave  list */
    ecat_pdo_entry_reg_t entry; /**< EtherCAT slave pdo entry register list */
    int offset;
} ecat_pdo_entries;

typedef struct{
    uint16_t index; /**< PDO entry index. */
    uint8_t subindex; /**< PDO entry subindex. */
    uint8_t bit_length; /**< Size of the PDO entry in bit. */
    uint8_t* name;
}servo_pdo_entry_info_t;

typedef struct{
    servo_pdo_entry_info_t* pdo_entry_info;
    uint16_t index;
    uint16_t n_entries;
    uint8_t* name;
}servo_pdo_info_t;

typedef struct{
    servo_pdo_info_t* pdo_info;
    uint16_t n_pdos;
    uint8_t index;
    uint8_t sm_type; /* 0: INVAILD_TYPE, 1: OUTPUTS_TYPE, 2: INPUTS_TYPE */
}servo_sm_info_t;

typedef struct{
    servo_sm_info_t* sm_info;
    uint16_t alias;
    uint16_t position;
    uint8_t sm_size;
}servo_slave_info_t;

typedef struct {
    struct list_head pdo_list;
} ecat_domain;

typedef struct{
    ec_domain_state_t d_state;
}servo_domain_state_t;

typedef struct{
    ec_master_state_t m_state;
}servo_master_state_t;

typedef struct{
    ec_master_t* master;
    ecat_domain* domain;
    struct list_head sc_list;
} servo_master_t;

typedef struct{
    void* eni_info;
    servo_master_t* master;
} servo_master;

#define MOTION_DOMAIN_READ_U8(data) EC_READ_U8(data)
#define MOTION_DOMAIN_READ_S8(data) EC_READ_S8(data)
#define MOTION_DOMAIN_READ_U16(data) EC_READ_U16(data)
#define MOTION_DOMAIN_READ_S16(data) EC_READ_S16(data)
#define MOTION_DOMAIN_READ_U32(data) EC_READ_U32(data)
#define MOTION_DOMAIN_READ_S32(data) EC_READ_S32(data)
#define MOTION_DOMAIN_READ_U64(data) EC_READ_U64(data)
#define MOTION_DOMAIN_READ_S64(data) EC_READ_S64(data)

#define MOTION_DOMAIN_WRITE_U8(data, val) EC_WRITE_U8(data, val)
#define MOTION_DOMAIN_WRITE_S8(data, val) EC_WRITE_S8(data, val)
#define MOTION_DOMAIN_WRITE_U16(data, val) EC_WRITE_U16(data, val)
#define MOTION_DOMAIN_WRITE_S16(data, val) EC_WRITE_S16(data, val)
#define MOTION_DOMAIN_WRITE_U32(data, val) EC_WRITE_U32(data, val)
#define MOTION_DOMAIN_WRITE_S32(data, val) EC_WRITE_S32(data, val)
#define MOTION_DOMAIN_WRITE_U64(data, val) EC_WRITE_U64(data, val)
#define MOTION_DOMAIN_WRITE_S64(data, val) EC_WRITE_S64(data, val)

int motion_servo_load_config(servo_master* servomaster,char* name);
servo_master* motion_servo_master_create(char* name);
servo_master_t* motion_servo_driver_register(servo_master* servomaster, void* domain);
int motion_servo_domain_entry_register(servo_master* servomaster, void** domain);

int motion_servo_slave_config_sdo8(servo_master* servomaster, uint16_t alias, uint16_t position, uint16_t sdo_index, uint8_t sdo_subindex, uint8_t value);
int motion_servo_slave_config_sdo16(servo_master* servomaster, uint16_t alias, uint16_t position, uint16_t sdo_index, uint8_t sdo_subindex, uint16_t value);
int motion_servo_slave_config_sdo32(servo_master* servomaster, uint16_t alias, uint16_t position, uint16_t sdo_index, uint8_t sdo_subindex, uint32_t value);
int motion_servo_slave_config_idn(servo_master* servomaster, uint16_t alias, uint16_t position, uint8_t drv_no, uint16_t idn, const uint8_t *data, size_t size);

int motion_servo_recv_process(servo_master_t* master, void* domain);
int motion_servo_send_process(servo_master_t* master, void* domain);
uint32_t motion_servo_sync_monitor_process(servo_master_t* master);
int motion_servo_get_domain_state(void* domain, servo_domain_state_t* domain_state);
int motion_servo_get_master_state(servo_master_t *master, servo_master_state_t* master_state);
uint8_t* motion_servo_domain_data(void* domain);
uint32_t motion_servo_domain_size(void* domain);
uint32_t motion_servo_get_domain_offset(servo_master_t* master, uint16_t alias, uint16_t position, uint16_t index, uint8_t subindex);
int motion_servo_master_activate(servo_master_t* servomaster);
int motion_servo_master_release(servo_master* servomaster);

int motion_servo_set_mode(servo_master* servomaster, uint16_t alias, uint16_t position, unsigned char mode);
int motion_servo_set_send_interval_with_time(servo_master* master, unsigned int send_interval);
int motion_servo_set_send_interval(servo_master* servomaster);
int motion_servo_register_dc(servo_master* servomaster);
int motion_servo_sync_dc(servo_master_t* servomaster, uint64_t time);
uint32_t motion_servo_get_cyclic_cycletime(servo_master* servomaster);
int motion_master_set_application_time(servo_master* servomaster, uint64_t time);
servo_slave_info_t* motion_servo_get_slave_info(servo_master* master, uint32_t slave_index);
void motion_servo_free_slave_info(servo_slave_info_t* servo_slave_info);

void test_console(void);

#ifdef __cplusplus
}
#endif

#endif
