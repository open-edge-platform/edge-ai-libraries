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

#define PI 3.1415926535897932384626433832795
#define BLOCK_PER_THREAD 2
#define BLOCK_WIDTH 16
#define BLOCK_HEIGHT 16

#define THREAD_WIDTH BLOCK_WIDTH * BLOCK_PER_THREAD
#define KEYPOINT_WIDTH 16
#define HALF_PATCH_SIZE 15
#define DESCRIPTOR_WIDTH 32

static vector<uint, BLOCK_WIDTH> imgIdx;

static constexpr float _PI = 3.14159265358979f;
static constexpr float _PI_2 = _PI / 2.0f;
static constexpr float _TWO_PI = 2.0f * _PI;
static constexpr float _INV_TWO_PI = 1.0f / _TWO_PI;
static constexpr float _THREE_PI_2 = 3.0f * _PI_2;

inline _GENX_ vector<float, BLOCK_WIDTH>  _cos (vector<float, BLOCK_WIDTH> v) {

    constexpr float c1 = 0.99940307f;
    constexpr float c2 = -0.49558072f;
    constexpr float c3 = 0.03679168f;

    const vector<float, BLOCK_WIDTH> v2 = v * v;
    return c1 + v2 * (c2 + c3 * v2);
}

inline _GENX_ vector<float, BLOCK_WIDTH> cos(vector<float, BLOCK_WIDTH> v) {
    v = cm_abs(v - cmtl::cm_floor<float, BLOCK_WIDTH>(v * _INV_TWO_PI) * _TWO_PI);
    
    vector<uchar, BLOCK_WIDTH> lpi2 = v < _PI_2;
    vector<uchar, BLOCK_WIDTH> lpi = (v < _PI ) ^ lpi2;
    vector<uchar, BLOCK_WIDTH> l3pi2 = (v < _THREE_PI_2) ^ lpi ^ lpi2;
    vector<uchar, BLOCK_WIDTH> other = !(lpi2 | lpi | l3pi2);

    vector<float, BLOCK_WIDTH> out;

    if (lpi2.any()) {
        out.merge(_cos(v), lpi2);
    }

    if (lpi.any()) {
        out.merge(-_cos(_PI - v), lpi);
    }

    if(l3pi2.any()) {
        out.merge(-_cos(v - _PI), l3pi2);
    }

    if (other.any()) {
        out.merge(_cos(_TWO_PI - v), other);
    }

    return out;
}

inline _GENX_ vector<float, BLOCK_WIDTH> sin(vector<float, BLOCK_WIDTH> v) {
    return cos(_PI_2 - v);
}

#define _DBL_EPSILON 2.2204460492503131e-16f
#define atan2_p1 (0.9997878412794807f*57.29577951308232f)
#define atan2_p3 (-0.3258083974640975f*57.29577951308232f)
#define atan2_p5 (0.1555786518463281f*57.29577951308232f)
#define atan2_p7 (-0.04432655554792128f*57.29577951308232f)

inline vector<float, BLOCK_WIDTH> fastAtan2(
        vector<float, BLOCK_WIDTH> y,
        vector<float, BLOCK_WIDTH> x)
{
    vector<float, BLOCK_WIDTH> ax = cm_abs<float, BLOCK_WIDTH>(x);
    vector<float, BLOCK_WIDTH> ay = cm_abs<float, BLOCK_WIDTH>(y);

    vector<uchar, BLOCK_WIDTH> axgtay = (ax >= ay);
    vector<uchar, BLOCK_WIDTH> other = !axgtay;
    vector<float, BLOCK_WIDTH> a  = 0.f;
    vector<float, BLOCK_WIDTH> c, c2;

    if (axgtay.any())
    {
        c = ay / (ax + _DBL_EPSILON);
        c2 = c*c;
        a.merge((((atan2_p7*c2 + atan2_p5)*c2 + atan2_p3)*c2 + atan2_p1)*c, axgtay);
    }

    if (other.any())
    {
        c = ax / (ay + _DBL_EPSILON);
        c2 = c*c;
        a.merge(90.f - (((atan2_p7*c2 + atan2_p5)*c2 + atan2_p3)*c2 + atan2_p1)*c, other);
    }

    a.merge((180.f - a), (x < 0.f));
    a.merge((360.f - a), (y < 0.f));

    return a;
}

