// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#ifndef __ORBEXTRACTOR_TESTUTIL_H__
#define __ORBEXTRACTOR_TESTUTIL_H__

#include <limits.h>
#include <math.h>
#include <string>
#include <iostream>
#include <cmath>
#include <opencv2/core/fast_math.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/imgcodecs.hpp>

using namespace std;

#define DATAPATH string("/opt/intel/orb_lze/tests")

const float factorPI = (float)(CV_PI/180.f);
const int HALF_PATCH_SIZE = 15;
const int EDGE_THRESHOLD = 19;

namespace util
{
    static constexpr float _PI = 3.14159265358979f;
    static constexpr float _PI_2 = _PI / 2.0f;
    static constexpr float _TWO_PI = 2.0f * _PI;
    static constexpr float _INV_TWO_PI = 1.0f / _TWO_PI;
    static constexpr float _THREE_PI_2 = 3.0f * _PI_2;

inline float _cos(float v)
{
    constexpr float c1 = 0.99940307f;
    constexpr float c2 = -0.49558072f;
    constexpr float c3 = 0.03679168f;

    const float v2 = v * v;
    return c1 + v2 * (c2 + c3 * v2);
}

inline float cos(float v)
{
    v = abs(v - cvFloor(v * _INV_TWO_PI) * _TWO_PI);

    if (v < _PI_2) {
        return _cos(v);
    }
    else if (v < _PI) {
        return -_cos(_PI - v);
    }
    else if (v < _THREE_PI_2) {
        return -_cos(v - _PI);
    }
    else {
        return _cos(_TWO_PI - v);
    }
}

inline float sin(float v) 
{
    return util::cos(_PI_2 - v);
}
};

void readTestInput(cv::Mat& src, string filename, const int *size, const int dim, int type) 
{
    FILE *fp = NULL;
    char *imagedata = NULL;

    //Create Opencv mat structure for image dimension. For 8 bit bayer, type should be CV_8UC1.
    src.create(dim, size, type);
    int framesize = src.total() * src.elemSize();

    //Open raw Bayer image.
    fp = fopen(filename.c_str(), "rb");

    //Memory allocation for bayer image data buffer.
    imagedata = (char*) malloc (sizeof(char) * framesize);

    //Read image data and store in buffer.
    int re = fread(imagedata, sizeof(char), framesize, fp);

    memcpy(src.data, imagedata, framesize);

    free(imagedata);

    fclose(fp);
}

template<typename T>
void readTestInput(T* src, string filename, int size) 
{
    FILE *fp = NULL;
    T *imagedata = NULL;

    //Open raw Bayer image.
    fp = fopen(filename.c_str(), "rb");

    //Read image data and store in buffer.
    fread(src, sizeof(T), size, fp);

    fclose(fp);
}

void writeTestOutput(cv::Mat& src, string filename)
{
    FILE *fp = NULL;
    char *imagedata = NULL;

    //Create Opencv mat structure for image dimension. For 8 bit bayer, type should be CV_8UC1.
    int framesize = src.total() * src.elemSize();

    //Open raw Bayer image.
    fp = fopen(filename.c_str(), "wb");

    //Write image data and store in buffer.
    fwrite(src.data, sizeof(char), framesize, fp);

    fclose(fp);
}

bool cmp8U(uchar * gpu, uchar * cpu, int size, int delta) 
{
    for(int i=0; i<size; i++)
    {
        if(abs(cpu[i]-gpu[i])>delta)
        {
            return false;
        }
    }
    return true;
}

void computeOrbDescriptor(const cv::KeyPoint & kpt, const cv::Mat& img, const cv::Point * pattern, uchar *desc) ;

void orbDescCPU(cv::Mat& image, vector<cv::KeyPoint> & keypoints, cv::Mat & descriptors, const vector<cv::Point>& pattern, int descriImgsize) 
{
    descriptors = cv::Mat::zeros((int)keypoints.size(), descriImgsize, CV_8UC1);

    for (size_t i = 0; i < keypoints.size(); i++)
    {
        computeOrbDescriptor(keypoints[i], image, &pattern[0], descriptors.ptr((int)i));
    }
}

void computeOrbDescriptor(const cv::KeyPoint & kpt, const cv::Mat& img, const cv::Point * pattern, uchar *desc) 
{
    float angle = (float)kpt.angle*factorPI;
    float a = util::cos(angle);
    float b = util::sin(angle);

    const uchar* center = &img.at<uchar>(cvRound(kpt.pt.y), cvRound(kpt.pt.x));
    const int step = (int)img.step;

#define GET_VALUE(idx) \
    center[cvRound(pattern[idx].x*b + pattern[idx].y*a)*step + \
    cvRound(pattern[idx].x*a - pattern[idx].y*b)]

    for (int i = 0; i < 32; ++i, pattern += 16)
    {
        int t0, t1, val;
        t0 = GET_VALUE(0); t1 = GET_VALUE(1);
        val = t0 < t1;
        t0 = GET_VALUE(2); t1 = GET_VALUE(3);
        val |= (t0 < t1) << 1;
        t0 = GET_VALUE(4); t1 = GET_VALUE(5);
        val |= (t0 < t1) << 2;
        t0 = GET_VALUE(6); t1 = GET_VALUE(7);
        val |= (t0 < t1) << 3;
        t0 = GET_VALUE(8); t1 = GET_VALUE(9);
        val |= (t0 < t1) << 4;
        t0 = GET_VALUE(10); t1 = GET_VALUE(11);
        val |= (t0 < t1) << 5;
        t0 = GET_VALUE(12); t1 = GET_VALUE(13);
        val |= (t0 < t1) << 6;
        t0 = GET_VALUE(14); t1 = GET_VALUE(15);
        val |= (t0 < t1) << 7;
        desc[i] = (uchar)val;
    }
#undef GET_VALUE
}

static float IC_Angle(const cv::Mat& image, cv::Point2f pt,  const vector<int> & u_max);

void computeOrientation(const cv::Mat &image, vector<cv::KeyPoint> &keypoints, const vector<int> & umax) 
{
    for (vector<cv::KeyPoint>::iterator keypoint = keypoints.begin(),
            keypointEnd = keypoints.end(); keypoint != keypointEnd; ++keypoint)
    {
        keypoint->angle = IC_Angle(image, keypoint->pt, umax);
    }
}

static float IC_Angle(const cv::Mat& image, cv::Point2f pt,  const vector<int> & u_max) 
{
    int m_01 = 0, m_10 = 0;

    const uchar* center = &image.at<uchar> (cvRound(pt.y), cvRound(pt.x));

    // Treat the center line differently, v=0
    for (int u = -HALF_PATCH_SIZE; u <= HALF_PATCH_SIZE; ++u)
        m_10 += u * center[u];

    // Go line by line in the circuI853lar patch
    int step = (int)image.step1();
    int cnt = 0;
    for (int v = 1; v <= HALF_PATCH_SIZE; ++v)
    {
        // Proceed over the two lines
        int v_sum = 0;
        int d = u_max[v];
        int cn = 0;
        for (int u = -d; u <= d; ++u)
        {
            int val_plus = center[u + v*step], val_minus = center[u - v*step];
            v_sum += (val_plus - val_minus);
            m_10 += u * (val_plus + val_minus);
            cn++;
        }
        m_01 += v * v_sum;
        cnt++;
    }

    return cv::fastAtan2((float)m_01, (float)m_10);
}

#endif //_ORBEXTRACTOR_TESTUTIL_H__
