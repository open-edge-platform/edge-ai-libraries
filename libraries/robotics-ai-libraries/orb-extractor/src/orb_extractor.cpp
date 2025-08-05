// SPDX-License-Identifier: BSD-3-Clause
/*******************************************************************************

                          License Agreement
               For Open Source Computer Vision Library
                       (3-clause BSD License)

Copyright (C) 2009, Willow Garage Inc., all rights reserved.

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

  * Redistributions of source code must retain the above copyright notice,
    this list of conditions and the following disclaimer.

  * Redistributions in binary form must reproduce the above copyright notice,
    this list of conditions and the following disclaimer in the documentation
    and/or other materials provided with the distribution.

  * Neither the names of the copyright holders nor the names of the contributors
    may be used to endorse or promote products derived from this software
    without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

*******************************************************************************/

#include "orb_extractor.h"
#include "orb_extractor_impl.h"
#include "orb_point_pairs.h"

#ifndef OPENCV_FREE
#include <opencv2/core.hpp>
#endif


template<typename pt>
struct cmp_pt
{
    bool operator()(const pt&a, const pt&b) const
    {
        return a.pt.y < b.pt.y || (a.pt.y == b.pt.y && a.pt.x < b.pt.x);
    }
};

orb_extractor::orb_extractor(const unsigned int max_num_keypts, const float scale_factor, const unsigned int num_levels,
                             const unsigned int ini_fast_thr, const unsigned int min_fast_thr, const unsigned int no_of_cameras,
                             const std::vector<std::vector<float>>& mask_rects)
{
    extractor_impl = new orb_extractor_impl();

    if (num_levels > extractor_impl->max_num_pyramid_levels)
        throw std::invalid_argument("Max allowed levels = "+std::to_string(extractor_impl->max_num_pyramid_levels));

    // initialize parameters  // FIXME, do it using a function
    extractor_impl->max_num_keypts_ = max_num_keypts;
    extractor_impl->scale_factor_ = scale_factor;
    extractor_impl->num_levels_ = num_levels;
    extractor_impl->ini_fast_thr_= ini_fast_thr;
    extractor_impl->no_of_cameras_= no_of_cameras;
    extractor_impl->min_fast_thr_ = min_fast_thr;
    extractor_impl->initialize();

}

orb_extractor::~orb_extractor()
{
    try {
           delete extractor_impl;
        }
        catch(const std::runtime_error& e)
        {
           std::cerr << "Caught runtime exception: " << e.what() << std::endl;
        }
}

// stereo input or mono input orb extract
#ifdef OPENCV_FREE
void orb_extractor::extract( const std::vector<Mat2d>& in_images, const std::vector<Mat2d>& in_image_mask,
                            std::vector<std::vector<KeyPoint>>& keypts,
                            std::vector<Mat2d>& out_descriptors
                           )
{
     if (in_images.size() > 1)
     {
          extractor_impl->extract(in_images, in_image_mask, keypts, out_descriptors);
     }
     else
     {
         extractor_impl->extract(in_images, in_image_mask, keypts.at(0), out_descriptors);
     }
}
#else
void orb_extractor::extract( const cv::_InputArray& in_images, const cv::_InputArray& in_image_mask,
                              std::vector<std::vector<KeyType>>& keypts,
                              const cv::_OutputArray& out_descriptors
                            )
{
     int type =  in_images.kind();
     cv::Size siz  = in_images.size();
     if( siz.width > 1)
     {
         extractor_impl->extract(in_images, in_image_mask, keypts, out_descriptors);
     }
     else
     {
         extractor_impl->extract(in_images, in_image_mask, keypts.at(0), out_descriptors);
     }
}
#endif

