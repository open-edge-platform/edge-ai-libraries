// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#ifndef __ORB_EXTRACTOR_IMPL__
#define __ORB_EXTRACTOR_IMPL__

#include <memory>

#include "orb_extractor_node.h"
#include "gpu/device_base.h"
#include "gpu/gpu_kernels.h"
#include "gpu/orb.h"

class orb_extractor_impl {
public:

    orb_extractor_impl()
    {
        orbKernel_ = std::make_shared<gpu::ORBKernel>();

        device_base_ = orbKernel_->getDeviceBase();
        gpu_mask_buffer_.setDeviceBase(device_base_);
        gpu_orb_pattern_buffer_.setDeviceBase(device_base_);
        gpu_u_max_buffer_.setDeviceBase(device_base_);
        gpu_initialized_ = false;
    }

    ~orb_extractor_impl() {};

    //! Initialize orb extractor
    void initialize();

    //! Extract keypoints and each descriptor of them mono input
    template<typename InT, typename OutT>
    void extract(const InT& in_image, const InT& in_image_mask,
                 std::vector<KeyType>& keypts, OutT& out_descriptors);

    //! Extract keypoints and each descriptor of them multi camera input
    template<typename InT, typename OutT>
    void extract( const InT& in_image, const InT& in_image_mask,
                    std::vector<std::vector<KeyType>>& keypts,
                    OutT& out_descriptors);

    //! calculate gpu bufer size
    void calc_gpu_buffer_size(size_t width, size_t height, int no_of_imgs);

    //! Calculate scale factors and sigmas
    void calc_scale_factors();

    //! Copy for large image to single images
    void copy_to(MatType& dst_image, const MatType& src_image, const Point2i start, const Point2i end);

    //! Copy for multi images to one single large image
    void copy_to_single_img(MatType& dst_image, const MatType& src_image, const Point2i start);

    //! Create rectangles
    void create_rectangle(MatType &image, const Point2i start, const Point2i end, const unsigned char pattern);

    //! Create a mask matrix that constructed by rectangles
    void create_rectangle_mask(const unsigned int cols, const unsigned int rows);

    //! Intialize GPU graph for ORB
    void gpu_initialize(const MatType& image);

    //! Set user provided kernel path
    void set_kernel_path(std::string path);

    //! Compute image pyramid
    void compute_image_pyramid(const MatType& image);

    //! Compute fast keypoints for cells in each image pyramid
    void compute_fast_keypoints(std::vector<std::vector<gpu::PartKey>>& all_keypts, const MatType& mask, int num_image=1);

    //! Correct keypoint's position to comply with the scale
    void correct_keypoint_scale(std::vector<KeyType>& keypts_at_level, const unsigned int level) const;

    //! Distribute computed fast keypoints
    void compute_keypoints_oct_tree(std::vector<std::vector<gpu::PartKey>> &keypts_to_distribute,
                                    std::vector<std::vector<gpu::PartKey>> &all_keypts) const;

    //! Distribute computed for multi camera input fast keypoints
    void compute_keypoints_oct_trees(std::vector<std::vector<std::vector<gpu::PartKey>>> &raw_keypts_to_distribute,
                                     std::vector<std::vector<gpu::PartKey>> &all_keypts,
                                     std::vector<std::vector<int>> &max_x_border_store,
                                     std::vector<int> &keypts_cnt) const;

    //! Pick computed keypoints on the image uniformly
    std::vector<gpu::PartKey> distribute_keypoints_via_tree(const std::vector<gpu::PartKey>& keypts_to_distribute,
                                                            const int min_x, const int max_x, const int min_y, const int max_y,
                                                            const unsigned int num_keypts) const;

    //! Initialize nodes that used for keypoint distribution tree
    std::list<orb_extractor_node<gpu::PartKey>> initialize_nodes(const std::vector<gpu::PartKey>& keypts_to_distribute,
                                                   const int min_x, const int max_x, const int min_y, const int max_y) const;

    //! Assign child nodes to the all node list
    void assign_child_nodes(const std::array<orb_extractor_node<gpu::PartKey>, 4>& child_nodes, std::list<orb_extractor_node<gpu::PartKey>>& nodes,
                            std::vector<std::pair<int, orb_extractor_node<gpu::PartKey>*>>& leaf_nodes) const;

    //! Find keypoint which has maximum value of response
    std::vector<gpu::PartKey> find_keypoints_with_max_response(std::list<orb_extractor_node<gpu::PartKey>>& nodes) const;

    static constexpr unsigned int orb_patch_radius_ = 19;

    //! size of maximum ORB patch radius
    static constexpr unsigned int orb_overlap_size_ = 6;

    //! BRIEF orientation
    static constexpr unsigned int fast_patch_size_ = 31;
    //! half size of FAST patch
    static constexpr int fast_half_patch_size_ = fast_patch_size_ / 2;

    static constexpr unsigned int orb_cell_size_ = 32;

    static constexpr unsigned int max_num_pyramid_levels = 8;

    //! rectangle mask has been already initialized or not
    bool mask_is_initialized_ = false;

    MatType rect_mask_;

    //! Image pyramid
    std::vector<MatType> image_pyramid_;

    unsigned int max_num_keypts_ = 2000;
    float scale_factor_ = 1.1;
    unsigned int num_levels_ = max_num_pyramid_levels;
    unsigned int ini_fast_thr_ = 20;
    unsigned int min_fast_thr_ = 7;
    unsigned int no_of_cameras_ = 1;

    std::vector<std::vector<float>> mask_rects_;

    //! A list of the scale factor of each pyramid layer
    std::vector<float> scale_factors_;
    std::vector<float> inv_scale_factors_;
    //! A list of the sigma of each pyramid layer
    std::vector<float> level_sigma_sq_;
    std::vector<float> inv_level_sigma_sq_;

    //! Maximum number of keypoint of each level
    std::vector<unsigned int> num_keypts_per_level_;
    //! Index limitation that used for calculating of keypoint orientation
    std::vector<int> u_max_;

    gpu::Vec8u gpu_mask_buffer_;
    std::vector<gpu::Vec8u> gpu_pyramid_buffer_;
    std::vector<gpu::Image8u> gpu_pyramid_image_;
    std::vector<gpu::Image8u> gpu_gaussian_image_;

    gpu::Vec32f gpu_orb_pattern_buffer_;
    gpu::Vec32i gpu_u_max_buffer_;

    std::string gpu_kernel_path_;

    bool gpu_initialized_;

    gpu::ORBKernel::Ptr orbKernel_;

    gpu::DeviceBase* device_base_;

    //! Set to 0 to let library to decide proper maximum keypoints buffer
    size_t max_nms_keypoints_ = 0;
    size_t max_fast_keypoints_ = 0;

};

#endif // __ORB_EXTRACTOR_IMPL__
