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
 * @file single_motor_vel.c
 * 
 */  

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <limits.h>
#include <pthread.h>
#include <sys/types.h>
#include <sys/mman.h>
#include <signal.h>
#include <motionentry.h>
#include <time.h>
#include <getopt.h>

#define CYCLE_US				(1000)
#define PERIOD_NS				(CYCLE_US*1000)
#define NSEC_PER_SEC			(1000000000L)
#define TIMESPEC2NS(T)          ((uint64_t) (T).tv_sec * NSEC_PER_SEC + (T).tv_nsec)
#define DIFF_NS(A,B)            (((B).tv_sec - (A).tv_sec)*NSEC_PER_SEC + ((B).tv_nsec)-(A).tv_nsec)
#define CYCLE_COUNTER_PERSEC	(NSEC_PER_SEC/PERIOD_NS)

static pthread_t cyclic_thread;
static pthread_t cyclic_thread1;
static volatile int run = 1;
static servo_master* masters = NULL;

static volatile int sem_update = 0;
int64_t latency_min_ns = 1000000, latency_max_ns = -1000000;

static char *eni_file;

#define POS_MODE

#define SLAVE00_POS   0,0
uint32_t controlword;
uint32_t targetpos;
uint32_t targetvel;
uint32_t statusword;
uint32_t actualpos;
uint32_t modesel;

#define PER_CIRCLE_ENCODER		(1<<23)
static double set_tar_vel = 1.0;

static uint16_t coe_cia402_statemachine(uint16_t status)
{
    if ((status&0x4F) == 0x0) {		// Not ready to Switch on
        return 0x80;
    } else if ((status&0x4F) == 0x40) { // Switch on Disabled
        return 0x6;
    } else if ((status&0x6F) == 0x21) { // Ready to Switch on
        return 0x7;
    } else if ((status&0x6F) == 0x23) { // Switch on
        return 0xF;
    } else if ((status&0x6F) == 0x27) { // Operation enabled
        return 0x1F;
    } else if ((status&0x6F) == 0x07) { // Quick stop active
        return 0x0;
    } else if ((status&0x4F) == 0x0F) { // Fault reaction active
        return 0x80;
    } else if ((status&0x4F) == 0x08) { // Fault
        return 0x80;
    }
    return 0x80;
}

void *my_thread(void *arg)
{
    struct timespec next_period, dc_period;
    servo_master* master = (servo_master*)arg;
    unsigned int cycle_count = 0;
    uint16_t control;
    uint32_t target;
    int64_t latency_ns = 0;
    void* tx_domain_sc;
    void* rx_domain_sc;
    uint8_t* tx_domain_pd_sc;
    uint8_t* rx_domain_pd_sc;

    struct sched_param param = {.sched_priority = 99};
    pthread_setschedparam(pthread_self(), SCHED_FIFO, &param);
    tx_domain_sc = motion_servo_get_tx_domain_by_slave(master->master, 0);
    rx_domain_sc = motion_servo_get_rx_domain_by_slave(master->master, 0);
    tx_domain_pd_sc = motion_servo_domain_data(tx_domain_sc);
    if (!tx_domain_pd_sc) {
        printf("fail to get tx domain data\n");
        return NULL;
    }
    rx_domain_pd_sc = motion_servo_domain_data(rx_domain_sc);
    if (!rx_domain_pd_sc) {
        printf("fail to get rx domain data\n");
        return NULL;
    }

    clock_gettime(CLOCK_MONOTONIC, &next_period);
    while(run){
        next_period.tv_nsec += CYCLE_US * 1000;
        while (next_period.tv_nsec >= NSEC_PER_SEC) {
            next_period.tv_nsec -= NSEC_PER_SEC;
            next_period.tv_sec++;
        }
        clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &next_period, NULL);
        cycle_count++;
        clock_gettime(CLOCK_MONOTONIC, &dc_period);
        latency_ns = DIFF_NS(next_period, dc_period);
        if (latency_ns > latency_max_ns) 
            latency_max_ns = latency_ns;
        if (latency_ns < latency_min_ns)
            latency_min_ns = latency_ns;
        if ((cycle_count%CYCLE_COUNTER_PERSEC)==0) {
            sem_update = 1;
        }
        motion_servo_recv_process(master->master, NULL);

        control = coe_cia402_statemachine(MOTION_DOMAIN_READ_U16(rx_domain_pd_sc + statusword));
        if (control == 0x1F) {
#ifdef POS_MODE
            target = MOTION_DOMAIN_READ_U32(rx_domain_pd_sc + actualpos);
            target += (uint32_t)((set_tar_vel*PER_CIRCLE_ENCODER)/CYCLE_COUNTER_PERSEC);
            MOTION_DOMAIN_WRITE_U32(tx_domain_pd_sc+targetpos, target);
#else
            target = set_tar_vel*PER_CIRCLE_ENCODER;
            MOTION_DOMAIN_WRITE_U32(tx_domain_pd_sc+targetvel, target);
#endif
        }
        MOTION_DOMAIN_WRITE_U16(tx_domain_pd_sc+controlword, control);

#ifdef POS_MODE
        MOTION_DOMAIN_WRITE_U8(tx_domain_pd_sc+modesel, MODE_CSP);
#else
        MOTION_DOMAIN_WRITE_U8(tx_domain_pd_sc+modesel, MODE_CSV);
#endif
        clock_gettime(CLOCK_MONOTONIC, &dc_period);
        motion_servo_sync_dc(master->master, TIMESPEC2NS(dc_period));
        motion_servo_send_process(master->master, NULL);
    }
    printf("latency:  %10.3f ... %10.3f\n", (float)latency_min_ns/1000, (float)latency_max_ns/1000);
    return NULL;
}

