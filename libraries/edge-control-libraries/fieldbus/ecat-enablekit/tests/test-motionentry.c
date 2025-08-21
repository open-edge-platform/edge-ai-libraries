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
 * @file test-motionentry.c
 * 
 */
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <errno.h>
#include <../libecat/motionentry.h>
#include <../esiconfig/esiconfig.h>
#include <../eniconfig/eniconfig.h>

static const char *base(const char *prog)
{
    const char *p = prog;

    while (*p != '\0') {
        if (*p == '/')
            prog = ++p;
        else
            p++;
    }

    return prog;
}

static void printhelp(const char *prog)
{
    printf("Usage: %s [-h] [-s esifile] [-n enifile]\n", prog);
    printf("  -h         print this help and exit\n");
    printf("  -s <ESI/XML name>        test ESI/XML file\n");
    printf("  -n <ENI/XML name>        test ENI/XML file\n");
    printf("\ntest file types: ENI/XML and ESI/XML.\n");
}

int main (int argc, char **argv)
{
    char* esifile = NULL;
    char* enifile = NULL;
    for (int i=1; i < argc; i++) {
        switch (argv[i][0]) {
        case '-':
            if (argv[i][1] == 'h') {
                printhelp(base(argv[0]));
                goto quit;
            } else if (argv[i][1] == 's') {
                i++;
                if (esifile) {
                    free(esifile);
                    esifile = NULL;
                }
                esifile = malloc(strlen(argv[i])+1);
                if (esifile) {
                    memmove(esifile, argv[i], strlen(argv[i])+1);
                }
            } else if (argv[i][1] == 'n') {
                i++;
                if (enifile) {
                    free(enifile);
                    enifile = NULL;
                }
                enifile = malloc(strlen(argv[i])+1);
                if (enifile) {
                    memmove(enifile, argv[i], strlen(argv[i])+1);
                }
            } else {
                fprintf(stderr, "Invalid argument\n");
                printhelp(base(argv[0]));
                goto quit;
            }
            break;
        }
    }
    test_console();

    if (esifile) {
        test_esiconfig(esifile);
        free(esifile);
        esifile = NULL;
    }
    if (enifile) {
        test_eniconfig(enifile);
        free(enifile);
        enifile = NULL;
    }

    return 0;
quit:
    if (esifile) {
        free(esifile);
        esifile = NULL;
    }
    if (enifile) {
        free(enifile);
        enifile = NULL;
    }
    return -1;
}

