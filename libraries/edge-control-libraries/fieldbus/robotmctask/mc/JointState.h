// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#pragma once

/* joint state structure*/
struct joint_state
{
    double pos_;  /* joint position */
    double vel_;  /* joint velocity */
    double acc_;  /* joint acceleration */
    double toq_;  /* joint torque */
};
