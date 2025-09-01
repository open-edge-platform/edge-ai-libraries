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
#include <cm/cmtl.h>

#define X 0
#define Y 1

#define BLKW 16
#define BLKH 8

//Constants defined in OpenCV
const int INTER_RESIZE_COEF_BITS = 11;
const int INTER_RESIZE_COEF_SCALE = 1 << INTER_RESIZE_COEF_BITS; //2048
const int CAST_BITS = INTER_RESIZE_COEF_BITS << 1; //22

const short increment[BLKW] = { 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15 };

//
//  Resize for various interpolation method (linear)
//
//////////////////////////////////////////////////////////////////////////////////////////
extern "C" _GENX_MAIN_ void
resize_linear_A8_GENX(
        SurfaceIndex SrcSI [[type("buffer_t")]],          // input surface buffer of INT  
        SurfaceIndex DstSI [[type("buffer_t")]],          // input surface buffer of INT  
        uint srcWidth,
        uint srcHeight,
        uint dstWidth,
        float ifx,
        float ify
     )
{
    vector<short, 2> pos;

    pos(X) = cm_local_id(X) + cm_group_id(X) * cm_local_size(X);
    pos(Y) = cm_local_id(Y) + cm_group_id(Y) * cm_local_size(Y);
    pos(X) = pos(X) * BLKW;
    pos(Y) = pos(Y) * BLKH;

    vector<short, BLKW> posXIdx(increment);
    posXIdx = posXIdx + pos(X);
    vector<short, BLKH> posYIdx(increment);
    posYIdx = posYIdx + pos(Y);

    vector<float, BLKW> sx((posXIdx + 0.5f) * ifx - 0.5f);
    vector<float, BLKH> sy((posYIdx + 0.5f) * ify - 0.5f);
    vector<int, BLKW> x(cm_rndd<uint>(sx));
    vector<int, BLKH> y(cm_rndd<uint>(sy));
    vector<float, BLKW> u(sx - x);
    vector<float, BLKH> v(sy - y);
    vector<uint, BLKW> src_cols(srcWidth - 1);
    vector<uint, BLKH> src_rows(srcHeight - 1);

    u.merge(0.f, (x < 0));
    x.merge(0, (x < 0));
    u.merge(0.f, (x >= srcWidth));
    x.merge(srcWidth - 1, (x >= srcWidth));
    v.merge(0.f, (y < 0));
    y.merge(0, (y < 0));
    v.merge(0.f, (y >= srcHeight));
    y.merge(srcHeight - 1, (y >= srcHeight));

    vector<uint, BLKW> x_ = cm_min<uint>(x+1, src_cols);
    vector<uint, BLKH> y_ = cm_min<uint>(y+1, src_rows);

    u = u * INTER_RESIZE_COEF_SCALE;
    v = v * INTER_RESIZE_COEF_SCALE;

    vector<int, BLKW> U = cm_rnde<int>(u);
    vector<int, BLKW> U1 = cm_rnde<int>(INTER_RESIZE_COEF_SCALE - u);
    vector<int, BLKH> V = cm_rnde<int>(v);
    vector<int, BLKH> V1 = cm_rnde<int>(INTER_RESIZE_COEF_SCALE - v);

    vector<uint, BLKW> _x = x;
    vector<uint, BLKH> _y = y;

    vector<uchar, BLKW> out;
    vector<uint, BLKW> outpos = posXIdx + posYIdx[0] * dstWidth;

#pragma unroll
    for (int i = 0; i < BLKH; i++)
    {
        vector<uchar, BLKW> data0, data1, data2, data3;

        read(SrcSI, 0, (_y.select<1,1>(i).replicate<BLKW>()*srcWidth) + _x, data0);
        read(SrcSI, 0, (_y.select<1,1>(i).replicate<BLKW>()*srcWidth) + x_, data1);
        read(SrcSI, 0, (y_.select<1,1>(i).replicate<BLKW>()*srcWidth) + _x, data2);
        read(SrcSI, 0, (y_.select<1,1>(i).replicate<BLKW>()*srcWidth) + x_, data3);

        vector<int, BLKW> U1V1 = cm_mul<int>(U1, V1[i]);
        vector<int, BLKW> UV1 = cm_mul<int>(U, V1[i]);
        vector<int, BLKW> U1V = cm_mul<int>(U1, V[i]);
        vector<int, BLKW> UV = cm_mul<int>(U, V[i]);

        vector<int, BLKW> val = cm_mul<int>(U1V1, data0) + cm_mul<int>(UV1, data1) +
                                    cm_mul<int>(U1V, data2) + cm_mul<int>(UV, data3);

        out.select<BLKW,1>(0) = (val + ( 1 << ( CAST_BITS - 1))) >> CAST_BITS;
        if ((posXIdx > dstWidth).any())
        {
            // Force out of bound write and HW will drop it
            vector<uchar,  BLKW> out_bound_mask = posXIdx >= dstWidth;
            outpos.merge(0xffffffff, out_bound_mask);
        }

        write(DstSI, 0, outpos, out);
        outpos += dstWidth;
    }
}
