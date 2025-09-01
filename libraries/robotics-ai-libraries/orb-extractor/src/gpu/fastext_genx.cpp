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
#define EVEN_MASK (1+4+16+64)
#define SLM_SIZE 64
#define BLKH 16
#define BLKW 16

static const uint init_offset[8] = { 0,4,4,4,4,4,4,4 };
static const ushort increment[16] = { 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15 };

inline _GENX_ void update_mask(
        int idx,
        vector_ref<uchar, 16> v0,
        vector_ref<uchar, 16> v1,
        vector_ref<int, 16> t0,
        vector_ref<int, 16> t1,
        vector_ref<int, 16> m0,
        vector_ref<int, 16> m1
        )
{
    m0 |= ((v0 < t0) << idx) | ((v1 < t0) << (8 + idx));
    m1 |= ((v0 > t1) << idx) | ((v1 > t1) << (8 + idx));
}

inline _GENX_ vector<int, 16> check(
        int idx,
        vector_ref<int, 16> m
        )
{
    return ((m & (511 << idx)) == (511 << idx));
}

inline _GENX_ void extractKeyPoints(
        matrix_ref<uchar, 22, 32> src,
        SurfaceIndex DstSI [[type("buffer_t")]],   // Keypoint surface index
        uint slmIdx,
        vector<short, 2> startPos,
        int overlap,
        int cellSize,
        int maxWidth,
        int maxHeight,
        int threshold,
        int minXY,
        int monoWidth
        )
{
    int minGroupX = startPos(X);
    int minGroupY = startPos(Y);
    int maxGroupX = startPos(X) + cellSize + overlap;
    int maxGroupY = startPos(Y) + cellSize + overlap;

    int image_number = cm_rndd<int>(startPos(X)/(monoWidth)) + 1;

    int image_boundary = monoWidth * image_number - minXY;

    if (maxGroupX > image_boundary)
      maxGroupX = image_boundary;

    if (maxGroupX > maxWidth)
      maxGroupX = maxWidth;

    vector<short, 2> pos;
    pos(X) = startPos(X) + cm_local_id(X)*BLKW;
    pos(Y) = startPos(Y) + cm_local_id(Y)*BLKH;

    vector<short, 16> posXidx;
    cmtl::cm_vector_assign(posXidx, pos(X), 1);

    int maxRow = ((pos(Y) + BLKH) > maxGroupY) ? maxGroupY - pos(Y) : BLKH;

    matrix<ushort, BLKH, BLKW> validKey = 0;

    vector<ushort, BLKW*BLKH*2> keyout = 0;
    int totalKey = 0, curIdx = 0;

    for (int nRow = 0; nRow < maxRow; nRow++)
    {
        vector<int, 16> t0 = src.row(nRow+3).select<16,1>(3) - threshold;
        vector<int, 16> t1 = src.row(nRow+3).select<16,1>(3) + threshold;
        vector<int, 16> m0 = 0;
        vector<int, 16> m1 = 0;

        update_mask(0, src.row(nRow+3).select<16,1>(6), src.row(nRow+3).select<16,1>(0), t0, t1, m0, m1);

        if (((m0 | m1) == 0).all())
            continue;

        update_mask(2, src.row(nRow+1).select<16,1>(5), src.row(nRow+5).select<16,1>(1), t0, t1, m0, m1);
        update_mask(4, src.row(nRow).select<16,1>(3), src.row(nRow+6).select<16,1>(3), t0, t1, m0, m1);
        update_mask(6, src.row(nRow+1).select<16,1>(1), src.row(nRow+5).select<16,1>(5), t0, t1, m0, m1);

        if( (((( m0 | (m0 >> 8)) & EVEN_MASK) != EVEN_MASK).all()) &&
            (((( m1 | (m1 >> 8)) & EVEN_MASK) != EVEN_MASK).all()) )
                continue;

        update_mask(1, src.row(nRow+2).select<16,1>(6), src.row(nRow+4).select<16,1>(0), t0, t1, m0, m1);
        update_mask(3, src.row(nRow).select<16,1>(4), src.row(nRow+6).select<16,1>(2), t0, t1, m0, m1);
        update_mask(5, src.row(nRow).select<16,1>(2), src.row(nRow+6).select<16,1>(4), t0, t1, m0, m1);
        update_mask(7, src.row(nRow+2).select<16,1>(0), src.row(nRow+4).select<16,1>(6), t0, t1, m0, m1);

        if( (((( m0 | (m0 >> 8)) & 255) != 255).all()) &&
            (((( m1 | (m1 >> 8)) & 255) != 255).all()) )
                continue;

        m0 |= m0 << 16;
        m1 |= m1 << 16;

        vector<int, 16> keyToCheck = 0;
#pragma unroll
        for (int i = 0; i < 16; i++)
            keyToCheck += check(i, m0) + check(i, m1);

        validKey.row(nRow) =  (keyToCheck > 0);

        if ((validKey.row(nRow) == 0).all())
          continue;

        vector<ushort, BLKW*2> keyindex;
        keyindex.select<16,2>(0) = validKey.row(nRow) * posXidx;
        keyindex.select<16,2>(1) = pos(Y) + nRow;

        vector<ushort, 16> widthMask = (keyindex.select<16,2>(0) < maxWidth - 3);
        vector<ushort, 16> heightMask = (keyindex.select<16,2>(1) < maxHeight - 3);
        widthMask *= (keyindex.select<16,2>(0) > minGroupX + 2);
        heightMask *= (keyindex.select<16,2>(1) > minGroupY + 2);
        widthMask *= (keyindex.select<16,2>(0) < maxGroupX - 3);
        heightMask *= (keyindex.select<16,2>(1) < maxGroupY - 3);

        validKey.row(nRow) *= widthMask;
        validKey.row(nRow) *= heightMask;

        while (validKey.row(nRow).any()){
            uint packed = cm_pack_mask(validKey.row(nRow));
            uint fbl = cm_fbl(packed);
            validKey.row(nRow)[fbl] = 0;
            keyout.select<2,1>(totalKey<<1) = keyindex.select<2,1>(fbl<<1);
            totalKey++;
        }
    }
    cm_barrier();

    vector<uint, 1> keyidx = 0;
    vector<uint, 1> ret = 0;
    vector<uint, 8>   slm_AtomicResult;
    vector<ushort, 8> slmOffset(init_offset);

    if (totalKey > 0)
         cm_slm_atomic(slmIdx, ATOMIC_INC, slmOffset, slm_AtomicResult);

    while (curIdx < totalKey)
    {
       write_atomic<ATOMIC_INC, uint, 1>(DstSI, keyidx, ret);
        vector<uint, 2> ss;
        ss[0] = ret[0]*2;
        ss[1] = ret[0]*2+1;
        vector<uint, 2> tmpout = keyout.select<2,1>(curIdx<<1);
        write(DstSI, 1, ss, tmpout);
        curIdx++;
        /*
        if (totalKey - curIdx > 8)
        {
            vector<uint, 1> data = 8;
            write_atomic<ATOMIC_ADD, uint, 1>(DstSI, keyidx, data, ret);
            vector<uint, 16> keyoutidx;
            int startValue = ret[0]*2;
            cmtl::cm_vector_assign(keyoutidx, startValue, 1);
            vector<uint, 16> tmpout = keyout.select<16,1>(curIdx<<1);
            write(DstSI, 1, keyoutidx, tmpout);
            curIdx += 8;
        }
        else
        {
            write_atomic<ATOMIC_INC, uint, 1>(DstSI, keyidx, ret);
            vector<uint, 2> ss;
            ss[0] = ret[0]*2;
            ss[1] = ret[0]*2+1;
            vector<uint, 2> tmpout = keyout.select<2,1>(curIdx<<1);
            write(DstSI, 1, ss, tmpout);
            curIdx++;
        }
        */
    }
}