void signal_handler(int sig)
{
    run = 0;
}

static void getOptions(int argc, char**argv)
{
    int index;
    static struct option longOptions[] = {
        //name		has_arg				flag	val
        {"velocity",	required_argument,	NULL,	'v'},
        {"eni",	    required_argument,	NULL,	'n'},
        {"help",	no_argument,		NULL,	'h'},
        {}
    };
    do {
        index = getopt_long(argc, argv, "v:n:h", longOptions, NULL);
        switch(index){
            case 'v':
                set_tar_vel = atof(optarg);
                if (set_tar_vel > 50.0) {
                    set_tar_vel = 50.0;
                }
                printf("Velocity: %f circle per second \n", set_tar_vel);
                break;
            case 'n':
                if (eni_file) {
                    free(eni_file);
                    eni_file = NULL;
                }
                eni_file = malloc(strlen(optarg)+1);
                if (eni_file) {
                    memset(eni_file, 0, strlen(optarg)+1);
                    memmove(eni_file, optarg, strlen(optarg)+1);
                    printf("Using %s\n", eni_file);
                }
                break;
            case 'h':
                printf("Global options:\n");
                printf("    --velocity  -v  Set target velocity(circle/s). Max:50.0 \n");
                printf("    --eni       -n  Specify ENI/XML file\n");
                printf("    --help      -h  Show this help.\n");
                if (eni_file) {
                    free(eni_file);
                    eni_file = NULL;
                }
                exit(0);
                break;
        }
    } while(index != -1);
}

