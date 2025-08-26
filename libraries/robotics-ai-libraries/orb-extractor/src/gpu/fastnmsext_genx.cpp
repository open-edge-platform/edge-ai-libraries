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

#define BLKW 128

const short neighbourX_idx[16] = {3,3,2,1,0,-1,-2,-3,-3,-3,-2,-1,0,1,2,3};
const short neighbourY_idx[16] = {0,-1,-2,-3,-3,-3,-2,-1,0,1,2,3,3,3,2,1};
const short increment[16] = {0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15};

/* No __inline.  Will spill registers */
 _GENX_ vector<int, 16> cornerScore(
        SurfaceIndex imgSI [[type("buffer_t")]],
        vector<uint, 16> kX,
        vector<uint, 16> kY,
        int step
        )
{
    vector<uint, 16> vImgIdx = kX + kY * step;
    vector<uchar, 16> v;
    vector<int, 16> a0 (0);
    vector<int, 16> b0;
    read(imgSI, 0, vImgIdx, v);

    matrix<int, 16, 16> d;
    vector<uint, 16> nImgXIdx(neighbourX_idx);
    vector<uint, 16> nImgYIdx(neighbourY_idx);

#pragma unroll
    for (int i = 0; i < 16; i++)
    {
        vector<uint, 16> nImgIdx = vImgIdx[i] + nImgXIdx + nImgYIdx * step;

        vector<uchar, 16> neighbour;
        read(imgSI, 0, nImgIdx, neighbour);

        d.column(i) = v[i] - neighbour;
    }

#pragma unroll
    for (int k = 0; k < 16; k += 2)
    {
        vector<int, 16> a = cm_min<int>(d.row((k+1)&15), d.row((k+2)&15));
        a = cm_min<int>(a, d.row((k+3)&15));
        a = cm_min<int>(a, d.row((k+4)&15));
        a = cm_min<int>(a, d.row((k+5)&15));
        a = cm_min<int>(a, d.row((k+6)&15));
        a = cm_min<int>(a, d.row((k+7)&15));
        a = cm_min<int>(a, d.row((k+8)&15));
        a0 = cm_max<int>(a0, cm_min<int>(a, d.row((k)&15)));
        a0 = cm_max<int>(a0, cm_min<int>(a, d.row((k+9)&15)));
    }

    b0 = -a0;

#pragma unroll
    for (int k = 0; k < 16; k += 2)
    {
        vector<int, 16> b = cm_max<int>(d.row((k+1)&15), d.row((k+2)&15));
        b = cm_max<int>(b, d.row((k+3)&15));
        b = cm_max<int>(b, d.row((k+4)&15));
        b = cm_max<int>(b, d.row((k+5)&15));
        b = cm_max<int>(b, d.row((k+6)&15));
        b = cm_max<int>(b, d.row((k+7)&15));
        b = cm_max<int>(b, d.row((k+8)&15));
        b0 = cm_min<int>(b0, cm_max<int>(b, d.row((k))));
        b0 = cm_min<int>(b0, cm_max<int>(b, d.row((k+9)&15)));
    }

    return -b0-1;
}


