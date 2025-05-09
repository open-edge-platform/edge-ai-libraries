/*******************************************************************************
 * Copyright (C) 2018-2025 Intel Corporation
 *
 * SPDX-License-Identifier: MIT
 ******************************************************************************/

#include "image_inference_async/image_inference_async.h"
#include "openvino_image_inference.h"
#include "utils.h"

using namespace InferenceBackend;

namespace {

ImagePreprocessorType getPreProcType(const std::map<std::string, std::string> &base_config) {
    auto it = base_config.find(KEY_PRE_PROCESSOR_TYPE);
    if (it == base_config.end())
        throw std::runtime_error("Image pre-processor type is not set");
    return static_cast<ImagePreprocessorType>(std::stoi(it->second));
}

} // namespace

std::map<std::string, GstStructure *> ImageInference::GetModelInfoPreproc(const std::string model_file) {
    return OpenVINOImageInference::GetModelInfoPreproc(model_file);
}

ImageInference::Ptr ImageInference::createImageInferenceInstance(MemoryType input_image_memory_type,
                                                                 const InferenceConfig &config, Allocator *allocator,
                                                                 CallbackFunc callback, ErrorHandlingFunc error_handler,
                                                                 dlstreamer::ContextPtr context) {
    // Flag to determine if asynchronous mode is required
    bool async_mode = false;

    // Determine the memory type to be used for inference
    MemoryType memory_type_to_use = MemoryType::ANY;

    switch (input_image_memory_type) {
    case MemoryType::SYSTEM:
        // Use system memory directly
        memory_type_to_use = input_image_memory_type;
        break;

    case MemoryType::DMA_BUFFER:
    case MemoryType::VAAPI: {
        // Enable asynchronous mode for DMA_BUFFER and VAAPI
        async_mode = true;

        // Ensure context is provided for VAAPI
        if (!context) {
            throw std::invalid_argument("Null context provided (VaApiContext is expected)");
        }

        // Determine the preprocessor type based on configuration
        ImagePreprocessorType preproc_type = getPreProcType(config.at(KEY_BASE));
        switch (preproc_type) {
        case ImagePreprocessorType::VAAPI_SYSTEM:
            // Use system memory for VAAPI_SYSTEM preprocessor type
            memory_type_to_use = MemoryType::SYSTEM;
            break;
        case ImagePreprocessorType::VAAPI_SURFACE_SHARING:
            // Use VAAPI memory for VAAPI_SURFACE_SHARING preprocessor type
            memory_type_to_use = MemoryType::VAAPI;
            break;

        default:
            throw std::runtime_error("Incorrect pre-process-backend, should be vaapi or vaapi-surface-sharing");
        }
        break;
    }

    default:
        throw std::invalid_argument("Unsupported memory type");
    }

    // Create an OpenVINOImageInference instance with the determined memory type
    auto ov_inference = std::make_shared<OpenVINOImageInference>(config, allocator, context, callback, error_handler,
                                                                 memory_type_to_use);

    ImageInference::Ptr result_inference;
    if (async_mode) {
#ifdef ENABLE_VAAPI
        // Wrap the inference in an asynchronous handler if async mode is enabled
        result_inference = std::make_shared<ImageInferenceAsync>(config, context, std::move(ov_inference));
#endif
    } else {
        // Use the OpenVINO inference directly if not in async mode
        result_inference = std::move(ov_inference);
    }

    return result_inference;
}