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

#include <cm/cm.h>

//  Resize for various interpolation method (linear)
//
//////////////////////////////////////////////////////////////////////////////////////////
extern "C" _GENX_MAIN_ void
fastclear_GENX(
        SurfaceIndex Src1SI [[type("buffer_t")]],          // input surface buffer of INT  
        SurfaceIndex Src2SI [[type("buffer_t")]]           // input surface buffer of INT  
     )
{
    vector<int, 4> out = 0;

    write(Src1SI, 0, out);
    write(Src2SI, 0, out);
}
