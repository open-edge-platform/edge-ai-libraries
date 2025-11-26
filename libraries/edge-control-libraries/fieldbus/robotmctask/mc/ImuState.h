// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#pragma once

struct orientation
{
    double x;
    double y;
    double z;
    double w;
};

struct triplet
{
    double x;
    double y;
    double z;
};

struct imu_state
{
    orientation orientation_; /* quaternion (x,y,z,w) */
    std::array<double, 9> orientation_covariance_; /* major 3x3 matrix about (x,y,z) */
    triplet vel_; /* angular velocity triplet (x,y,z) */
    std::array<double, 9> vel_covariance_; /* major 3x3 matrix about (x,y,z) */
    triplet acc_; /* linear acceleration triplet (x,y,z) */
    std::array<double, 9> acc_covariance_; /* major 3x3 matrix about (x,y,z) */
    double tor_;
};