//
//  Fast feature extractor extended version which support overlap region and two thresholds
//
//////////////////////////////////////////////////////////////////////////////////////////
extern "C" _GENX_MAIN_ void
fastext_GENX(
        SurfaceIndex SrcSI [[type("image2d_t uchar")]],
        SurfaceIndex DstSI [[type("buffer_t")]],   // Keypoint surface index
        SurfaceIndex MaskSI [[type("buffer_t")]],
        SurfaceIndex PositionSI [[type("buffer_t")]],
        int iniThreshold,
        int minThreshold,
        int overlap,
        int cellSize,
        int minXY,
        int srcWidth,
        int srcHeight,
        float scaleFactor,
        int maskCheck,
        int maskStep,
        int monoWidth
     )
{
    vector<short, 2> pos;
    vector<short, 2> groupStartPos;

    groupStartPos(Y) = cm_group_id(Y) * cellSize + minXY;

    vector<uint, 1> groupPositionData;
    read(DWALIGNED(PositionSI), cm_group_id(X)*4, groupPositionData);

    groupStartPos(X) = groupPositionData[0];
    int startPos = groupStartPos(X);

    if (maskCheck)
    {
        uint minX = groupStartPos(X)*scaleFactor;
        uint minY = groupStartPos(Y)*scaleFactor;
        uint maxX = (groupStartPos(X) + cellSize + overlap)*scaleFactor;
        uint maxY = (groupStartPos(Y) + cellSize + overlap)*scaleFactor;

        vector<uint, 4> cornerIdx;
        vector<uchar, 4> maskData;

        cornerIdx[0] = minX + minY*maskStep;
        cornerIdx[1] = maxX + minY*maskStep;
        cornerIdx[2] = minX + maxY*maskStep;
        cornerIdx[3] = maxX + maxY*maskStep;

        read(MaskSI, 0, cornerIdx, maskData);

        if (maskData.all() == 0)
            return;
    }

    pos(X) = groupStartPos(X) + cm_local_id(X) * BLKW;
    pos(Y) = groupStartPos(Y) + cm_local_id(Y) * BLKH;

    cm_slm_init(SLM_SIZE);
    uint slmSum = cm_slm_alloc(SLM_SIZE);

    vector<uint, 8> slmData = 0;
    vector<uint, 8> slmOffset(init_offset);
    cm_slm_write (slmSum, slmOffset, slmData);

    matrix<uchar, 22, 32> srcData;

    read(SrcSI, pos(X)-3, pos(Y)-3, srcData.select<8,1,32,1>(0,0));
    read(SrcSI, pos(X)-3, pos(Y)+5, srcData.select<8,1,32,1>(8,0));
    read(SrcSI, pos(X)-3, pos(Y)+13, srcData.select<6,1,32,1>(16,0));

    extractKeyPoints(srcData, DstSI, slmSum, groupStartPos, overlap, cellSize,
            srcWidth, srcHeight, iniThreshold, minXY, monoWidth);

    cm_barrier();

    vector<uint, 8> data = 0;
    cm_slm_read(slmSum, slmOffset, data);

    if (data[0] == 0)
    {
        extractKeyPoints(srcData, DstSI, slmSum, groupStartPos, overlap, cellSize,
                srcWidth, srcHeight, minThreshold, minXY, monoWidth);
    }
}

