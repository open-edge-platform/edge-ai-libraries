// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#ifndef PLC_RT_H
#define PLC_RT_H

#include <cstdio>
#include <thread>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <pthread.h>
#include <sys/mman.h>
#include <getopt.h>
#include <math.h>

#include <shmringbuf.h>

#include <fb/common/include/axis.hpp>
#include <fb/common/include/global.hpp>
#include <fb/public/include/fb_halt.hpp>
#include <fb/public/include/fb_stop.hpp>
#include <fb/public/include/fb_power.hpp>
#include <fb/public/include/fb_reset.hpp>
#include <fb/public/include/fb_read_axis_error.hpp>
#include <fb/public/include/fb_read_actual_velocity.hpp>
#include <fb/public/include/fb_move_velocity.hpp>
#include <fb/public/include/fb_move_absolute.hpp>
#include <fb/public/include/fb_move_relative.hpp>

double agvmGetRatioByVelLimit(const double VelLimit, const double Vel1, const double Vel2, const double Vel3, const double Vel4);
double agvmLimitVel(const double Vel, const double VelMin);


double agvmGetRatioByVelLimit(const double VelLimit, const double Vel1, const double Vel2, const double Vel3, const double Vel4)
{
  double 	Ratio = 1.0, VelMax;
  VelMax = fabs(Vel1);

  if (VelMax < fabs(Vel2))
    VelMax = fabs(Vel2);

  if (VelMax < fabs(Vel3))
    VelMax = fabs(Vel3);

  if (VelMax < fabs(Vel4))
    VelMax = fabs(Vel4);

  if (VelMax > 0.0)
    Ratio = VelLimit / VelMax;

  return Ratio;
}

double agvmLimitVel(const double Vel, const double VelMin)
{
  double res = Vel;
  if (Vel > 0.0 && Vel > VelMin)
    res = VelMin;
  if (Vel < 0.0 && Vel < -VelMin)
    res = -VelMin;

  return res;
}
#endif