// multi camera input orb extract
template<typename InT, typename OutT>
void orb_extractor_impl::extract( const InT& in_images, const InT& in_image_mask,
                                  std::vector<std::vector<KeyType>>& keypts,
                                  OutT& out_descriptors
                                )
{
    orbKernel_->initializeGPU(max_num_keypts_ * no_of_cameras_);

    if (in_images.empty()) {
        return;
    }

    // combine images horizontally
    std::vector<MatType> stereo_images;
    stereo_images.resize(no_of_cameras_);

#ifdef OPENCV_FREE
    stereo_images = in_images;
#else
    in_images.getMatVector(stereo_images);
#endif

    int rows  = std::max(stereo_images.at(0).rows, stereo_images.at(1).rows);
    int cols = 0;
    for( int i = 0; i < no_of_cameras_; i++)
    {
       cols += stereo_images.at(i).cols;
    }

    //estimate gpu buffer size
    if( max_fast_keypoints_ == 0)
       calc_gpu_buffer_size((cols/no_of_cameras_), rows, no_of_cameras_);
#ifdef OPENCV_FREE
    MatType image (rows, cols);
#else
    MatType image (rows, cols, CV_8UC1);
#endif

    copy_to(image, stereo_images.at(0), Point2i(0, 0), Point2i(stereo_images.at(0).cols, stereo_images.at(0).rows));

    for(int i = 1; i < no_of_cameras_; i++)
    {
        copy_to(image, stereo_images.at(i), Point2i((int)stereo_images.at(i-1).cols*i, i-1), Point2i(stereo_images.at(i-1).cols, stereo_images.at(i-1).rows));
    }
#ifndef OPENCV_FREE
    assert(image.type() == CV_8UC1);
#endif

    // build image pyramid
    compute_image_pyramid(image);

    // mask initialization
    if (!mask_is_initialized_ && !mask_rects_.empty()) {
        create_rectangle_mask(image.cols, image.rows);
        mask_is_initialized_ = true;
    }

    std::vector<std::vector<gpu::PartKey>> gpu_raw_keypts, l_gpu_raw_keypts, r_gpu_raw_keypts, gpu_all_keypts;

    // select mask to use
    if (!in_image_mask.empty()) {
        // Use image_mask if it is available
#ifdef OPENCV_FREE
        const auto image_mask = in_image_mask.at(0);
#else
        const auto image_mask = in_image_mask.getMat();
        assert(image_mask.type() == CV_8UC1);
#endif
        compute_fast_keypoints(gpu_raw_keypts, image_mask, no_of_cameras_);
    }
    else if (!rect_mask_.empty()) {
        // Use rectangle mask if it is available and image_mask is not used
#ifndef OPENCV_FREE
        assert(rect_mask_.type() == CV_8UC1);
#endif
        compute_fast_keypoints(gpu_raw_keypts, rect_mask_, no_of_cameras_);
    }
    else {
        // Do not use any mask if all masks are unavailable
        compute_fast_keypoints(gpu_raw_keypts, MatType(), no_of_cameras_);
    }

    for (unsigned int level = 0; level < num_levels_; ++level) {
        orbKernel_->gaussianBlur(gpu_pyramid_image_.at(level),
                gpu_gaussian_image_.at(level), 7, 2);
    }
    orbKernel_->execute(gpu::kCmdList0);

    std::vector<std::vector<std::vector<gpu::PartKey>>> imgs_gpu_raw_keypts;

    //initilize with no of cameras
    imgs_gpu_raw_keypts.resize(no_of_cameras_);
    for( int j = 0; j < no_of_cameras_; j++)
    {
        auto& gpu_keypts = imgs_gpu_raw_keypts.at(j);
        gpu_keypts.resize(num_levels_);
    }

    int img1_cnt = 0;

    for (unsigned int level = 0; level < num_levels_; ++level)
    {
        int width = gpu_pyramid_image_.at(level).width() / no_of_cameras_;
        int min_width = 0;
        int max_width = width;

        auto& r_gpu_keypts = gpu_raw_keypts.at(level);

        for( int j = 0; j < no_of_cameras_; j++)
        {
            auto& gpu_keypts = imgs_gpu_raw_keypts.at(j);

            auto& i_gpu_keypts = gpu_keypts.at(level);
            i_gpu_keypts.reserve(gpu_keypts.size()/no_of_cameras_);

            max_width = width * (j+1);
            img1_cnt= 0;

            for(int i = 0; i < r_gpu_keypts.size(); i++ )
            {
                if((r_gpu_keypts.at(i).pt.x > min_width) && (r_gpu_keypts.at(i).pt.x < max_width))
                {
                    if( j == 0)
                    {
                        i_gpu_keypts.push_back(r_gpu_keypts.at(i));
                    }
                    else
                    {
                        r_gpu_keypts.at(i).pt.x -= min_width;
                        i_gpu_keypts.push_back(r_gpu_keypts.at(i));
                    }
                    img1_cnt++;
                }
            }
            min_width = max_width;
        }
    }

    std::vector<std::vector<int>> max_x_border_store;
    max_x_border_store.resize(num_levels_);
    std::vector<int> keypts_cnt;
    keypts_cnt.resize(num_levels_);

    compute_keypoints_oct_trees(imgs_gpu_raw_keypts, gpu_all_keypts, max_x_border_store, keypts_cnt);

    MatType descriptors;

    unsigned int num_keypts = 0;
    for (unsigned int level = 0; level < num_levels_; ++level) {
        num_keypts += gpu_all_keypts.at(level).size();
    }
    if (num_keypts == 0) {
#ifdef OPENCV_FREE
        out_descriptors.clear();
#else
        out_descriptors.release();
#endif

    }
    else {
#ifdef OPENCV_FREE
        descriptors.resize(num_keypts, 32);
#else
        descriptors.release();
        descriptors.create(num_keypts, 32, CV_8U);
#endif
    }

    std::vector<std::vector<KeyType>> all_keypts;
    all_keypts.resize(num_levels_);
    unsigned int descriptor_offset = 0;

    for (unsigned int level = 0; level < num_levels_; ++level) {
        auto& gpu_keypts_at_level = gpu_all_keypts.at(level);
        const auto num_keypts_at_level = gpu_keypts_at_level.size();
        auto& cv_keypts_at_level = all_keypts.at(level);

        const unsigned int scaled_patch_size = fast_patch_size_ * scale_factors_.at(level);

        orbKernel_->orbDescriptor(gpu_keypts_at_level, gpu_pyramid_buffer_.at(level),
                gpu_gaussian_image_.at(level),
                gpu_orb_pattern_buffer_,
                gpu_u_max_buffer_,
                cv_keypts_at_level, level, scaled_patch_size, descriptors, descriptor_offset,
                (num_keypts_per_level_.at(level)*no_of_cameras_));

        descriptor_offset += num_keypts_at_level * 32;
    }

    orbKernel_->execute(gpu::kCmdList1);

#ifdef OPENCV_FREE
    std::vector<MatType>& stereo_out_descriptors = out_descriptors;
    stereo_out_descriptors.resize(no_of_cameras_);
#else
    std::vector<MatType>& stereo_out_descriptors = *(std::vector<cv::Mat>*)out_descriptors.getObj();
    stereo_out_descriptors.resize(no_of_cameras_);
#endif

    for(int no_img = 0; no_img < no_of_cameras_; no_img++)
    {
#ifdef OPENCV_FREE
        stereo_out_descriptors.at(no_img).resize(keypts_cnt.at(no_img), 32);
#else
        stereo_out_descriptors.at(no_img).create(keypts_cnt.at(no_img), 32, CV_8U);
#endif
        auto &i_keypts =  keypts.at(no_img);
        i_keypts.clear();
        i_keypts.resize(keypts_cnt.at(no_img));
    }

    std::vector<int> k_cnt;
    k_cnt.resize(no_of_cameras_);
    k_cnt = {0};

    int cnt = 0;
    float scale_at_level = 0.0;

    int min_x_border = 0;
    KeyType tmp;

    for (unsigned int level = 0; level < num_levels_; ++level) {

        auto& keypts_at_level = all_keypts.at(level);
        scale_at_level = scale_factors_.at(level);
        auto max_x_border = max_x_border_store.at(level);
        min_x_border = 0;

        for( int j = 0; j < no_of_cameras_; j++)
        {
            int max_x = max_x_border[j];
            auto &i_keypts =  keypts.at(j);

            int i_cnt = k_cnt[j];

            for(std::vector<KeyType>::iterator keyptsf = keypts_at_level.begin(), keypointEnd = keypts_at_level.end(); keyptsf != keypointEnd; ++keyptsf)
            {
#ifdef OPENCV_FREE
               if((keyptsf->x > min_x_border) && (keyptsf->x < max_x))
                {
                    if( j != 0)
                    {
                        keyptsf->x = keyptsf->x - (min_x_border - orb_patch_radius_);
                    }
                    tmp.x = keyptsf->x * scale_at_level;
                    tmp.y = keyptsf->y * scale_at_level;
                    tmp.size = keyptsf->size;
                    tmp.angle = keyptsf->angle;
                    tmp.response = keyptsf->response;
                    tmp.octave = keyptsf->octave;
                    i_keypts.at(i_cnt) = tmp;
                    std::memcpy(stereo_out_descriptors.at(j).row(i_cnt), descriptors.row(cnt), descriptors.cols);
                    i_cnt++;
                    cnt++;
                }
#else
               if((keyptsf->pt.x > min_x_border) && (keyptsf->pt.x < max_x))
                {
                    if( j != 0)
                    {
                        keyptsf->pt.x = keyptsf->pt.x - (min_x_border - orb_patch_radius_);
                    }
                    tmp.size = keyptsf->size;
                    tmp.angle = keyptsf->angle;
                    tmp.response = keyptsf->response;
                    tmp.octave = keyptsf->octave;
                    tmp.pt = keyptsf->pt  * scale_at_level;
                    i_keypts.at(i_cnt) = tmp;
                    std::memcpy(stereo_out_descriptors.at(j).row(i_cnt).data, descriptors.row(cnt).data, descriptors.cols);
                    i_cnt++;
                    cnt++;
                }
#endif
            }
        k_cnt[j] = i_cnt;
        min_x_border = max_x_border[j];
        }
    }
#ifdef DEBUG_LOG
    std::cout<<"\n";
    for(int i = 0; i < no_of_cameras_; i++)
    {
        std::cout << "img:" << i+1 << " keypts_size:" << keypts.at(i).size() << "\n";
    }
#endif
}

