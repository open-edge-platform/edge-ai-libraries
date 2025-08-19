// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#ifndef __DEVICE_IMAGE_H__
#define __DEVICE_IMAGE_H__

#include "cm_base.h"
#include "device_base.h"

namespace gpu
{

enum ImageType
{
    kBuffer,
    kImage2D,
    kImage3D
};

template <ze_image_format_layout_t LT, ze_image_format_type_t FT, typename T>
class DeviceImage
{
public:

    DeviceImage() : image_(nullptr), width_(0), height_(0), pitch_(0),
            channel_(0), type_(kBuffer), capacity_(0), allocated_(false), device_base_(nullptr), command_list_(nullptr), device_(0), context_(0) {}

    DeviceImage(uint32_t size) : image_(nullptr), capacity_(0),
        channel_(0), type_(kBuffer), allocated_(false), device_base_(nullptr), command_list_(nullptr), device_(0), context_(0) { resize(size);}

    DeviceImage(uint32_t width, uint32_t height) : image_(nullptr),
        channel_(0), capacity_(0), type_(kImage2D), allocated_(false), device_base_(nullptr), command_list_(nullptr), device_(0), context_(0) { resize(width, height);}

    ~DeviceImage() noexcept(false)
    {
        if (device_base_->DelRef())
            delete device_base_;
        destroy();
    }

    void setDeviceBase(DeviceBase *dev)
    {
        device_base_ = dev;
        device_base_->AddRef();
        context_ = device_base_->GetContext();
        device_ = device_base_->GetDevice();
        command_list_ = device_base_->GetCommandList();
    }

    void allocate(uint32_t size)
    {
        if (device_base_ == nullptr)
        {
          throw std::runtime_error("Buffer not initialize correctly");
        }

        if (image_)
            return;

        destroy();
        /* TODO:  Bug in Level Zero for buffer allocation */
        /* Allocation will fail now */
        image_ = LzCreateBuffer(context_, device_, size);
        allocated_ = true;
        type_ = kBuffer;
    }

    void allocate(uint32_t width, uint32_t height)
    {
        if (device_base_ == nullptr)
        {
          throw std::runtime_error("Buffer not initialize correctly");
        }

        if (image_ && width_ == width && height_ == height)
            return;

        destroy();
        ze_image_format_t fmt = {LT, FT};
        image_ = LzCreateImage2D(context_, device_, fmt, width, height);
        width_ = width;
        height_ = height;
        /* Get the image pitch */
        auto [channel, row_pitch, slice_pitch] = LzGetImageProperties(image_);
        capacity_ = row_pitch * height_;
        pitch_ = row_pitch;
        channel_ = channel;
        allocated_ = true;
        type_ = kImage2D;
    }

    void destroy()
    {
        if (device_base_ == nullptr)
        {
          throw std::runtime_error("Buffer not initialize correctly");
        }

        if (allocated_ && image_)
            LzDestroyImage(image_);
        image_ = nullptr;
        width_ = 0;
        height_ = 0;
        allocated_ = false;
    }

    void resize(uint32_t size)
    {
        allocate(size);
    }

    void resize(uint32_t width, uint32_t height)
    {
        allocate(width, height);
    }

    void assign(uint32_t width, uint32_t height, const void* h_data)
    {
        resize(width, height);
        upload((T*)h_data);
    }

    template<typename VT>
    void _upload(VT h_data, CommandListIndex mode, ze_event_handle_t event)
    {
        if (device_base_ == nullptr)
        {
          throw std::runtime_error("Buffer not initialize correctly");
        }

        if (mode == kImmediate)
        {
            ze_event_handle_t e = (event == nullptr) ? device_base_->CreateEvent() : event;

            LzAppendImageCopyFromMemory(command_list_->at(mode), image_, h_data, e);

            LzWaitForEvent(e);
            if (event == nullptr)
                device_base_->DestroyEvent(e);
        }
        else
        {
            LzAppendImageCopyFromMemory(command_list_->at(mode), image_, h_data, event);
            LzAppendBarrier(command_list_->at(mode));
        }
    }

    void _upload(const T *h_data, CommandListIndex mode = kAppend, ze_event_handle_t event = nullptr)
    {
        _upload<const T*>(h_data, mode, event);
    }

    void upload(const void *h_data, CommandListIndex mode = kAppend, ze_event_handle_t event = nullptr)
    {
        _upload<const void*>(h_data, mode, event);
    }

