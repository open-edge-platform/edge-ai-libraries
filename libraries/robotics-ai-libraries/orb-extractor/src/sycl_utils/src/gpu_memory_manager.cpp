// SPDX-License-Identifier: Apache-2.0
/*
Author: Gao Mingcen
Date: 28/02/2013

File Name: GpuMemoryManager.cu

Functions of GpuMemoryManager, a simple manager of managing memory for GPU

===============================================================================

Copyright (c) 2012, 2013, School of Computing, National University of Singapore.
All rights reserved.

Project homepage: http://www.comp.nus.edu.sg/~tants/flipflop.html

If you use ffHull and you like it or have comments on its usefulness etc., we
would love to hear from you at <tants@comp.nus.edu.sg>. You may share with us
your experience and any possibilities that we may improve the work/code.

===============================================================================

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

Redistributions of source code must retain the above copyright notice, this list
of conditions and the following disclaimer. Redistributions in binary form must
reproduce the above copyright notice, this list of conditions and the following
disclaimer in the documentation and/or other materials provided with the
distribution.

Neither the name of the National University of Singapore nor the names of its
contributors may be used to endorse or promote products derived from this
software without specific prior written permission from the National University
of Singapore.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE  GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
*/
#ifdef _WIN32
#define ONEDPL_USE_PREDEFINED_POLICIES 0
#endif

// #include <sycl/sycl.hpp>
// #include <dpct/dpct.hpp>
#include "gpu_memory_manager.h"

#include <stdlib.h>

#include <cstdio>

#include "device_impl.h"

GpuMemoryManager::GpuMemoryManager(bool shared)
{
  this->_initialized = false;
  this->_usedByteLength = 0;
  this->_createTimes = 1;
  this->_deleteTimes = 1;
  this->_releaseTimes = 1;
  this->_reuseTimes = 1;
  this->_accumulatedLength = 0;
  this->_shared = shared;
}

GpuMemoryManager::~GpuMemoryManager()
{
  if (this->_initialized) {
    this->_initialized = false;
    for (unsigned int i = 0; i < this->freeMemoryPool.size(); i++) {
      int * pointer = this->freeMemoryPool[i].pointer;
      dev_->GetDeviceImpl()->free(pointer);
    }
    for (unsigned int i = 0; i < this->usingMemoryPool.size(); i++) {
      int * pointer = this->usingMemoryPool[i].pointer;
      dev_->GetDeviceImpl()->free(pointer);
    }
    this->freeMemoryPool.clear();
    this->usingMemoryPool.clear();
  }
}

std::shared_ptr<Device> GpuMemoryManager::GetDevice()
{
  if (this->_initialized)
    return dev_;
  else
    return nullptr;
}

void GpuMemoryManager::InitializeQueue(std::shared_ptr<Device> dev)
{
  if (this->_initialized) return;

  size_t totalMemory = dev->GetDeviceImpl()->get_global_mem_size();

  dev_ = dev;

  this->_maxByteLength = totalMemory;
  this->_initialized = true;
}

bool GpuMemoryManager::ReleaseMemory(void * pointer)
{
  int index = this->_findUsingUnit(pointer);
  if (index == -1) {
    printf("GpuMemoryManager Error: Space is lost when released\n");
    return false;
  }

  GpuMemoryUnit gmu = this->usingMemoryPool[index];
  int byteLength = gmu.byteLength;
  //--reorganize
  this->usingMemoryPool.erase(this->usingMemoryPool.begin() + index);
  int pos = this->_findFirstFittingFreeUnit(byteLength);
  if (pos >= 0)
    this->freeMemoryPool.insert(this->freeMemoryPool.begin() + pos, gmu);
  else
    this->freeMemoryPool.push_back(gmu);

  return true;
}