int main (int argc, char **argv)
{
    servo_master* master = NULL;
    servo_master* master1 = NULL;
    struct timespec dc_period;

    getOptions(argc, argv);
    signal(SIGTERM, signal_handler);
    signal(SIGINT, signal_handler);

    mlockall(MCL_CURRENT | MCL_FUTURE);

    /* Create master by ENI*/
    if (!eni_file) {
        printf("Error: Unspecify ENI/XML file\n");
        exit(0);
    }
    masters = motion_servo_master_create_v2(0);

    if (masters == NULL) {
        printf("%s:masters is NULL\n",eni_file);
        return -1;
    }

    master = motion_servo_master_request(masters, eni_file, 0);
    if (master == NULL) {
        return -1;
    }
    master1 = motion_servo_master_request(masters, eni_file, 1);
    if (master1 == NULL) {
        return -1;
    }
    free(eni_file);
    eni_file = NULL;
    motion_servo_set_multiple_domain_mode(master);
    motion_servo_set_multiple_domain_mode(master1);

    sleep(20);
    if (!motion_servo_driver_register_v2(master)) {
        goto End;
    }
    if (!motion_servo_driver_register_v2(master1)) {
        goto End;
    }

    motion_servo_set_send_interval(master);
    motion_servo_set_send_interval(master1);

    motion_servo_register_dc(master);
    motion_servo_register_dc(master1);
    clock_gettime(CLOCK_MONOTONIC, &dc_period);
    motion_master_set_application_time(master, TIMESPEC2NS(dc_period));
    motion_master_set_application_time(master1, TIMESPEC2NS(dc_period));

#ifdef POS_MODE
    motion_servo_set_mode(master, SLAVE00_POS, MODE_CSP);
    motion_servo_set_mode(master1, SLAVE00_POS, MODE_CSP);
#else
    motion_servo_set_mode(master, SLAVE00_POS, MODE_CSV);
    motion_servo_set_mode(master1, SLAVE00_POS, MODE_CSV);
#endif

    if (motion_servo_master_activate(master->master)) {
        printf("fail to activate master\n");
        goto End;
    }
    if (motion_servo_master_activate(master1->master)) {
        printf("fail to activate master\n");
        goto End;
    }

    statusword = motion_servo_get_rx_domain_offset(master->master, SLAVE00_POS, 0x6041, 0x00);
    if (statusword == DOMAIN_INVAILD_OFFSET)
    {
        goto End;
    }
    actualpos = motion_servo_get_rx_domain_offset(master->master, SLAVE00_POS, 0x6064, 0x00);
    if (actualpos == DOMAIN_INVAILD_OFFSET)
    {
        goto End;
    }
    controlword = motion_servo_get_tx_domain_offset(master->master, SLAVE00_POS, 0x6040, 0x00);
    if (controlword == DOMAIN_INVAILD_OFFSET)
    {
        goto End;
    }
    targetpos = motion_servo_get_tx_domain_offset(master->master, SLAVE00_POS, 0x607a, 0x00);
    if (targetpos == DOMAIN_INVAILD_OFFSET)
    {
        goto End;
    }
#ifndef POS_MODE
    targetvel = motion_servo_get_tx_domain_offset(master->master, SLAVE00_POS, 0x60FF, 0x00);
    if (targetvel == DOMAIN_INVAILD_OFFSET)
    {
        goto End;
    }
#endif
    modesel = motion_servo_get_tx_domain_offset(master->master, SLAVE00_POS, 0x6060, 0x00);
    if (modesel == DOMAIN_INVAILD_OFFSET)
    {
        goto End;
    }

    /* Create cyclic RT-thread */
    pthread_attr_t thattr;
    pthread_attr_init(&thattr);
    pthread_attr_setdetachstate(&thattr, PTHREAD_CREATE_JOINABLE);
    if (pthread_create(&cyclic_thread, &thattr, &my_thread, master)) {
        printf("pthread_create cyclic task failed\n");
        pthread_attr_destroy(&thattr);
        goto End;
    }
    if (pthread_create(&cyclic_thread1, &thattr, &my_thread, master1)) {
        printf("pthread_create cyclic task failed\n");
        pthread_attr_destroy(&thattr);
        goto End;
    }

    while (run) {
        //sched_yield();
        if (sem_update) {
            printf("latency:  %10.3f ... %10.3f\n", (float)latency_min_ns/1000, (float)latency_max_ns/1000);
            sem_update = 0;
        }
        //sleep(1);
    }

    pthread_join(cyclic_thread, NULL);
    pthread_join(cyclic_thread1, NULL);
    pthread_attr_destroy(&thattr);

    motion_servo_master_release(master);
    motion_servo_master_release(master1);
    return 0;
End:
    if (master1) {
        motion_servo_master_release(master1);
    }
    if (master) {
        motion_servo_master_release(master);
    }
    return -1;
}

