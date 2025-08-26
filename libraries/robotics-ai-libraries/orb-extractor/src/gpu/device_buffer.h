// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#ifndef __DEVICE_BUFFER_H__
#define __DEVICE_BUFFER_H__

#include "cm_base.h"
#include "device_base.h"
#include <type_traits>

namespace gpu
{

template <typename T, int C>
class DeviceBuffer
{
public:

    DeviceBuffer() :
        data_(nullptr), width_(0), height_(0), channel_(0), size_(0),
        capacity_(0), allocated_(false), type_(kSharedMemory), device_base_(nullptr), command_list_(nullptr), device_(0), context_(0) {}

    DeviceBuffer(MemoryType type) :
        data_(nullptr), width_(0), height_(0), channel_(0), size_(0),
        capacity_(0), allocated_(false), device_base_(nullptr), command_list_(nullptr), device_(0), context_(0)
    {
      type_ = type;
    }

    DeviceBuffer(uint32_t size) :
        data_(nullptr), width_(0), height_(0), channel_(0),
        capacity_(0), allocated_(false), type_(kSharedMemory), device_base_(nullptr), command_list_(nullptr), device_(0), context_(0)
    {
        resize(size);
    }

    DeviceBuffer(uint32_t size, MemoryType type) :
        data_(nullptr), width_(0), height_(0), channel_(0),
        capacity_(0), allocated_(false), device_base_(nullptr), command_list_(nullptr), device_(0), context_(0)
    {
        type_ = type;
        resize(size);
    }

    DeviceBuffer(uint32_t width, uint32_t height) :
        data_(nullptr), channel_(0), capacity_(0), allocated_(false),
        type_(kSharedMemory), device_base_(nullptr), command_list_(nullptr), device_(0), context_(0)
    {
        resize(width, height);
    }

    DeviceBuffer(uint32_t width, uint32_t height, MemoryType type) :
        data_(nullptr), channel_(0), capacity_(0), allocated_(false),
        type_(type), device_base_(nullptr), command_list_(nullptr), device_(0), context_(0)
    {
        type_ = type;
        resize(width, height);
    }

    ~DeviceBuffer() noexcept(false)
    {
        if (device_base_->DelRef())
            delete device_base_;
        destroy();
    }

    void setDeviceBase(DeviceBase *device)
    {
        device_base_ = device;
        device_base_->AddRef();
        context_ = device_base_->GetContext();
        device_ = device_base_->GetDevice();
        command_list_ = device_base_->GetCommandList();
    }

    void allocate(uint32_t count)
    {
        if (device_base_ == nullptr)
        {
          throw std::runtime_error("Buffer not initialize correctly");
        }

        if (data_ && capacity_ >= count)
            return;

        destroy();
        if ((type_ & kDeviceMemory) == kDeviceMemory)
            data_ = LzAllocDeviceMemory(context_, device_, sizeof(T) * count);
        else if ((type_ & kSharedMemory) == kSharedMemory)
            data_ = LzAllocSharedMemory(context_, device_, sizeof(T) * count);
        else if ((type_ & kHostMemory) == kHostMemory)
            data_ = LzAllocHostMemory(context_, sizeof(T) * count);

        capacity_ = count;
        channel_ = C;
        allocated_ = true;
    }

    void allocate(uint32_t width, uint32_t height)
    {
        if (device_base_ == nullptr)
        {
          throw std::runtime_error("Buffer not initialize correctly");
        }

        if (data_ && width_ == width && height_ == height)
            return;

        destroy();
        if ((type_ & kDeviceMemory) == kDeviceMemory)
            data_ = LzAllocDeviceMemory(context_, device_, sizeof(T) * width * height);
        else if ((type_ & kSharedMemory) == kSharedMemory)
            data_ = LzAllocSharedMemory(context_, device_, sizeof(T) * width * height);
        else if ((type_ & kHostMemory) == kHostMemory)
            data_ = LzAllocHostMemory(context_, sizeof(T) * width * height);

        size_ = width * height;
        capacity_ = size_;
        channel_ = C;
        allocated_ = true;
    }

    void destroy()
    {
        if (device_base_ == nullptr)
        {
          throw std::runtime_error("Buffer not initialize correctly");
        }

        if (data_)
            LzFreeMemory(context_, data_);

        data_ = nullptr;
        size_ = 0;
        width_ = 0;
        height_ = 0;
        allocated_ = false;
    }

    void resize(uint32_t size)
    {
        allocate(size);
        size_ = size;
    }

    void resize(uint32_t size, MemoryType type)
    {
        type_ = type;
        allocate(size);
        size_ = size;
    }

    void resize(uint32_t width, uint32_t height)
    {
        allocate(width, height);
        width_ = width;
        height_ = height;
    }

    void resize(uint32_t width, uint32_t height, MemoryType type)
    {
        type_ = type;
        allocate(width, height);
        width_ = width;
        height_ = height;
    }

    void map(uint32_t size, void* data)
    {
        data_ = (T*) data;
        size_ = size;
        allocated_ = false;
    }

    void map(uint32_t width, uint32_t height, void* data)
    {
        data_ = (T*) data;
        size_ = width * height * sizeof(T);
        allocated_ = false;
    }

    void assign(uint32_t size, const void* h_data)
    {
        resize(size);
        upload((T*)h_data);
    }

    void assign(uint32_t width, uint32_t height, const void* h_data)
    {
        resize(width, height);
        upload((T*)h_data);
    }