//mono orb_extract
template<typename InT, typename OutT>
void orb_extractor_impl::extract(const InT& in_image, const InT& in_image_mask,
                            std::vector<KeyType>& keypts, OutT& out_descriptors)
{
    if (in_image.empty()) {
        return;
    }

    // get cv::Mat of image
#ifdef OPENCV_FREE
    const auto image = in_image.at(0);
#else
    std::vector<cv::Mat> images;
    images.resize(no_of_cameras_);
    in_image.getMatVector(images);
    cv::Mat image = images.at(0);
    //const auto image = in_image.getMat();
    assert(image.type() == CV_8UC1);
#endif

    int rows  = image.rows;
    int cols = image.cols;

    //estimate gpu buffer size
    if( max_fast_keypoints_ == 0)
       calc_gpu_buffer_size(cols, rows, no_of_cameras_);

    // build image pyramid
    compute_image_pyramid(image);

    // mask initialization
    if (!mask_is_initialized_ && !mask_rects_.empty()) {
        create_rectangle_mask(image.cols, image.rows);
        mask_is_initialized_ = true;
    }

    std::vector<std::vector<gpu::PartKey>> gpu_raw_keypts, gpu_all_keypts;

    // select mask to use
    if (!in_image_mask.empty()) {
        // Use image_mask if it is available
#ifdef OPENCV_FREE
        const auto image_mask = in_image_mask.at(0);
#else
        const auto image_mask = in_image_mask.getMat();
        assert(image_mask.type() == CV_8UC1);
#endif

        compute_fast_keypoints(gpu_raw_keypts, image_mask, no_of_cameras_);
    }
    else if (!rect_mask_.empty()) {
        // Use rectangle mask if it is available and image_mask is not used
#ifndef OPENCV_FREE
        assert(rect_mask_.type() == CV_8UC1);
#endif
        compute_fast_keypoints(gpu_raw_keypts, rect_mask_, no_of_cameras_);
    }
    else {
        // Do not use any mask if all masks are unavailable
        compute_fast_keypoints(gpu_raw_keypts, MatType(), no_of_cameras_);
    }


    for (unsigned int level = 0; level < num_levels_; ++level) {
        orbKernel_->gaussianBlur(gpu_pyramid_image_.at(level),
                gpu_gaussian_image_.at(level), 7, 2);
    }

    orbKernel_->execute(gpu::kCmdList0);

    compute_keypoints_oct_tree(gpu_raw_keypts, gpu_all_keypts);

    MatType descriptors;

    unsigned int num_keypts = 0;
    for (unsigned int level = 0; level < num_levels_; ++level) {
        num_keypts += gpu_all_keypts.at(level).size();
    }
    if (num_keypts == 0) {
#ifdef OPENCV_FREE
        out_descriptors.clear();
#else
        out_descriptors.release();
#endif
    }
    else {
#ifdef OPENCV_FREE
        out_descriptors.clear();
        out_descriptors.resize(1);
        out_descriptors[0].resize(num_keypts, 32);
        descriptors.resize(num_keypts, 32);
#else
        out_descriptors.release();
        std::vector<cv::Mat>& arr_descriptors = *(std::vector<cv::Mat>*)out_descriptors.getObj();
        arr_descriptors.resize(no_of_cameras_);
        arr_descriptors[0].create(num_keypts, 32, CV_8U);
        descriptors = arr_descriptors[0];
#endif
    }

    keypts.clear();
    keypts.reserve(num_keypts);

    std::vector<std::vector<KeyType>> all_keypts;
    all_keypts.resize(num_levels_);

    unsigned int descriptor_offset = 0;
    for (unsigned int level = 0; level < num_levels_; ++level) {
        auto& gpu_keypts_at_level = gpu_all_keypts.at(level);
        const auto num_keypts_at_level = gpu_keypts_at_level.size();
        auto& cv_keypts_at_level = all_keypts.at(level);

        const unsigned int scaled_patch_size = fast_patch_size_
            * scale_factors_.at(level);

        orbKernel_->orbDescriptor(gpu_keypts_at_level, gpu_pyramid_buffer_.at(level),
                gpu_gaussian_image_.at(level),
                gpu_orb_pattern_buffer_,
                gpu_u_max_buffer_,
                cv_keypts_at_level, level, scaled_patch_size, descriptors, descriptor_offset,
                num_keypts_per_level_.at(level));

        descriptor_offset += num_keypts_at_level * 32;

    }

    orbKernel_->execute(gpu::kCmdList1);

    for (unsigned int level = 0; level < num_levels_; ++level) {

        auto& keypts_at_level = all_keypts.at(level);

        correct_keypoint_scale(keypts_at_level, level);

        keypts.insert(keypts.end(), keypts_at_level.begin(), keypts_at_level.end());
    }
#ifdef OPENCV_FREE
    for(int i = 0; i < keypts.size(); i++)
    {
        std::memcpy(out_descriptors.at(0).row(i), descriptors.row(i), descriptors.cols);
    }
#endif


#ifdef DEBUG_LOG
    std::cout << " mono: keypt_size:"<< keypts.size() <<"\n";
#endif
}