_GENX_ void updateOrientation(
        SurfaceIndex imgSI,
        vector_ref<float, BLOCK_WIDTH*4> keypoint,
        vector<uint, BLOCK_WIDTH> idx,
        vector<int, 16> u_max,
        uint step
        )
{
    vector<int, BLOCK_WIDTH> m_10 = 0;
    vector<int, BLOCK_WIDTH> m_01 = 0;
    vector<uchar, BLOCK_WIDTH> neighbor;

    for (int u = -HALF_PATCH_SIZE; u <= HALF_PATCH_SIZE; ++u) {
        // Opportunity to optimize since the indices are sequential.
        read(imgSI, 0, idx+u, neighbor);
        m_10 += u * neighbor;
    }


    vector<uchar, BLOCK_WIDTH> val_plus;
    vector<uchar, BLOCK_WIDTH> val_minus;
    for (int v = 1; v <= HALF_PATCH_SIZE; ++v)
    {
        // Proceed over the two lines
        vector<int, BLOCK_WIDTH> v_sum = 0;
        int d = u_max[v];
        for (int u = -d; u <= d; ++u)
        {
            read(imgSI, 0, idx + u + v*step, val_plus);
            read(imgSI, 0, idx + u - v*step, val_minus);
            v_sum += vector<int, BLOCK_WIDTH>(val_plus - val_minus);
            m_10 += u * (val_plus + val_minus);
        }
        m_01 += v * v_sum;
    }

    vector<float, BLOCK_WIDTH> angle = fastAtan2(vector<float, BLOCK_WIDTH>(m_01), vector<float, BLOCK_WIDTH>(m_10));
    keypoint.select<BLOCK_WIDTH, 4>(3) = angle;
}

inline _GENX_ vector<uchar, BLOCK_WIDTH> getValue(
        SurfaceIndex ImageSI,
        uint step,
        vector_ref<float, BLOCK_WIDTH> a,
        vector_ref<float, BLOCK_WIDTH> b,
        float patternX,
        float patternY
        )
{
    vector<uint, BLOCK_WIDTH> nIdx;
    vector<uchar, BLOCK_WIDTH> neighbour;

    vector<int, BLOCK_WIDTH> Idx;
    Idx = cm_rnde<int>(patternX * b + patternY * a)*step +
             cm_rnde<int>(patternX * a - patternY * b);

    nIdx = imgIdx + Idx;

    read(ImageSI, 0, nIdx, neighbour);

    return neighbour;
}

_GENX_ void
computeOrbDescriptor(SurfaceIndex GaussianSI,
    SurfaceIndex PatternSI,
    vector_ref<float, BLOCK_WIDTH*4> keypoint,
    uint imgStep,
    matrix_ref<uchar, BLOCK_WIDTH, 32> descT) {
    
    const float floatPI = PI/180.f;
    vector<float, BLOCK_WIDTH> angle = keypoint.select<BLOCK_WIDTH,4>(3)*floatPI;

    vector<float, BLOCK_WIDTH> a = cos(angle);
    vector<float, BLOCK_WIDTH> b = sin(angle);

    matrix<uchar, 32, BLOCK_WIDTH> desc;
    int poffset = 0;

    for (int i = 0; i < 32; i++)
    {
        vector<float, 32> pattern;
        read(PatternSI, poffset, pattern);

        vector<int, BLOCK_WIDTH> t0, t1, val;

        t0 = getValue(GaussianSI, imgStep, a, b, pattern[0] /*x*/, pattern[1] /*y*/);
        t1 = getValue(GaussianSI, imgStep, a, b, pattern[2], pattern[3]);
        val = t0 < t1;

        t0 = getValue(GaussianSI, imgStep, a, b, pattern[4], pattern[5]);
        t1 = getValue(GaussianSI, imgStep, a, b, pattern[6], pattern[7]);
        val |= (t0 < t1) << 1;
        t0 = getValue(GaussianSI, imgStep, a, b, pattern[8], pattern[9]);
        t1 = getValue(GaussianSI, imgStep, a, b, pattern[10], pattern[11]);
        val |= (t0 < t1) << 2;
        t0 = getValue(GaussianSI, imgStep, a, b, pattern[12], pattern[13]);
        t1 = getValue(GaussianSI, imgStep, a, b, pattern[14], pattern[15]);
        val |= (t0 < t1) << 3;
        t0 = getValue(GaussianSI, imgStep, a, b, pattern[16], pattern[17]);
        t1 = getValue(GaussianSI, imgStep, a, b, pattern[18], pattern[19]);
        val |= (t0 < t1) << 4;
        t0 = getValue(GaussianSI, imgStep, a, b, pattern[20], pattern[21]);
        t1 = getValue(GaussianSI, imgStep, a, b, pattern[22], pattern[23]);
        val |= (t0 < t1) << 5;
        t0 = getValue(GaussianSI, imgStep, a, b, pattern[24], pattern[25]);
        t1 = getValue(GaussianSI, imgStep, a, b, pattern[26], pattern[27]);
        val |= (t0 < t1) << 6;;
        t0 = getValue(GaussianSI, imgStep, a, b, pattern[28], pattern[29]);
        t1 = getValue(GaussianSI, imgStep, a, b, pattern[30], pattern[31]);
        val |= (t0 < t1) << 7;;
        desc.row(i) = val;

        poffset+=32*4;
    }

    cmtl::Transpose_16x16(desc.select<16,1,16,1>(0,0), descT.select<16,1,16,1>(0,0));
    cmtl::Transpose_16x16(desc.select<16,1,16,1>(16,0), descT.select<16,1,16,1>(0,16));
}