    template<typename VT>
    void _download(VT h_data, CommandListIndex mode, ze_event_handle_t event)
    {
        if (device_base_ == nullptr)
        {
          throw std::runtime_error("Buffer not initialize correctly");
        }

        if (mode == kImmediate)
        {
            ze_event_handle_t e = (event == nullptr) ? device_base_->CreateEvent() : event;

            LzAppendImageCopyToMemory(command_list_->at(mode), image_, h_data, e);

            LzWaitForEvent(e);
            if (event == nullptr)
                device_base_->DestroyEvent(e);
        }
        else
        {
            LzAppendImageCopyToMemory(command_list_->at(mode), image_, h_data, event);
            LzAppendBarrier(command_list_->at(mode));
        }
    }

    void download(T *h_data, CommandListIndex mode = kAppend, ze_event_handle_t event = nullptr)
    {
        _download<T*>(h_data, mode, event);
    }

    void download(void *h_data, CommandListIndex mode = kAppend, ze_event_handle_t event = nullptr)
    {
        _download<void *>(h_data, mode, event);
    }

    void copyTo(ze_image_handle_t rhs, int mode = kAppend, ze_event_handle_t event = nullptr)
    {
        if (device_base_ == nullptr)
        {
          throw std::runtime_error("Buffer not initialize correctly");
        }

        /* TODO: Query rhs type to ensure match with current image_ */
        if (mode == kImmediate)
        {
            ze_event_handle_t e = (event == nullptr) ? device_base_->CreateEvent() : event;

            LzAppendImageCopy(command_list_->at(mode), image_, rhs, e);

            LzWaitForEvent(e);
            if (event == nullptr)
                device_base_->DestroyEvent(e);
        }
        else
        {
            LzAppendImageCopy(command_list_->at(mode), image_, rhs, event);
            LzAppendBarrier(command_list_->at(mode));
        }
    }

    ze_image_handle_t raw() const
    {
        return image_;
    }

    uint32_t width() const
    {
        if (allocated_ && type_ == kImage2D)
            return width_;
        else
            return 0;
    }

    uint32_t height() const
    {
        if (allocated_ && type_ == kImage2D)
            return height_;
        else
            return 0;
    }

    uint32_t pitch() const
    {
        if (allocated_ && type_ == kImage2D)
            return pitch_;
        else
            return 0;
    }

    uint32_t channel() const
    {
        if (allocated_ && type_ == kImage2D)
            return channel_;
        else
            return 0;
    }

private:

    ze_image_handle_t image_;
    ImageType type_;
    uint32_t width_, height_, pitch_;
    uint32_t channel_, capacity_;
    bool allocated_;

    DeviceBase *device_base_;
    ze_device_handle_t device_;
    ze_context_handle_t context_;
    std::vector<ze_command_list_handle_t> *command_list_;
};

template <ze_image_format_layout_t LT, ze_image_format_type_t FT, typename T>
using Image = DeviceImage<LT, FT, T>;

using Image8u = Image<ZE_IMAGE_FORMAT_LAYOUT_8, ZE_IMAGE_FORMAT_TYPE_UINT, uint8_t>;
using Image8s = Image<ZE_IMAGE_FORMAT_LAYOUT_8, ZE_IMAGE_FORMAT_TYPE_SINT, int8_t>;
using Image16u = Image<ZE_IMAGE_FORMAT_LAYOUT_16, ZE_IMAGE_FORMAT_TYPE_UINT, uint16_t>;
using Image16s = Image<ZE_IMAGE_FORMAT_LAYOUT_16, ZE_IMAGE_FORMAT_TYPE_SINT, int16_t>;
using Image8888u = Image<ZE_IMAGE_FORMAT_LAYOUT_8_8_8_8, ZE_IMAGE_FORMAT_TYPE_UINT, uint32_t>;
using Image32f = Image<ZE_IMAGE_FORMAT_LAYOUT_32, ZE_IMAGE_FORMAT_TYPE_FLOAT, float>;

using Image3D8888u = DeviceImage<ZE_IMAGE_FORMAT_LAYOUT_8_8_8_8, ZE_IMAGE_FORMAT_TYPE_UINT, uint32_t>;

} // namespace gpu

#endif // !__DEVICE_IMAGE_H__
