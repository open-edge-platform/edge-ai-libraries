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

#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <signal.h>
#include <string.h>
#include <malloc.h>
#include <pthread.h>
#include <fcntl.h>
#include <errno.h>
#include <sys/mman.h>
#include <sys/shm.h>

#include "shmringbuf.h"

pthread_t rt;

#define MSG_LEN 512
static char s_buf[MSG_LEN] = {
	0x1f, 0x0, 0x8, 0x3a, 0x58, 0x1e, 0xc3, 0x0, 0x0, 0x37, 0x32,
	0xe4, 0x38, 0x18, 0xc3, 0xa0, 0xf1, 0x4, 0x0, 0x2f, 0x0, 0xe4,
	0x38, 0x18, 0xc3, 0x0, 0x0, 0x0, 0x0, 0x0, 0x3a, 0x1a, 0x1,
	0xa0, 0xf1, 0x4, 0x0, 0x2f
};
static shm_handle_t handle;

int getopt(int argc, char * const argv[], const char *optstring);
extern char *optarg;
extern int optind, opterr, optopt;

#define RT_PRIO 90

static long delay_nsec = 100000000; /* 100 ms */


static void *realtime_thread(void *arg)
{
	int ret, val, n=0;
	struct timespec ts;

	for (;;) {
		val = n++;
		//memset(s_buf, val, sizeof(s_buf));
	
		/* send data to regular thread */
		while (shm_blkbuf_full(handle)) {
			usleep(50);
			printf("full ...");
			//sleep(2);
		}
		printf("\n");
		ret = shm_blkbuf_write(handle, s_buf, sizeof(s_buf));
		//printf("%s: sent %d bytes\n", __FUNCTION__, ret);
		if (!ret) {
			continue;
		}


		/*
			* We run in full real-time mode (i.e. primary mode),
			* so we have to let the system breathe between two
			* iterations.
		*/
		ts.tv_sec = delay_nsec / 1000000000;
		ts.tv_nsec = delay_nsec % 1000000000;
		clock_nanosleep(CLOCK_REALTIME, 0, &ts, NULL);
	}

	return NULL;
}



int main(int argc, char **argv)
{
	struct sched_param rtparam;
	pthread_attr_t rtattr;
	sigset_t set;
	int sig;
	int oc, prio = RT_PRIO;
	int delay_msec = delay_nsec/1000000;
    char ec;

    while (-1 != (oc = getopt(argc, argv, "hi:p:")))
    {
        switch (oc)
        {
        case 'i':
			delay_msec = atoi(optarg);
			delay_nsec = delay_msec*1000000;
            break;
        case 'p':
			prio = atoi(optarg);
			if ( prio < 0 || prio > 99)
				prio = RT_PRIO;
            break;
		case 'h':
			printf("Usage:\n");
			printf("    sudo ./sim_rt_send -i <interval ms> -p <RT thread priority>\n");
			return 0;
        case '?':
            ec = (char)optopt;
            printf("Invalid option \'%c\' !", ec);
            return 0;
        default:
            break;
        }
    }

	rtparam.sched_priority = prio;
	printf("Interval is %d ms.\n", delay_msec);
	printf("Real time thread priority is %d\n.", prio);

	handle = shm_blkbuf_init("shm_test", 16, MSG_LEN);

	sigemptyset(&set);
	sigaddset(&set, SIGINT);
	sigaddset(&set, SIGTERM);
	sigaddset(&set, SIGHUP);
	pthread_sigmask(SIG_BLOCK, &set, NULL);
	pthread_attr_init(&rtattr);
	pthread_attr_setdetachstate(&rtattr, PTHREAD_CREATE_JOINABLE);
	pthread_attr_setinheritsched(&rtattr, PTHREAD_EXPLICIT_SCHED);
	pthread_attr_setschedpolicy(&rtattr, SCHED_FIFO);
	pthread_attr_setschedparam(&rtattr, &rtparam);
	errno = pthread_create(&rt, &rtattr, &realtime_thread, NULL);
	if (errno)
		printf("pthread_create faild\n");
	
	sigwait(&set, &sig);
	pthread_cancel(rt);
	pthread_join(rt, NULL);

	shm_blkbuf_close(handle);
	printf("..end\n");

	return 0;
}