    template<typename VT>
    void _upload(VT h_data, CommandListIndex mode, size_t size, ze_event_handle_t event)
    {
        if (device_base_ == nullptr)
        {
          throw std::runtime_error("Buffer not initialize correctly");
        }

        size_t copy_size = (size == 0) ? sizeof(T) * size_ : sizeof(T) * size;

        if (mode == kImmediate)
        {
            ze_event_handle_t e = (event == nullptr) ? device_base_->CreateEvent() : event;

            LzAppendMemoryCopy(command_list_->at(mode), data_, h_data, copy_size, e);

            LzWaitForEvent(e);
            if (event == nullptr)
                device_base_->DestroyEvent(e);
        }
        else
        {
            if (std::is_same<VT, const ze_image_handle_t>::value) {
                LzAppendImageCopyToMemory(command_list_->at(mode), (ze_image_handle_t)h_data, data_);
                LzAppendBarrier(command_list_->at(mode));

            } else {
                LzAppendMemoryCopy(command_list_->at(mode), data_, h_data, copy_size, event);
                LzAppendBarrier(command_list_->at(mode));
            }
        }
    }

    void upload(const T *h_data, CommandListIndex mode = kAppend, size_t size = 0, ze_event_handle_t event = nullptr)
    {
        _upload<const T *>(h_data, mode, size, event);
    }

    void upload(const ze_image_handle_t h_data, CommandListIndex mode = kAppend, size_t size = 0, ze_event_handle_t event = nullptr)
    {
        _upload<const ze_image_handle_t>(h_data, mode, size, event);
    }

    void upload(const void *h_data, CommandListIndex mode = kAppend, size_t size = 0, ze_event_handle_t event = nullptr)
    {
        _upload<const void *>(h_data, mode, size, event);
    }

    template<typename VT>
    void _download(VT h_data, CommandListIndex mode, size_t size, ze_event_handle_t event)
    {
        if (device_base_ == nullptr)
        {
          throw std::runtime_error("Buffer not initialize correctly");
        }

        size_t copy_size = (size == 0) ? sizeof(T) * size_ : sizeof(T) * size;

        if (mode == kImmediate)
        {
            ze_event_handle_t e = (event == nullptr) ? device_base_->CreateEvent() : event;

            LzAppendMemoryCopy(command_list_->at(mode), h_data, data_, copy_size, e);

            LzWaitForEvent(e);
            if (event == nullptr)
                device_base_->DestroyEvent(e);
        }
        else
        {
            LzAppendMemoryCopy(command_list_->at(mode), h_data, data_, copy_size, event);
            LzAppendBarrier(command_list_->at(mode));
        }
    }

    void download(T *h_data, CommandListIndex mode = kAppend, size_t size = 0, ze_event_handle_t event = nullptr)
    {
        _download<T *>(h_data, mode, size, event);
    }

    void download(void *h_data, CommandListIndex mode = kAppend, size_t size = 0, ze_event_handle_t event = nullptr)
    {
        _download<void *>(h_data, mode, size, event);
    }

    void copyTo(T* rhs, CommandListIndex mode = kAppend, size_t size = 0, ze_event_handle_t event =  nullptr)
    {
        _download<void *>(rhs, mode, size, event);
    }

    template<typename VT>
    void _fill_pattern(VT pattern, CommandListIndex mode, size_t size, ze_event_handle_t event)
    {
        if (device_base_ == nullptr)
        {
          throw std::runtime_error("Buffer not initialize correctly");
        }

        size_t fill_size = (size == 0) ? sizeof(T) * size_ : sizeof(T) * size;

        if (mode == kImmediate)
        {
            ze_event_handle_t e = (event == nullptr) ? device_base_->CreateEvent() : event;

            LzAppendMemoryFill(command_list_->at(mode), data_, &pattern, sizeof(T), fill_size,
                e, 0, nullptr);

            LzWaitForEvent(e);
            if (event == nullptr)
                device_base_->DestroyEvent(e);
        }
        else
        {
            LzAppendMemoryFill(command_list_->at(mode), data_, &pattern, sizeof(T), fill_size,
                event, 0, nullptr);
            LzAppendBarrier(command_list_->at(mode));
        }
    }


    void fillZero(CommandListIndex mode = kAppend, size_t size = 0, ze_event_handle_t event = nullptr)
    {
        _fill_pattern<T>((T) 0, mode, size, event);
    }

    void fillPattern(T pattern, CommandListIndex mode = kAppend, size_t size = 0, ze_event_handle_t event = nullptr)
    {
        _fill_pattern<T>(pattern, mode, size, event);
    }

    void *raw()
    {
        return data_;
    }

    T* data()
    {
        assert(type_ != kDeviceMemory);
        return (T*) data_;
    }
    const T* data() const
    {
        assert(type_ != kDeviceMemory);
        return (T*) data_;
    }

    uint32_t size() const { return size_; }
    int ssize() const { return static_cast<int>(size_); }

    uint32_t width() const
    {
        if (allocated_ && width_)
            return width_;
        else
            return 0;
    }

    uint32_t height() const
    {
        if (allocated_ && height_)
            return height_;
        else
            return 0;
    }

    uint32_t channel() const
    {
        if (allocated_ && channel_)
            return channel_;
        else
            return 0;
    }

    operator T* () { return (T*) data_; }
    operator const T* () const { return (T*) data_; }

private:

    void* data_;
    uint32_t width_, height_;
    uint32_t channel_, size_, capacity_;
    bool allocated_;
    MemoryType type_;

    DeviceBase *device_base_;
    ze_device_handle_t device_;
    ze_context_handle_t context_;
    std::vector<ze_command_list_handle_t> *command_list_;

};

template<typename T, int C>
using Vec = DeviceBuffer<T, C>;
using Vec32f = Vec<float, 1>;
using Vec32d = Vec<double, 1>;
using Vec32i = Vec<int, 1>;
using Vec8u = Vec<uint8_t, 1>;
using Vec32u = Vec<uint32_t, 1>;

} // namespace gpu 

#endif // !__DEVICE_BUFFER_H__
