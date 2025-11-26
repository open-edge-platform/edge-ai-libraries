#pragma once

#include "inference_stat.h"
#include <openvino/openvino.hpp>

namespace inference
{
    class Inference
    {
    public:
        Inference() = default;
        virtual ~Inference() = default;

        virtual bool Init(const std::string& policyfile, const std::string& config, const std::string& csvFile, std::string& device);
        virtual bool LoadModel(const std::string& policyfile, const std::string& config, const std::string& device);
        virtual void Update(void* state, void* cmd) {};
        InferenceStat infer_stat;

    protected:
        //ov model
        ov::Core ov_core;
        std::shared_ptr<ov::Model> interpreter;
        ov::CompiledModel compiled_model;
        ov::InferRequest infer_request;
        size_t input_tensor_size;
        size_t output_tensor_size;

    private:

    };

} // namespace inference