bool GpuMemoryManager::GetMemory(void ** pointer, size_t byteLength)
{
  //--find the proper one
  int index = this->_findFirstFittingFreeUnit(byteLength);
  if (index >= 0) {
    GpuMemoryUnit gmu = this->freeMemoryPool[index];
    if (gmu.byteLength > byteLength * 10 && byteLength <= 50) {
      return this->_createMemory(pointer, byteLength);
    } else {
      *pointer = gmu.pointer;
      //--reorganize
      this->freeMemoryPool.erase(freeMemoryPool.begin() + index);
      this->usingMemoryPool.push_back(gmu);
    }
  } else {
    return this->_createMemory(pointer, byteLength);
  }
  return true;
}
bool GpuMemoryManager::ExpandArray(void ** pointer, size_t oldByteLength, size_t newByteLength)
{
  if (oldByteLength >= newByteLength) return false;
  void * newArray;
  if (!this->GetMemory((void **)&newArray, newByteLength)) exit(-1);
  dev_->GetDeviceImpl()->memcpy(newArray, *pointer, oldByteLength);
  if (!this->ReleaseMemory(*pointer)) exit(-1);
  *pointer = newArray;
  return true;
}
bool GpuMemoryManager::_createMemory(void ** pointer, size_t byteLength)
{
  if (byteLength > this->_maxByteLength - this->_usedByteLength) {
    if (!this->_freeMemory(byteLength)) {
      printf(
        "GpuMemoryManager Error: No extra space is valid(%zu > %zu - %zu)\n", byteLength,
        this->_maxByteLength, this->_usedByteLength);
      return false;
    }
  }
  // malloc space
  int * space;
  if (_shared)
    space = (int *)dev_->GetDeviceImpl()->malloc_shared(byteLength);
  else
    space = (int *)dev_->GetDeviceImpl()->malloc_device(byteLength);
  this->_usedByteLength += byteLength;
  this->_accumulatedLength += byteLength;
  *pointer = space;
  // create unit
  GpuMemoryUnit gmu;
  gmu.pointer = space;
  gmu.byteLength = byteLength;
  //--reorganize
  this->usingMemoryPool.push_back(gmu);

  return true;
}
bool GpuMemoryManager::_freeMemory(size_t byteLength)
{
  int freeByteLength = 0;
  while (freeByteLength < byteLength && !this->freeMemoryPool.empty()) {
    GpuMemoryUnit gmu = this->freeMemoryPool[this->freeMemoryPool.size() - 1];
    dev_->GetDeviceImpl()->free(gmu.pointer);
    freeByteLength += gmu.byteLength;
    this->_usedByteLength -= gmu.byteLength;

    this->freeMemoryPool.pop_back();
  }
  return freeByteLength >= byteLength;
}
int GpuMemoryManager::_findFirstFittingFreeUnit(size_t byteLength)
{
  if (this->freeMemoryPool.empty()) return -1;
  int low = 0, high = this->freeMemoryPool.size() - 1;
  int pos = -1;
  while (true) {
    pos = (low + high) / 2;
    if (this->freeMemoryPool[pos].byteLength == byteLength) {
      break;
    } else if (this->freeMemoryPool[pos].byteLength > byteLength) {
      if (pos == 0)
        break;
      else if (this->freeMemoryPool[pos - 1].byteLength < byteLength)
        break;
      else {
        high = pos - 1;
      }
    } else if (this->freeMemoryPool[pos].byteLength < byteLength) {
      if (pos == this->freeMemoryPool.size() - 1) {
        pos = -1;
        break;
      } else if (this->freeMemoryPool[pos + 1].byteLength > byteLength) {
        pos = pos + 1;
        break;
      } else {
        low = pos + 1;
      }
    }
    if (low > high) {
      pos = -1;
      break;
    }
  }
  return pos;
}

int GpuMemoryManager::_findUsingUnit(void * pointer)
{
  int index;
  for (index = 0; index < (int)this->usingMemoryPool.size(); index++) {
    if (pointer == this->usingMemoryPool[index].pointer) break;
  }
  if (index >= (int)this->usingMemoryPool.size()) {
    index = -1;
  }
  return index;
}
