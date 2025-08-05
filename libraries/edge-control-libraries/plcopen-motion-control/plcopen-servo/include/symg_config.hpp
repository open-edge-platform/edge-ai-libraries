// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

#pragma once

#include "ecrt.h"
#include <stdio.h>

#define CYCLE_US 1000
#define PERIOD_NS (CYCLE_US * 1000)
#define NSEC_PER_SEC (1000000000L)
#define TIMESPEC2NS(T) ((uint64_t)(T).tv_sec * NSEC_PER_SEC + (T).tv_nsec)

#define SLAVE00_POS 0, 0
#define SLAVE00_ID 0x00008818, 0x00001170
#define PER_CIRCLE_ENCODER 13798

typedef enum
{
  MODE_PP   = 1,
  MODE_PV   = 3,
  MODE_PT   = 4,
  MODE_NULL = 5,
  MODE_HM   = 6,
  MODE_IP   = 7,
  MODE_CSP  = 8,
  MODE_CSV  = 9,
  MODE_CST  = 10
} Mode;

typedef enum
{
  UL = 1,
  UR = 2,
  LL = 3,
  LR = 4
} Wheel_Id;

typedef struct
{
  ec_slave_config_t* sc;
  unsigned int control;
  unsigned int speed1;
  unsigned int speed2;
  unsigned int speed3;
  unsigned int speed4;
  unsigned int pio_out;
  unsigned int status;
  unsigned int enc1;
  unsigned int enc2;
  unsigned int enc3;
  unsigned int enc4;
  unsigned int pio_in;
} Slave_Data;

typedef struct
{
  unsigned int ctl;
  int spd1;
  int spd2;
  int spd3;
  int spd4;
  unsigned int po_out;
  unsigned int stat;
  unsigned int en1;
  unsigned int en2;
  unsigned int en3;
  unsigned int en4;
  unsigned int po_in;
} Ctrl_Data;

extern ec_pdo_entry_info_t slave_pdo_entries[];

extern ec_pdo_info_t slave_pdos[];

extern ec_sync_info_t slave_syncs[];