unsigned int orb_extractor::get_max_num_keypoints() const {
    return extractor_impl->max_num_keypts_;
}

void orb_extractor::set_max_num_keypoints(const unsigned int max_num_keypts) {

    if (extractor_impl->max_num_keypts_ == max_num_keypts)
        return;

    extractor_impl->max_num_keypts_ = max_num_keypts;
    extractor_impl->initialize();
}

float orb_extractor::get_scale_factor() const {
    return extractor_impl->scale_factor_;
}

void orb_extractor::set_scale_factor(const float scale_factor) {

    if (extractor_impl->scale_factor_ == scale_factor)
        return;

    extractor_impl->scale_factor_ = scale_factor;
    extractor_impl->initialize();
}

unsigned int orb_extractor::get_num_scale_levels() const {
    return extractor_impl->num_levels_;
}

void orb_extractor::set_num_scale_levels(const unsigned int num_levels) {

    if (extractor_impl->num_levels_ == num_levels)
        return;

    extractor_impl->num_levels_ = num_levels;
    extractor_impl->initialize();
}

unsigned int orb_extractor::get_initial_fast_threshold() const {
    return extractor_impl->ini_fast_thr_;
}

void orb_extractor::set_initial_fast_threshold(const unsigned int initial_fast_threshold) {
    extractor_impl->ini_fast_thr_ = initial_fast_threshold;
}

unsigned int orb_extractor::get_minimum_fast_threshold() const {
    return extractor_impl->min_fast_thr_;
}

void orb_extractor::set_minimum_fast_threshold(const unsigned int minimum_fast_threshold) {
    extractor_impl->min_fast_thr_ = minimum_fast_threshold;
}

void orb_extractor::get_image_pyramid(std::vector<MatType> &image_pyramid)
{
#ifdef OPENCV_FREE
    for( int level = 0; level < extractor_impl->num_levels_; level++)
    {
         extractor_impl->image_pyramid_.at(level) = MatType( extractor_impl->image_pyramid_.at(level).getHeight(),
                                                             extractor_impl->image_pyramid_.at(level).getWidth(),
                                                             extractor_impl->gpu_pyramid_buffer_.at(level).data());
    }
#endif
  image_pyramid = extractor_impl->image_pyramid_;
}

void orb_extractor::get_image_pyramid(std::vector<std::vector<MatType>> &image_pyramid)
{
#ifdef OPENCV_FREE
   for( int level = 0; level < extractor_impl->num_levels_; level++)
   {
       extractor_impl->image_pyramid_.at(level) = MatType( extractor_impl->image_pyramid_.at(level).getHeight(),
                                                           extractor_impl->image_pyramid_.at(level).getWidth(),
                                                           extractor_impl->gpu_pyramid_buffer_.at(level).data());
   }
#endif
  if( extractor_impl->no_of_cameras_ == 1)
  {
    image_pyramid.resize(extractor_impl->no_of_cameras_);
    image_pyramid.at(extractor_impl->no_of_cameras_-1) = extractor_impl->image_pyramid_;
  }
  else
  {
    image_pyramid.resize(extractor_impl->no_of_cameras_);
    for(int cam_id = 0; cam_id < extractor_impl->no_of_cameras_; cam_id++)
    {
      image_pyramid.at(cam_id).resize(extractor_impl->num_levels_);
      std::vector<MatType>& imgs = image_pyramid.at(cam_id);

      for(int level = 0; level < extractor_impl->num_levels_; level++)
      {
        int cols = extractor_impl->image_pyramid_.at(level).cols/extractor_impl->no_of_cameras_;
        int rows = extractor_impl->image_pyramid_.at(level).rows;
#ifdef OPENCV_FREE
        imgs.at(level) = MatType(rows, cols);
#else
        imgs.at(level) = MatType(rows, cols, CV_8UC1);
#endif
        extractor_impl->copy_to_single_img( imgs.at(level), extractor_impl->image_pyramid_.at(level), Point2i(cols*cam_id, 0));
      }
    }
  }
}

void orb_extractor::set_gpu_kernel_path(std::string path)
{
    extractor_impl->set_kernel_path(std::move(path));
    // FIXME // Create setKernelPath in impl
   //orbKernel_->setKernelPath(extractor_impl->gpu_kernel_path_);
}

std::vector<float> orb_extractor::get_scale_factors() const {
    return extractor_impl->scale_factors_;
}

std::vector<float> orb_extractor::get_inv_scale_factors() const {
    return extractor_impl->inv_scale_factors_;
}