extern "C" _GENX_MAIN_ void
orb_descriptor_GENX(
        SurfaceIndex KeySI [[type("buffer_t")]],
        SurfaceIndex ImageSI [[type("buffer_t")]],
        SurfaceIndex GaussianSI [[type("buffer_t")]],
        SurfaceIndex PatternSI [[type("buffer_t")]],
        SurfaceIndex DescriptorSI [[type("buffer_t")]],
        SurfaceIndex UmaxSI [[type("buffer_t")]],
        uint totalKeypoints,
        uint imgStep,
        uint outBaseOffset
        )
{
    int pos, descpos, keyidx;

    pos = keyidx = get_thread_origin_x();
    descpos = pos*THREAD_WIDTH * DESCRIPTOR_WIDTH;
    pos *=  THREAD_WIDTH * KEYPOINT_WIDTH;
    keyidx *= THREAD_WIDTH;

    vector<int, 16> umax;
    vector<float, BLOCK_WIDTH*4> keypoint;

    read(UmaxSI, 0, umax);

    for (int blk = 0; blk < BLOCK_PER_THREAD; blk++)
    {
        pos += blk*BLOCK_WIDTH*KEYPOINT_WIDTH;

        //We want to deal with 16 keypoints at a time. 
        //Below we read 64 floats (16 x 4 floats per keypoint)
        //split into two reads, because block read limit is 128 bytes.
        read(DWALIGNED(KeySI), pos, keypoint.select<32,1>(0));
        read(DWALIGNED(KeySI), pos+128, keypoint.select<32,1>(32));

        imgIdx = cm_rnde<uint>(keypoint.select<BLOCK_WIDTH,4>(0)) + cm_rnde<uint>(keypoint.select<BLOCK_WIDTH,4>(1))*imgStep;

        updateOrientation(ImageSI, keypoint, imgIdx, umax, imgStep);

        //Write keypoint data with computed orientation
        write(KeySI, pos, keypoint.select<32,1>(0));
        write(KeySI, pos+128, keypoint.select<32,1>(32));

        matrix<uchar, BLOCK_WIDTH, 32> descT;
        computeOrbDescriptor(GaussianSI, PatternSI, keypoint, imgStep, descT);

#pragma unroll
        for (int j = 0; j < 4; j++)
        {
            if (totalKeypoints - keyidx >= 4)
            {
                vector<uchar, 128> out = descT.select<4,1,32,1>(j*4,0);

                // Each times write 4 keypoints descriptor
                write(DescriptorSI, descpos + outBaseOffset, out);
                descpos+=128;
                keyidx+=4;
            }
            else if (totalKeypoints - keyidx < 4) {

                int remainder = totalKeypoints - keyidx;
                for (int k = 0; k < remainder; k++)
                {
                    vector<uchar, 32> out = descT.select<1,1,32,1>(j*4+k,0);
                    write(DescriptorSI, descpos + outBaseOffset, out);
                    descpos+=32;
                    keyidx++;
                }
            }
        }
    }
}
