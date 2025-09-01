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
#include <ecrt.h>
#include <getopt.h>


#define CYCLE_US				(1000)
#define PERIOD_NS				(CYCLE_US*1000)
#define NSEC_PER_SEC			(1000000000L)
#define TIMESPEC2NS(T)          ((uint64_t) (T).tv_sec * NSEC_PER_SEC + (T).tv_nsec)
#define DIFF_NS(A,B)            (((B).tv_sec - (A).tv_sec)*NSEC_PER_SEC + ((B).tv_nsec)-(A).tv_nsec)
#define CYCLE_COUNTER_PERSEC	(NSEC_PER_SEC/PERIOD_NS)

static pthread_t cyclic_thread;
static volatile int run = 1;
static servo_master* master = NULL;
static uint8_t* domain1;
void* domain;
static uint32_t domain_size;

static volatile int sem_update = 0;
int64_t latency_min_ns = 1000000, latency_max_ns = -1000000;

static char *eni_file;

#define POS_MODE

#define SLAVE00_POS   0,0
uint32_t offset_controlword = 0;
uint32_t offset_signal_ctrlword = 0;
uint32_t offset_targetposition = 0;
uint32_t offset_opmode = 0;
uint32_t offset_statusword = 0;
uint32_t offset_actualposition = 0;
uint32_t offset_actualvel = 0;
uint16_t servo_controlword, signal_ctrlword;
uint32_t target_position;
uint32_t actual_position;

#ifdef ENABLE_SHM
shm_handle_t handle;
#endif

#define PER_CIRCLE_ENCODER		(1<<23)
static double set_tar_vel = 1.0;

static void soe_statemachine(uint16_t status)
{
    if ((status & 0x3000) != 0) {
        signal_ctrlword = 0x0001;
	target_position = actual_position;
    }

    if ((status & 0xf000) == 0x8000) {
        servo_controlword = 0xe000;
	target_position = actual_position;
	signal_ctrlword = 0x0;
    } else if ((status & 0xf000) == 0xc000) {
        servo_controlword = 0xe000;
	signal_ctrlword = 0x0;
        target_position = actual_position + 5000;
    }
}

void *my_thread(void *arg)
{
    struct timespec next_period, dc_period;
    unsigned int cycle_count = 0;
    int64_t latency_ns = 0;

    struct sched_param param = {.sched_priority = 99};
    pthread_setschedparam(pthread_self(), SCHED_FIFO, &param);

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
        motion_servo_recv_process(master->master, domain);
	actual_position = EC_READ_S32(domain1 + offset_actualposition);
        soe_statemachine(MOTION_DOMAIN_READ_U16(domain1 + offset_statusword));
        
	MOTION_DOMAIN_WRITE_U16(domain1+offset_signal_ctrlword, signal_ctrlword);
        MOTION_DOMAIN_WRITE_S32(domain1+offset_targetposition, target_position);
        MOTION_DOMAIN_WRITE_U16(domain1+offset_controlword, servo_controlword);
        
	clock_gettime(CLOCK_MONOTONIC, &dc_period);
        motion_servo_sync_dc(master->master, TIMESPEC2NS(dc_period));
        motion_servo_send_process(master->master, domain);
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
    struct timespec dc_period;
    int ret;

    getOptions(argc, argv);
    signal(SIGTERM, signal_handler);
    signal(SIGINT, signal_handler);

    mlockall(MCL_CURRENT | MCL_FUTURE);

    /* Create master by ENI*/
    if (!eni_file) {
        printf("Error: Unspecify ENI/XML file\n");
        exit(0);
    }
    master = motion_servo_master_create(eni_file);
    free(eni_file);
    eni_file = NULL;
    if (master == NULL) {
        return -1;
    }
    /* Motion domain create */
    if (motion_servo_domain_entry_register(master, &domain)) {
        goto End;
    }

    if (!motion_servo_driver_register(master, domain)) {
        goto End;
    }

    motion_servo_set_send_interval(master);

    motion_servo_register_dc(master);
    clock_gettime(CLOCK_MONOTONIC, &dc_period);
    motion_master_set_application_time(master, TIMESPEC2NS(dc_period));

    if (motion_servo_master_activate(master->master)) {
        printf("fail to activate master\n");
        goto End;
    }

    domain1 = motion_servo_domain_data(domain);
    if (!domain1) {
        printf("fail to get domain data\n");
        goto End;
    }

    uint8_t value_s_15[2] = {0x07, 0x00};
    ret = motion_servo_slave_config_idn(master, 0, 0, 0, 15, value_s_15, 2);
    if(ret < 0){
        fprintf(stderr, "Failed to set telegram type.\n");
        return -1;
    }

    uint8_t value_s_16[10] = {0x06, 0x00, 0x06, 0x00, 0x33, 0x00, 0x0b, 0x00, 0x0c, 0x00};
    ret = motion_servo_slave_config_idn(master, 0, 0, 0, 16, value_s_16, 10);
    if(ret < 0){
        fprintf(stderr, "Failed to ecrt_slave_config_idn.\n");
        return -1;
    }

    uint8_t value_s_24[8] = {0x04, 0x00, 0x04, 0x00, 0x2f, 0x00, 0x91, 0x00};
    ret = motion_servo_slave_config_idn(master, 0, 0, 0, 24, value_s_24, 8);
    if(ret < 0){
        fprintf(stderr, "Failed to ecrt_slave_config_idn.\n");
        return -1;
    }


    uint8_t value_s_32[2] = {0x0b, 0x00};
    ret = motion_servo_slave_config_idn(master, 0, 0, 0, 32, value_s_32, 2);
    if(ret < 0){
        fprintf(stderr, "Failed to set operration mode.\n");
        return -1;
    }


    uint8_t value_s_1[2] = {0xf4, 0x01};
    ret = motion_servo_slave_config_idn(master, 0, 0, 0, 1, value_s_1, 2);
    if(ret < 0){
        fprintf(stderr, "Failed to set operration mode.\n");
        return -1;
    }

    domain_size = motion_servo_domain_size(domain);
    offset_statusword = motion_servo_get_domain_offset(master->master, SLAVE00_POS, 0x87, 0x00);
    if (offset_statusword == DOMAIN_INVAILD_OFFSET)
    {
        goto End;
    }
    offset_actualposition = motion_servo_get_domain_offset(master->master, SLAVE00_POS, 0x33, 0x00);
    if (offset_actualposition == DOMAIN_INVAILD_OFFSET)
    {
        goto End;
    }
    offset_controlword = motion_servo_get_domain_offset(master->master, SLAVE00_POS, 0x86, 0x00);
    if (offset_controlword == DOMAIN_INVAILD_OFFSET)
    {
        goto End;
    }
    offset_targetposition = motion_servo_get_domain_offset(master->master, SLAVE00_POS, 0x2f, 0x00);
    if (offset_targetposition == DOMAIN_INVAILD_OFFSET)
    {
        goto End;
    }
    offset_signal_ctrlword = motion_servo_get_domain_offset(master->master, SLAVE00_POS, 0x91, 0x00);
    if (offset_signal_ctrlword == DOMAIN_INVAILD_OFFSET)
    {
        goto End;
    }
    /* Create cyclic RT-thread */
    pthread_attr_t thattr;
    pthread_attr_init(&thattr);
    pthread_attr_setdetachstate(&thattr, PTHREAD_CREATE_JOINABLE);

    if (pthread_create(&cyclic_thread, &thattr, &my_thread, NULL)) {
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
    pthread_attr_destroy(&thattr);
    motion_servo_master_release(master);
    return 0;
End:
    motion_servo_master_release(master);
    return -1;
}

