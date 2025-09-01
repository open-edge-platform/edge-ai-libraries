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
 * @brief A header file with declaration for ACRN shared memory device
 * @file acrn_shm.hpp
 */
#ifndef MC_GW__ACRN_SHM_HPP_
#define MC_GW__ACRN_SHM_HPP_

#include <stdio.h>
#include <unistd.h>
#include <iostream>
#include <fcntl.h>
#include <string.h>
#include <sys/mman.h>
#include <map>

namespace cross_vm_messenger
{
/**
 * @class AcrnSharedMemory
 * @brief This class implements the ops of ACRN shared memory.
 *
 * The common usage step:
 *   @todo
 */
class AcrnSharedMemory  // singleton
{
  #define PATH_MAX 4096
public:
  enum
  {
    UIO_UR_ROS_to_FuSa = 0,
    UIOj_UR_FuSa_to_ROS = 1,
  };
  typedef struct {
    char* start;
    size_t len;
  } MemoryUsage;

public:
  AcrnSharedMemory(const int uio_nr = 0, const size_t mem_size = 4096)
  : uio_nr_(uio_nr), shm_size_(mem_size)
  {
    shm_size_ = alignSize(mem_size);

    char node_path[PATH_MAX] = {0};
    sprintf(node_path, "/sys/class/uio/uio%ld/device/resource2_wc", (long int)uio_nr);

    fd_ = open(node_path, O_RDWR);
    if (fd_ < 0 ){
      throw std::runtime_error("Open UIO device node ERROR!");
    }

    shm_addr_ = (char*)mmap(NULL, shm_size_, PROT_READ|PROT_WRITE, MAP_SHARED, fd_, 0);
	  if (shm_addr_ == MAP_FAILED) {
      throw std::runtime_error("mmap failed!");
	  }

    reset();
  }

  virtual ~AcrnSharedMemory()
  {
    if (fd_ >= 0){
      close(fd_);
    }
    if (shm_addr_ != nullptr){
      munmap(shm_addr_, shm_size_);
    }
  }

  void reset()
  {
    for (int i = 0; i < (int)shm_size_; i++) {
      shm_addr_[i] = 0;
    }
    MemoryUsage use;
    shm_use_.clear();
    use.start = shm_addr_;
    use.len = shm_size_;
    shm_use_["remaining"] = use;
  }

  bool assign(std::string name, const size_t size)
  {
    MemoryUsage remaining = shm_use_["remaining"];
    size_t asize = alignSize(size);
    size_t available = shm_size_ + (size_t)shm_addr_ - (size_t)remaining.start;
    if (asize > available){
      std::cout << "ERROR: no enough space in shared memory! (available space=" << available << ")" << std::endl;
      return false;
    }

    MemoryUsage new_use;
    new_use.start = remaining.start;
    new_use.len = asize;
    remaining.start += asize;

    shm_use_[name] = new_use;
    shm_use_["remaining"] = remaining;

    return true;
  }

  int read(std::string use, char* buf, int size) const
  {
    if (buf == nullptr){
      std::cout << "the input Buf is not assigned, read Nothing!" << std::endl;
      return 0;
    }

    auto mem_use = shm_use_.find(use);
    if(mem_use == shm_use_.end()){
      std::cout << "WARNING: did NOT find the assigned memory! read Nothing!" << std::endl;
      return 0;
    }

    size_t n = size;
    if(n > mem_use->second.len){
      std::cout << "WARNING: the required size is larger than the assigned memory!" 
        << std::endl;
      n = mem_use->second.len;
    }
    memcpy(buf, mem_use->second.start, n);
    return n;
  }

  int write(std::string use, char* buf, int size) const
  {
    if (buf == nullptr){
      std::cout << "the output Buf is not assigned, read Nothing!" << std::endl;
      return 0;
    }

    auto mem_use = shm_use_.find(use);
    if(mem_use == shm_use_.end()){
      std::cout << "WARNING: did NOT find the assigned memory! read Nothing!" << std::endl;
      return 0;
    }

    size_t n = size;
    if(n > mem_use->second.len){
      std::cout << "WARNING: the required size is larger than the assigned memory!" 
        << std::endl;
      n = mem_use->second.len;
    }
    memcpy(mem_use->second.start, buf, n);

    return n;
  }

  char* get_shm_addr(std::string use = "") const
  {
    if (use == ""){
      return shm_addr_;
    }
    
    auto mem_use = shm_use_.find(use);
    if(mem_use == shm_use_.end()){
      std::cout << "WARNING: did NOT find the assigned memory! " << std::endl;
      return nullptr;
    }

    return mem_use->second.start;
  }
  
  void dump_memory(std::string use = "", int buf_size = -1)
  {
    size_t mem_sz = shm_size_;
    char* mem_start = shm_addr_;

    auto mem_use = shm_use_.find(use);
    if(mem_use != shm_use_.end()){
      mem_start = mem_use->second.start;
      mem_sz = mem_use->second.len;
    }
    if (mem_sz > 1024 ) mem_sz = 1024;
    int dump_sz = buf_size;
    if (dump_sz > (int)mem_sz) dump_sz = mem_sz;

    char tmp[1024] = {0};
	  size_t len, size = sizeof(tmp);
	  char *p = tmp;
	  int i;

	  len = snprintf(p, size, "Shared memory Dump: [");
	  p += len;
	  size -= len;

	  for (i = 0; i < dump_sz; i++) {
		  len = snprintf(p, size, " 0x%x", mem_start[i]);
		  p += len;
		  size -= len;
	  }

	  len = snprintf(p, size, " ]");
	  p += len;
	  size -= len;

	  printf("%s\n", tmp);
  }
private:
  inline size_t alignSize(size_t size)
  {
    int page_size = getpagesize();
    if (page_size <= 0){
      std::cout << "WARNING: page size <=0!" << std::endl;
      return size;
    }
    return ((size + page_size -1) & ~(page_size - 1));
  }
private:
  int fd_ = -1;
  int uio_nr_ = -1;
  size_t shm_size_ = 0;
  char* shm_addr_ = nullptr;

  std::map<std::string, MemoryUsage> shm_use_;

};

}  // namespace Params
#endif  // VINO_PARAM_LIB__PARAM_MANAGER_HPP_
