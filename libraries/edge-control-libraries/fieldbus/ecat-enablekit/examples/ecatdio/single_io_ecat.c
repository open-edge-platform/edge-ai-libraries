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
 * @file single_io_ecat.c
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

#define CYCLE_US                (1000)
#define PERIOD_NS               (CYCLE_US*1000)
#define NSEC_PER_SEC            (1000000000L)
#define TIMESPEC2NS(T)          ((uint64_t) (T).tv_sec * NSEC_PER_SEC + (T).tv_nsec)
#define DIFF_NS(A,B)            (((B).tv_sec - (A).tv_sec)*NSEC_PER_SEC + ((B).tv_nsec)-(A).tv_nsec)
#define CYCLE_COUNTER_PERSEC    (NSEC_PER_SEC/PERIOD_NS)

static pthread_t cyclic_thread;
static volatile int run = 1;
static servo_master* master = NULL;
static uint8_t* domain1;
void* domain;

static unsigned int horselight_tick;
static char *eni_file;

uint32_t output0, output1;
uint32_t input0, input1;

#define SLAVE00_POS   0, 0

void *my_thread(void *arg)
{
    struct timespec next_period;
    unsigned short temp = 1;
    unsigned int cycle_count = 0;

    struct sched_param param = {.sched_priority = 99};
    pthread_setschedparam(pthread_self(), SCHED_FIFO, &param);
    clock_gettime(CLOCK_MONOTONIC, &next_period);
    while(run != 0) {
        next_period.tv_nsec += CYCLE_US * 1000;
        while (next_period.tv_nsec >= NSEC_PER_SEC) {
            next_period.tv_nsec -= NSEC_PER_SEC;
            next_period.tv_sec++;
        }
        clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &next_period, NULL);
        cycle_count++;
        motion_servo_recv_process(master->master, domain);
        if (cycle_count % horselight_tick == 0) {
            temp <<= 1;
            if(temp==0x0000) {
                temp = 1;
            }
        }
        MOTION_DOMAIN_WRITE_U8(domain1+output0, temp&0xFF);
        MOTION_DOMAIN_WRITE_U8(domain1+output1, (temp>>8)&0xFF);
        motion_servo_send_process(master->master, domain);
    }
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
        {"tick",	required_argument,	NULL,	't'},
        {"eni",	    required_argument,	NULL,	'n'},
        {"help",	no_argument,		NULL,	'h'},
        {}
    };
    horselight_tick = 1000;
    do {
        index = getopt_long(argc, argv, "t:n:h", longOptions, NULL);
        switch(index){
            case 't':
                horselight_tick = atoi(optarg);
                printf("Set tick:%d ms \n", horselight_tick);
                break;
            case 'n':
                if (eni_file) {
                    free(eni_file);
                    eni_file = NULL;
                }
                eni_file = malloc(strlen(optarg)+1);
                if (eni_file != NULL) {
                    memset(eni_file, 0, strlen(optarg)+1);
                    memmove(eni_file, optarg, strlen(optarg)+1);
                    printf("Using %s\n", eni_file);
                }
                break;
            case 'h':
                printf("Global options:\n");
                printf("    --tick      -t  Set horse light cycle tick, default: %d ms\n", horselight_tick);
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

    if (motion_servo_master_activate(master->master)) {
        printf("fail to activate master\n");
        goto End;
    }
    domain1 = motion_servo_domain_data(domain);
    if (!domain1) {
        printf("fail to get domain data\n");
        goto End;
    }
    output0 = motion_servo_get_domain_offset(master->master, SLAVE00_POS, 0x7001, 0x01);
    if (output0 == DOMAIN_INVAILD_OFFSET)
    {
        goto End;
    }
    output1 = motion_servo_get_domain_offset(master->master, SLAVE00_POS, 0x7001, 0x02);
    if (output1 == DOMAIN_INVAILD_OFFSET)
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
        sched_yield();
        //sleep(0.01);
    }
    pthread_join(cyclic_thread, NULL);
    pthread_attr_destroy(&thattr);
    motion_servo_master_release(master);
    return 0;
End:
    motion_servo_master_release(master);
    return -1;
}