std::vector<float> orb_extractor::get_level_sigma_sq() const {
    return extractor_impl->level_sigma_sq_;
}

std::vector<float> orb_extractor::get_inv_level_sigma_sq() const {
    return extractor_impl->inv_level_sigma_sq_;
}

void orb_extractor_impl::set_kernel_path(std::string path)
{
   gpu_kernel_path_ = path;
   orbKernel_->setKernelPath(std::move(path));
}

void orb_extractor_impl::initialize() {
    // compute scale pyramid information
    calc_scale_factors();

    // resize buffers according to the number of levels
    image_pyramid_.resize(num_levels_);

    gpu_pyramid_image_.resize(num_levels_);
    gpu_pyramid_buffer_.resize(num_levels_);
    gpu_gaussian_image_.resize(num_levels_);

    for (int i = 0; i < num_levels_; i++)
    {
      gpu_pyramid_image_.at(i).setDeviceBase(device_base_);
      gpu_pyramid_buffer_.at(i).setDeviceBase(device_base_);
      gpu_gaussian_image_.at(i).setDeviceBase(device_base_);

    }

    num_keypts_per_level_.resize(num_levels_);

    // compute the desired number of keypoints per scale
    double desired_num_keypts_per_scale
        = max_num_keypts_ * (1.0 - 1.0 / scale_factor_)
          / (1.0 - std::pow(1.0 / scale_factor_, static_cast<double>(num_levels_)));
    unsigned int total_num_keypts = 0;
    for (unsigned int level = 0; level < num_levels_ - 1; ++level) {
        num_keypts_per_level_.at(level) = std::round(desired_num_keypts_per_scale);
        total_num_keypts += num_keypts_per_level_.at(level);
        desired_num_keypts_per_scale *= 1.0 / scale_factor_;
    }
    num_keypts_per_level_.at(num_levels_ - 1) = std::max(static_cast<int>(max_num_keypts_) - static_cast<int>(total_num_keypts), 0);

    // Preparate  for computation of orientation
    u_max_.resize(fast_half_patch_size_ + 1);
    const unsigned int vmax = std::floor(fast_half_patch_size_ * std::sqrt(2.0) / 2 + 1);
    const unsigned int vmin = std::ceil(fast_half_patch_size_ * std::sqrt(2.0) / 2);
    for (unsigned int v = 0; v <= vmax; ++v) {
        u_max_.at(v) = std::round(std::sqrt(fast_half_patch_size_ * fast_half_patch_size_ - v * v));
    }
    for (unsigned int v = fast_half_patch_size_, v0 = 0; vmin <= v; --v) {
        while (u_max_.at(v0) == u_max_.at(v0 + 1)) {
            ++v0;
        }
        u_max_.at(v) = v0;
        ++v0;
    }

    gpu_u_max_buffer_.resize(u_max_.size());
    gpu_u_max_buffer_.upload(u_max_.data(), gpu::kImmediate);

    gpu_orb_pattern_buffer_.resize(256 * 4);
    gpu_orb_pattern_buffer_.upload(&orb_point_pairs, gpu::kImmediate);

    orbKernel_->initializeGPU(max_num_keypts_);
}

//void orb_extractor_impl::gpu_initialize(cv::Mat image)
void orb_extractor_impl::gpu_initialize(const MatType& image)
{
    auto total_levels = num_levels_;

    for (unsigned int i = 0; i < total_levels; ++i) {
        const double scale = scale_factors_.at(i);

        const size_t width = std::round(image.cols * 1.0 / scale);
        const size_t height = std::round(image.rows * 1.0 / scale);

        gpu_pyramid_buffer_.at(i).resize(width, height);
        gpu_pyramid_image_.at(i).resize(width, height);
        gpu_gaussian_image_.at(i).resize(width, height);
#ifdef OPENCV_FREE
        image_pyramid_.at(i) = MatType(height, width);
#else
        const cv::Size sz(std::round(image.cols * 1.0 / scale), std::round(image.rows * 1.0 / scale));
        image_pyramid_.at(i) = MatType(sz, CV_8U, gpu_pyramid_buffer_.at(i).raw());
#endif
    }

    gpu_initialized_ = true;
}

void orb_extractor_impl::calc_scale_factors() {

    std::vector<float> scale_factors(num_levels_, 1.0);
    for (unsigned int level = 1; level < num_levels_; ++level) {
        scale_factors.at(level) = scale_factor_ * scale_factors.at(level - 1);
    }

    std::vector<float> inv_scale_factors(num_levels_, 1.0);
    for (unsigned int level = 1; level < num_levels_; ++level) {
        inv_scale_factors.at(level) = (1.0f / scale_factor_) * inv_scale_factors.at(level - 1);
    }

    float scale_factor_at_level = 1.0;
    std::vector<float> level_sigma_sq(num_levels_, 1.0);
    for (unsigned int level = 1; level < num_levels_; ++level) {
        scale_factor_at_level = scale_factor_ * scale_factor_at_level;
        level_sigma_sq.at(level) = scale_factor_at_level * scale_factor_at_level;
    }

    scale_factor_at_level = 1.0;
    std::vector<float> inv_level_sigma_sq(num_levels_, 1.0);
    for (unsigned int level = 1; level < num_levels_; ++level) {
        scale_factor_at_level = scale_factor_ * scale_factor_at_level;
        inv_level_sigma_sq.at(level) = 1.0f / (scale_factor_at_level * scale_factor_at_level);
    }

    inv_level_sigma_sq_ = std::move(inv_level_sigma_sq);
    level_sigma_sq_ = std::move(level_sigma_sq);
    scale_factors_ = std::move(scale_factors);
    inv_scale_factors_ = std::move(inv_scale_factors);
}

void orb_extractor_impl::copy_to(MatType& dst_image, const MatType& src_image,
                                 const Point2i start, const Point2i end)
{
    auto rows = dst_image.rows;
    auto src_cols = src_image.cols;
    auto type = dst_image.type();

    for (int i = 0; i < rows; i++)
    {
      const decltype(type) *src_row = src_image.ptr<decltype(type)>(i, 0);
      decltype(type) *dst_row = dst_image.ptr<decltype(type)>(i, start.x);

      std::memcpy(dst_row, src_row, src_cols);
    }
}

