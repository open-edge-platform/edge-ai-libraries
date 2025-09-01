// SPDX-License-Identifier: Apache-2.0
/**                 
***
*** Copyright  (C) 1985-20BLOCK_WIDTH+2 Intel Corporation. All rights reserved.
***
*** The information and source code contained herein is the exclusive
*** property of Intel Corporation. and may not be disclosed, examined
*** or reproduced in whole or in part without explicit written authorization
*** from the company.
***
***
*** Description: Gaussian3x3 filter written using Cm for GenX
***
*** -----------------------------------------------------------------------------------------------
**/
#include <cm/cm.h>

#define X 0
#define Y 1

#define BLOCK_WIDTH 16
#define BLOCK_HEIGHT 16

//
//  Gaussian7x7 filter for picture in U8 pixel format.
//
/////////////////////////////////////////////////////////////////////////////////////////
extern "C" _GENX_MAIN_ void
gaussian_7x7_GENX(
        SurfaceIndex SrcSI [[type("image2d_t uchar")]],
        SurfaceIndex DstSI [[type("image2d_t uchar")]],
        vector<float ,7> Coeffs
        )
{
    vector<short, 2> pos;
    pos(X) = cm_local_id(X) + cm_group_id(X) * cm_local_size(X);
    pos(Y) = cm_local_id(Y) + cm_group_id(Y) * cm_local_size(Y);
    pos(X) = pos(X) * BLOCK_WIDTH;
    pos(Y) = pos(Y) * BLOCK_HEIGHT;

    matrix<uchar, BLOCK_HEIGHT+6, BLOCK_WIDTH*2> inA;
    matrix<float, BLOCK_HEIGHT+6, BLOCK_WIDTH> mX;
    matrix<float, BLOCK_HEIGHT, BLOCK_WIDTH> mX_out;
    matrix<uchar, BLOCK_HEIGHT, BLOCK_WIDTH> outX;

    // Need to fill up kernels border to constant value
    read(SrcSI, pos(X) -3, pos(Y) -3, inA.select<8,1,32,1>(0,0));
    read(SrcSI, pos(X) -3, pos(Y) +5, inA.select<8,1,32,1>(8,0));
    read(SrcSI, pos(X) -3, pos(Y) +13, inA.select<6,1,32,1>(16,0));

    mX = (Coeffs[0] * inA.select<BLOCK_WIDTH+6,1,BLOCK_HEIGHT,1>(0,0))
        + (Coeffs[1] * inA.select<BLOCK_WIDTH+6,1,BLOCK_HEIGHT,1>(0,1))
        + (Coeffs[2] * inA.select<BLOCK_WIDTH+6,1,BLOCK_HEIGHT,1>(0,2))
        + (Coeffs[3] * inA.select<BLOCK_WIDTH+6,1,BLOCK_HEIGHT,1>(0,3))
        + (Coeffs[4] * inA.select<BLOCK_WIDTH+6,1,BLOCK_HEIGHT,1>(0,4))
        + (Coeffs[5] * inA.select<BLOCK_WIDTH+6,1,BLOCK_HEIGHT,1>(0,5))
        + (Coeffs[6] * inA.select<BLOCK_WIDTH+6,1,BLOCK_HEIGHT,1>(0,6));

    mX_out = (Coeffs[0] * mX.select<BLOCK_WIDTH,1,BLOCK_HEIGHT,1>(0,0))
        + (Coeffs[1] * mX.select<BLOCK_WIDTH,1,BLOCK_HEIGHT,1>(1,0))
        + (Coeffs[2] * mX.select<BLOCK_WIDTH,1,BLOCK_HEIGHT,1>(2,0))
        + (Coeffs[3] * mX.select<BLOCK_WIDTH,1,BLOCK_HEIGHT,1>(3,0))
        + (Coeffs[4] * mX.select<BLOCK_WIDTH,1,BLOCK_HEIGHT,1>(4,0))
        + (Coeffs[5] * mX.select<BLOCK_WIDTH,1,BLOCK_HEIGHT,1>(5,0))
        + (Coeffs[6] * mX.select<BLOCK_WIDTH,1,BLOCK_HEIGHT,1>(6,0));

    outX = cm_rnde<uchar>(mX_out);

    write(DstSI, pos(X), pos(Y), outX);
}
