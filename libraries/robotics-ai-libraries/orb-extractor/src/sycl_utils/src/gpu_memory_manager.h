// SPDX-License-Identifier: Apache-2.0
/*
Author: Gao Mingcen
Date: 28/02/2013

File Name: GpuMemoryManager.h

Class definition of GpuMemoryManager, a simple manager of managing memory for
GPU

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

#pragma once

#include <vector>

#include "device.h"

struct GpuMemoryUnit
{
  int * pointer;
  int byteLength;
};

class GpuMemoryManager
{
private:
  int _initialized;
  size_t _maxByteLength;
  size_t _usedByteLength;
  int _createTimes;
  int _reuseTimes;
  int _releaseTimes;
  int _deleteTimes;
  size_t _accumulatedLength;
  bool _shared;
  std::vector<GpuMemoryUnit> freeMemoryPool;
  std::vector<GpuMemoryUnit> usingMemoryPool;
  int _findFirstFittingFreeUnit(size_t byteLength);
  int _findUsingUnit(void * pointer);
  bool _createMemory(void ** pointer, size_t byteLength);
  bool _freeMemory(size_t byteLength);

  std::shared_ptr<Device> dev_;

public:
  GpuMemoryManager(bool shared);
  ~GpuMemoryManager(void);
  std::shared_ptr<Device> GetDevice();
  void InitializeQueue(std::shared_ptr<Device> dev);
  bool GetMemory(void ** pointer, size_t byteLength);
  bool ReleaseMemory(void * pointer);
  bool ExpandArray(void ** pointer, size_t oldByteLength, size_t newByteLength);
};