void orb_extractor_impl::copy_to_single_img(MatType& dst_image, const MatType& src_image,
                                            const Point2i start)
{
    auto rows = dst_image.rows;
    auto src_cols = src_image.cols/no_of_cameras_;
    auto type = dst_image.type();

    for (int i = 0; i < rows; i++)
    {
      const decltype(type) *src_row = src_image.ptr<decltype(type)>(i, start.x);
      decltype(type) *dst_row = dst_image.ptr<decltype(type)>(i, 0);

      std::memcpy(dst_row, src_row, src_cols);
    }
}

void orb_extractor_impl::create_rectangle(MatType& image, const Point2i start, const Point2i end,
                                          const unsigned char pattern)
{
    auto rows = end.y - start.y;
    auto cols = end.x - start.x;
    auto type = image.type();

    for (int i = 0; i < rows; i++)
    {
        decltype(type) *this_row = image.ptr<decltype(type)>(i + start.y, start.x);
        std::memset(this_row, pattern, cols);
    }
}

void orb_extractor_impl::create_rectangle_mask(const unsigned int cols, const unsigned int rows) {
    if (rect_mask_.empty()) {
#ifdef OPENCV_FREE
        rect_mask_ = MatType(rows, cols, 255);
#else
        rect_mask_ = MatType(rows, cols, CV_8UC1, cv::Scalar(255));
#endif
    }
    // draw masks
    for (const auto& mask_rect : mask_rects_) {
        // draw black rectangle
        const unsigned int x_min = std::round(cols * mask_rect.at(0));
        const unsigned int x_max = std::round(cols * mask_rect.at(1));
        const unsigned int y_min = std::round(rows * mask_rect.at(2));
        const unsigned int y_max = std::round(rows * mask_rect.at(3));
        create_rectangle(rect_mask_, Point2i(x_min, y_min), Point2i(x_max, y_max), 0);
    }
}

void orb_extractor_impl::compute_image_pyramid(const MatType& image) {

    if (!gpu_initialized_) {
        gpu_initialize(image);
    }

    //extractor_impl->image_pyramid_.at(0) = image;
#ifdef OPENCV_FREE
    gpu_pyramid_buffer_.at(0).upload(image.data(), gpu::kImmediate);
    gpu_pyramid_image_.at(0).upload(image.data(), gpu::kImmediate);
#else
    gpu_pyramid_buffer_.at(0).upload(image.data, gpu::kImmediate);
    gpu_pyramid_image_.at(0).upload(image.data, gpu::kImmediate);
#endif
    for (unsigned int level = 1; level < num_levels_; ++level) {
        orbKernel_->resize(gpu_pyramid_buffer_.at(level - 1), gpu_pyramid_buffer_.at(level), gpu::kInterpolationLinear);

        gpu_pyramid_image_.at(level).upload(gpu_pyramid_buffer_.at(level));
    }
}

void orb_extractor_impl::compute_fast_keypoints(std::vector<std::vector<gpu::PartKey>> &all_raw_keypts,
                                                const MatType &mask, int num_image)
{
    all_raw_keypts.resize(num_levels_);

    bool mask_check;
    if (mask.empty())
    {
        mask_check = false;
    } else {
        if (((unsigned int)mask.cols != gpu_mask_buffer_.width()) &&
            ((unsigned int)mask.rows != gpu_mask_buffer_.height())) {

            /* Only upload the mask if mask layout change */
            gpu_mask_buffer_.resize(mask.cols, mask.rows);
#ifdef OPENCV_FREE
            gpu_mask_buffer_.upload(mask.data());
#else
            gpu_mask_buffer_.upload(mask.data);
#endif
        }
        mask_check = true;
    }

    for (unsigned int level = 0; level < num_levels_; ++level) {
        const float scale_factor = scale_factors_.at(level);

        auto &keypts_at_level = all_raw_keypts.at(level);

        orbKernel_->fastExt(gpu_pyramid_image_.at(level), gpu_pyramid_buffer_.at(level),
                keypts_at_level, gpu_mask_buffer_, scale_factor, mask_check,
                gpu_mask_buffer_.width(), ini_fast_thr_, min_fast_thr_,
                orb_patch_radius_, orb_overlap_size_, orb_cell_size_, num_image,
                max_nms_keypoints_, max_fast_keypoints_);

    }
}


void orb_extractor_impl::compute_keypoints_oct_trees( std::vector<std::vector<std::vector<gpu::PartKey>>>& imgs_raw_keypts_to_distribute,
                                                      std::vector<std::vector<gpu::PartKey>>& all_keypts,
                                                      std::vector<std::vector<int>>& max_x_border_store,
                                                      std::vector<int>& keypts_cnt) const
{
    all_keypts.resize(num_levels_);
    int keypt_count = 0;

    keypts_cnt.resize(no_of_cameras_);

    for (unsigned int level = 0; level < num_levels_; ++level)
    {
        std::vector<gpu::PartKey>& keypts_at_level = all_keypts.at(level);
        keypts_at_level.reserve(max_num_keypts_ * no_of_cameras_);

        constexpr unsigned int min_border_y = orb_patch_radius_;
        const unsigned int cols = (gpu_pyramid_image_.at(level).width() / no_of_cameras_) + (gpu_pyramid_image_.at(level).width() & 1);
        const unsigned int max_border_y = gpu_pyramid_image_.at(level).height() - orb_patch_radius_;

        auto &max_x = max_x_border_store.at(level);
        max_x.resize(no_of_cameras_);

        for(int j=0; j < no_of_cameras_; j++)
        {
            unsigned int min_border_x1 = ((cols * (j*1))) + orb_patch_radius_;
            int max_border_x = cols  - orb_patch_radius_;
            unsigned int min_border_x =  orb_patch_radius_;

            //store max_x
             max_x[j] = (cols*(j+1)) + orb_patch_radius_;

            auto& gpu_keypts = imgs_raw_keypts_to_distribute.at(j);
            std::sort(gpu_keypts.at(level).begin(), gpu_keypts.at(level).end(), cmp_pt<gpu::PartKey>());

            //left Distribute keypoints via tree
            std::vector<gpu::PartKey> dist_keypts;
            dist_keypts = distribute_keypoints_via_tree( gpu_keypts.at(level), min_border_x, max_border_x,
                    min_border_y, max_border_y, num_keypts_per_level_.at(level));

            keypt_count = 0;

            for (auto& keypt : dist_keypts) {
                keypt.pt.x += min_border_x1;
                keypt.pt.y += min_border_y;
                keypts_at_level.push_back(keypt);
                keypt_count++;
            }
            keypts_cnt.at(j) += keypt_count;
        }
    }
}