//
//  Non maximum supression for FAST
//
//////////////////////////////////////////////////////////////////////////////////////////
extern "C" _GENX_MAIN_ void
fastnmsext_GENX(
        SurfaceIndex ImgSrcSI [[type("buffer_t")]],    // Img surface index
        SurfaceIndex KeysSrcSI [[type("buffer_t")]],   // Keypoints input surface index
        SurfaceIndex KeysDstSI [[type("buffer_t")]],   // Keypoints output surface index
        uint srcWidth,
        uint srcHeight,
        uint step,
        float minXY
     )
{
    int pos = get_thread_origin_x() * BLKW * 2 * 4;
    int tid = get_thread_origin_x() * BLKW;
    vector<uint, 1> count;
    read(KeysSrcSI, 0, count);

//#pragma unroll
    for (int l = 0; l < 8; l++)
    {
        vector<uint, 32> keyPtIn;

        read(DWALIGNED(KeysSrcSI), pos + 4, keyPtIn);

        vector<uint, 16> kX = keyPtIn.select<16,2>(0);
        vector<uint, 16> kY = keyPtIn.select<16,2>(1);

        vector<int, 16> s = cornerScore(ImgSrcSI, kX, kY, step);

        vector <short, 16> checkA;
        checkA = (kX < 4 | s > cornerScore(ImgSrcSI, kX-1, kY, step)) +
                (kY < 4 | s > cornerScore(ImgSrcSI, kX, kY-1, step));

        if ((checkA != 2).all())
        {
            pos += 128;
            tid += 16;

            if (tid > count[0])
               return;
            continue;
        }

        vector <short, 16> checkB;
        checkB =  (kX >= srcWidth - 4 | s > cornerScore(ImgSrcSI, kX+1, kY, step)) +
            (kY >= srcHeight - 4 | s > cornerScore(ImgSrcSI, kX, kY+1, step)) +
            (kX < 4 | kY < 4 | s > cornerScore(ImgSrcSI, kX-1, kY-1, step)) +
            (kX >= srcWidth - 4 | kY < 4 | s > cornerScore(ImgSrcSI, kX+1, kY-1, step)) +
            (kX < 4 | kY >= srcHeight - 4 | s > cornerScore(ImgSrcSI, kX-1, kY+1, step)) +
            (kX >= srcWidth - 4 | kY >= srcHeight - 4 | s > cornerScore(ImgSrcSI, kX+1, kY+1, step));

        // mask out the pixel if out of bound
        vector <uint, 16> posInc(increment);
        posInc += tid;
        vector <ushort, 16> inBound = (posInc < count[0]) * 0xffff;
        checkB &= inBound;

        /*
        if ((cc == 9752) && (tid >= 9728))
        {
            int cccc = count[0];
            printf("count[0]=%d, tid=%d\n", cccc, tid);
            printf("posInc=%d %d %d %d %d %d %d %d\n",
                    posInc[0],posInc[1],posInc[2],posInc[3],
                    posInc[4],posInc[5],posInc[6],posInc[7]);

            printf("inBound=%d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d\n",
                    inBound[0],inBound[1],inBound[2],inBound[3],
                    inBound[4],inBound[5],inBound[6],inBound[7],
                    inBound[8],inBound[9],inBound[10],inBound[11],
                    inBound[12],inBound[13],inBound[14],inBound[15]
                    );
            printf("kX=%d %d %d %d %d %d %d %d,%d,%d,%d,%d,%d,%d,%d,%d\n",
                    kX[0],kX[1],kX[2],kX[3],
                    kX[4],kX[5],kX[6],kX[7],
                    kX[8],kX[9],kX[10],kX[11],
                    kX[12],kX[13],kX[14],kX[15]
                    );
            printf("kY=%d %d %d %d %d %d %d %d,%d,%d,%d,%d,%d,%d,%d,%d\n",
                    kY[0],kY[1],kY[2],kY[3],
                    kY[4],kY[5],kY[6],kY[7],
                    kY[8],kY[9],kY[10],kY[11],
                    kY[12],kY[13],kY[14],kY[15]
                    );
        }
        */

        if ((checkB == 6).any())
        {
            vector<uint, 1> keyidx = 0;
            vector<uint, 1> ret;

            for (int i = 0; i < 16; i++)
            {
                if (checkB[i] == 6 && checkA[i] == 2)
                {
                    vector<int, 4> keyoutput;
                    keyoutput.select<1,1>(0) = kX[i] - minXY;
                    keyoutput.select<1,1>(1) = kY[i] - minXY;
                    keyoutput.select<1,1>(2) = s[i];
                    keyoutput.select<1,1>(3) = 0.f;


                    write_atomic<ATOMIC_INC, uint, 1>(KeysDstSI, keyidx, ret);

                    vector<uint, 4> ss;
                    ss[0] = ret[0]*4;
                    ss[1] = ret[0]*4+1;
                    ss[2] = ret[0]*4+2;
                    ss[3] = ret[0]*4+3;

                    write(KeysDstSI, 1, ss, keyoutput);

                }
            }
        }

        tid += 16;
        pos += 128;
        if (tid > count[0])
            return;
    }
}
