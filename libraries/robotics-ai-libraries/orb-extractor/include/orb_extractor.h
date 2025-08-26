// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

#include "orb_type.h"

#include "config.h"

class orb_extractor {
public:

    orb_extractor() = delete;

    //! Constructor
    orb_extractor(const unsigned int max_num_keypts, const float scale_factor, const unsigned int num_levels,
                  const unsigned int ini_fast_thr, const unsigned int min_fast_thr, const unsigned int no_of_cameras,
                  const std::vector<std::vector<float>>& mask_rects = {});

    //! Destructor
    ~orb_extractor();

    //! Warpper function for extract keypoints and each descriptor of them for mono input or stereo
#ifdef OPENCV_FREE
    void extract( const std::vector<Mat2d>& in_image, const std::vector<Mat2d>& in_image_mask,
                            std::vector<std::vector<KeyPoint>>& keypts,
                            std::vector<Mat2d>& out_descriptors
                          );
#else
    void extract( const cv::_InputArray& in_image, const cv::_InputArray& in_image_mask,
                            std::vector<std::vector<cv::KeyPoint>>& keypts,
                            const cv::_OutputArray& out_descriptors
                          );
#endif

    //! Get the maximum number of keypoints
    unsigned int get_max_num_keypoints() const;

    //! Set the maximum number of keypoints
    void set_max_num_keypoints(const unsigned int max_num_keypts);

    //! Get the scale factor
    float get_scale_factor() const;

    //! Set the scale factor
    void set_scale_factor(const float scale_factor);

    //! Get the number of scale levels
    unsigned int get_num_scale_levels() const;

    //! Set the number of scale levels
    void set_num_scale_levels(const unsigned int num_levels);

    //! Get the initial fast threshold
    unsigned int get_initial_fast_threshold() const;

    //! Set the initial fast threshold
    void set_initial_fast_threshold(const unsigned int initial_fast_threshold);

    //! Get the minimum fast threshold
    unsigned int get_minimum_fast_threshold() const;

    //! Set the minimum fast threshold
    void set_minimum_fast_threshold(const unsigned int minimum_fast_threshold);

    //! Get image pyramid
    void get_image_pyramid(std::vector<MatType> &image_pyramid);

    //! Get image pyramid for stereo input.
    void get_image_pyramid(std::vector<std::vector<MatType>> &image_pyramid);

    //! Set GPU kernel binary path
    void set_gpu_kernel_path(std::string path);

    //! Set max keypoints gpu buffer size
    void set_max_keypoints_gpu_buffer_size(size_t max_fast_keypoints_size, size_t max_nms_keypoints_size);

    //! Get scale factors
    std::vector<float> get_scale_factors() const;

    //! Get inverse scale factors
    std::vector<float> get_inv_scale_factors() const;

    //! Get sigma square for all levels
    std::vector<float> get_level_sigma_sq() const;

    //! Get inverted sigma square for all levels
    std::vector<float> get_inv_level_sigma_sq() const;

private:
    //! making object
    orb_extractor_impl* extractor_impl = NULL;
};