void orb_extractor_impl::compute_keypoints_oct_tree(std::vector<std::vector<gpu::PartKey>>& keypts_to_distribute,
                                               std::vector<std::vector<gpu::PartKey>>& all_keypts) const
{
    all_keypts.resize(num_levels_);

    for (unsigned int level = 0; level < num_levels_; ++level) {
        constexpr unsigned int min_border_x = orb_patch_radius_;
        constexpr unsigned int min_border_y = orb_patch_radius_;
        const unsigned int max_border_x = gpu_pyramid_image_.at(level).width() - orb_patch_radius_;
        const unsigned int max_border_y = gpu_pyramid_image_.at(level).height() - orb_patch_radius_;

        std::vector<gpu::PartKey>& keypts_at_level = all_keypts.at(level);
        keypts_at_level.reserve(max_num_keypts_);

        std::sort(keypts_to_distribute.at(level).begin(), keypts_to_distribute.at(level).end(), cmp_pt<gpu::PartKey>());

        // Distribute keypoints via tree
        keypts_at_level = distribute_keypoints_via_tree(keypts_to_distribute.at(level), min_border_x, max_border_x,
                                                        min_border_y, max_border_y, num_keypts_per_level_.at(level));

        for (auto& keypt : keypts_at_level) {
            keypt.pt.x += min_border_x;
            keypt.pt.y += min_border_y;
        }
    }
}

void orb_extractor_impl::correct_keypoint_scale(std::vector<KeyType>& keypts_at_level, const unsigned int level) const {
    if (level == 0) {
        return;
    }
    const float scale_at_level = scale_factors_.at(level);
    for (auto& keypt_at_level : keypts_at_level) {
#ifdef OPENCV_FREE
        keypt_at_level.x *= scale_at_level;
        keypt_at_level.y *= scale_at_level;
#else
        keypt_at_level.pt *= scale_at_level;
#endif
    }
}

std::vector<gpu::PartKey> orb_extractor_impl::distribute_keypoints_via_tree(const std::vector<gpu::PartKey>& keypts_to_distribute,
                                                                  const int min_x, const int max_x, const int min_y,
                                                                  const int max_y, const unsigned int num_keypts) const
{
    auto nodes = initialize_nodes(keypts_to_distribute, min_x, max_x, min_y, max_y);

    // Forkable leaf nodes list
    // The pool is used when a forking makes nodes more than a limited number
    std::vector<std::pair<int, orb_extractor_node<gpu::PartKey>*>> leaf_nodes_pool;
    leaf_nodes_pool.reserve(nodes.size() * 10);

    // A flag denotes if enough keypoints have been distributed
    bool is_filled = false;

    while (true) {
        const unsigned int prev_size = nodes.size();
        auto iter = nodes.begin();
        leaf_nodes_pool.clear();

        // Fork node and remove the old one from nodes
        while (iter != nodes.end()) {
            if (iter->is_leaf_node_) {
                iter++;
                continue;
            }

            // Divide node and assign to the leaf node pool
            const auto child_nodes = iter->divide_node();
            assign_child_nodes(child_nodes, nodes, leaf_nodes_pool);
            // Remove the old node
            iter = nodes.erase(iter);
        }

        // Stop iteration when the number of nodes is over the designated size or new node is not generated
        if (num_keypts <= nodes.size() || nodes.size() == prev_size) {
            is_filled = true;
            break;
        }

        // If all nodes number is more than limit, keeping nodes are selected by next step
        if (num_keypts < nodes.size() + leaf_nodes_pool.size()) {
            is_filled = false;
            break;
        }
    }

    while (!is_filled) {
        // Select nodes so that keypoint number is just same as designeted number
        const unsigned int prev_size = nodes.size();

        auto prev_leaf_nodes_pool = leaf_nodes_pool;
        leaf_nodes_pool.clear();

        // Sort by number of keypoints in the patch of each leaf node
        //std::sort(prev_leaf_nodes_pool.rbegin(), prev_leaf_nodes_pool.rend());
        // Do processes from the node which has much more keypoints
        for (const auto& prev_leaf_node : prev_leaf_nodes_pool) {
            // Divide node and assign to the leaf node pool
            const auto child_nodes = prev_leaf_node.second->divide_node();
            assign_child_nodes(child_nodes, nodes, leaf_nodes_pool);
            // Remove the old node
            nodes.erase(prev_leaf_node.second->iter_);

            if (num_keypts <= nodes.size()) {
                is_filled = true;
                break;
            }
        }

        // Stop dividing if the number of nodes is reached to the limit or there are no dividable nodes
        if (is_filled || num_keypts <= nodes.size() || nodes.size() == prev_size) {
            is_filled = true;
            break;
        }
    }

    return find_keypoints_with_max_response(nodes);
}

