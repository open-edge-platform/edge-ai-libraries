/*
 * MathUtils.hpp
 *
 * Copyright 2020 (C) SYMG(Shanghai) Intelligence System Co.,Ltd
 *
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 *
 */

#pragma once

#include <cmath>

namespace RTmotion
{
#ifndef __square
#define __square(x) ((x) * (x))
#endif

#ifndef __cube
#define __cube(x) (__square(x) * (x))
#endif

#ifndef __EPSILON
#define __EPSILON 0.00001
#endif

#ifndef __iszero
#define __iszero(x) (fabs(x) < __EPSILON)
#endif

#ifndef __isnotzero
#define __isnotzero(x) (fabs(x) > __EPSILON)
#endif

#ifndef __iseq
#define __iseq(a, b) __iszero((a) - (b))
#endif

#ifndef __isne
#define __isne(a, b) __isnotzero((a) - (b))
#endif

#ifndef __isne
#define __isne(a, b) __isnotzero((a) - (b))
#endif

#ifndef __isgt
#define __isgt(a, b) ((a) > (b) + __EPSILON)
#endif

#ifndef __isls
#define __isls(a, b) ((a) < (b)-__EPSILON)
#endif

inline bool isOpposite(double num1, double num2)
{
  if (!num1 || !num2)
    return false;
  else
    return (num1 < 0) != (num2 < 0);
}

}  // namespace RTmotion
