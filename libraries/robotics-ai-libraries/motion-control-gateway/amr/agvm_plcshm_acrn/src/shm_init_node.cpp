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

#include <rclcpp/rclcpp.hpp>
#include <string>
#include <functional>
#include <chrono>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <assert.h>
#include <bits/stdc++.h>
#ifdef ENABLE_SHM_RINGBUF
#include <shmringbuf.h>
#endif

static const rclcpp::Logger LOGGER = rclcpp::get_logger("agvm_plcshm_node");

int main(int argc, char * argv[]) 
{
    rclcpp::init(argc, argv);
#ifdef ENABLE_SHM_RINGBUF
	shm_handle_t handle_s, handle_c;

    handle_s = shm_blkbuf_init("amr_state", 2, 1024);
    handle_c = shm_blkbuf_init("amr_cmd", 2, 1024);
#endif
    rclcpp::spin(std::make_shared<rclcpp::Node>("shm_init_node"));
    rclcpp::shutdown();
#ifdef ENABLE_SHM_RINGBUF
	shm_blkbuf_close(handle_s);
	shm_blkbuf_close(handle_c);
#endif
    return 0;
}