std::list<orb_extractor_node<gpu::PartKey>> orb_extractor_impl::initialize_nodes(const std::vector<gpu::PartKey>& keypts_to_distribute,
                                                                       const int min_x, const int max_x,
                                                                       const int min_y, const int max_y) const
{
    // The aspect ratio of the target area for keypoint detection
    const auto ratio = static_cast<double>(max_x - min_x) / (max_y - min_y);
    // The width and height of the patches allocated to the initial node
    double delta_x, delta_y;
    // The number of columns or rows
    unsigned int num_x_grid, num_y_grid;

    if (ratio > 1) {
        // If the aspect ratio is greater than 1, the patches are made in a horizontal direction
        num_x_grid = std::round(ratio);
        num_y_grid = 1;
        delta_x = static_cast<double>(max_x - min_x) / num_x_grid;
        delta_y = max_y - min_y;
    } else {
        // If the aspect ratio is equal to or less than 1, the patches are made in a vertical direction
        num_x_grid = 1;
        num_y_grid = std::round(1 / ratio);
        delta_x = max_x - min_y;
        delta_y = static_cast<double>(max_y - min_y) / num_y_grid;
    }

    // The number of the initial nodes
    const unsigned int num_initial_nodes = num_x_grid * num_y_grid;

    // A list of node
    std::list<orb_extractor_node<gpu::PartKey>> nodes;

    // Initial node objects
    std::vector<orb_extractor_node<gpu::PartKey>*> initial_nodes;
    initial_nodes.resize(num_initial_nodes);

    // Create initial node substances
    for (unsigned int i = 0; i < num_initial_nodes; ++i) {
        orb_extractor_node<gpu::PartKey> node;

        // x / y index of the node's patch in the grid
        const unsigned int ix = i % num_x_grid;
        const unsigned int iy = i / num_x_grid;

        node.pt_begin_ = Point2i(delta_x * ix, delta_y * iy);
        node.pt_end_ = Point2i(delta_x * (ix + 1), delta_y * (iy + 1));
        node.keypts_.reserve(keypts_to_distribute.size());

        nodes.push_back(node);
        initial_nodes.at(i) = &nodes.back();
    }
    int cnt = 0;

    // Assign all keypoints to initial nodes which own keypoint's position
    for (const auto& keypt : keypts_to_distribute) {
        // x / y index of the patch where the keypt is placed
        const unsigned int ix = keypt.pt.x / delta_x;
        const unsigned int iy = keypt.pt.y / delta_y;
        const unsigned int node_idx = ix + iy * num_x_grid;

#ifdef DEBUG_LOG
        if(node_idx == 2)
        {
           std::cout << "\n node_idx:" << node_idx << ", ix:" << ix << ", iy:" << iy <<", num_x_gris:" << num_x_grid <<", keypt.pt.x:"
                     << keypt.pt.x << ", keypt.pt.y:" << keypt.pt.y << ", delta_x:" << delta_x << ", delta_y:" << delta_y;
           std::cout << "\n.......................................";
           exit(1);
           //node_idx=1;
        }
#endif

        initial_nodes.at(node_idx)->keypts_.push_back(keypt);
    }
    auto iter = nodes.begin();
    while (iter != nodes.end()) {
        // Remove empty nodes
        if (iter->keypts_.empty()) {
            iter = nodes.erase(iter);
            continue;
        }
        // Set the leaf node flag if the node has only one keypoint
        iter->is_leaf_node_ = (iter->keypts_.size() == 1);
        iter++;
    }

    return nodes;
}

void orb_extractor_impl::assign_child_nodes(const std::array<orb_extractor_node<gpu::PartKey>, 4>& child_nodes,
                                       std::list<orb_extractor_node<gpu::PartKey>>& nodes,
                                       std::vector<std::pair<int, orb_extractor_node<gpu::PartKey>*>>& leaf_nodes) const
{
    for (const auto& child_node : child_nodes) {
        if (child_node.keypts_.empty()) {
            continue;
        }
        nodes.push_front(child_node);
        if (child_node.keypts_.size() == 1) {
            continue;
        }
        leaf_nodes.emplace_back(std::make_pair(child_node.keypts_.size(), &nodes.front()));
        // Keep the self iterator to remove from std::list randomly
        nodes.front().iter_ = nodes.begin();
    }
}

std::vector<gpu::PartKey> orb_extractor_impl::find_keypoints_with_max_response(
    std::list<orb_extractor_node<gpu::PartKey>>& nodes) const
{
    // A vector contains result keypoint
    std::vector<gpu::PartKey> result_keypts;
    result_keypts.reserve(nodes.size());

    // Store keypoints which has maximum response in the node patch
    for (auto& node : nodes) {
        auto& node_keypts = node.keypts_;
        auto& keypt = node_keypts.at(0);
        double max_response = keypt.response;

        for (unsigned int k = 1; k < node_keypts.size(); ++k) {
            if (node_keypts.at(k).response > max_response) {
                keypt = node_keypts.at(k);
                max_response = node_keypts.at(k).response;
            }
        }

        result_keypts.push_back(keypt);
    }

    return result_keypts;
}

void orb_extractor::set_max_keypoints_gpu_buffer_size(size_t max_fast_keypoints_size, size_t max_nms_keypoints_size)
{
  // FIXME, Add function to set
   extractor_impl->max_fast_keypoints_ = max_fast_keypoints_size;
   extractor_impl->max_nms_keypoints_ = max_nms_keypoints_size;
}

void orb_extractor_impl::calc_gpu_buffer_size(size_t width, size_t height, int no_of_imgs)
{
   double non_integer_fast_result = (((((width*height)/100)*7)*2.1)*no_of_imgs);
   non_integer_fast_result = (round(non_integer_fast_result/4096))*4096;
   max_fast_keypoints_ = (size_t)non_integer_fast_result;
   max_fast_keypoints_ = max_fast_keypoints_ * sizeof(gpu::PtGPUBuffer);

   double non_integer_nms_result = ((((double)width * height) / 100) * 5.6) * no_of_imgs;
   non_integer_nms_result = (round(non_integer_nms_result/4096))*4096;
   max_nms_keypoints_ = (size_t)non_integer_nms_result;
   max_nms_keypoints_ = max_nms_keypoints_ * sizeof(gpu::KeypointGPUBuffer);
}
