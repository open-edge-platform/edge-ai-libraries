#include "rl_inference_dummy.h"

namespace inference
{
    bool RlInferenceDummy::Init(const std::string& policyfile, const std::string& config, const std::string& csvFile, std::string& device)
    {
        input_tensor_size = 0;
        output_tensor_size = 0;
        // Load policy model and rl cfg
        if (!LoadModel(policyfile, config, device))
        {
            std::cout << "[RlInferenceDummy] Failed to load the model. Ensure the path is correct and accessible." << std::endl;
            return false;
        }
        return true;
    }

    bool RlInferenceDummy::LoadModel(const std::string& policyfile, const std::string& config, const std::string& device)
    {
        std::cout << "Load RL model from path : " << policyfile << std::endl;
        interpreter = ov_core.read_model(policyfile.c_str());
        compiled_model = ov_core.compile_model(interpreter, device);
        infer_request = compiled_model.create_infer_request();

        // Get input tensor information
        input_tensor_size = 0;
        auto inputTensor = compiled_model.inputs();
        for (const auto &input : inputTensor)
        {
            auto shape = input.get_shape();
            std::cout << "Input Shape: [";
            for (size_t j = 0; j < shape.size(); ++j)
            {
                std::cout << shape[j] << (j != shape.size() - 1 ? ", " : "");
            }
            std::cout << "]" << std::endl;
            input_tensor_size++;
        }

        // Get output tensor information
        output_tensor_size = 0;
        auto outputTensor = compiled_model.outputs();
        for (const auto &output : outputTensor)
        {
            auto shape = output.get_shape();
            std::cout << "Output Shape: [";
            for (size_t j = 0; j < shape.size(); ++j)
            {
                std::cout << shape[j] << (j != shape.size() - 1 ? ", " : "");
            }
            std::cout << "]" << std::endl;
            output_tensor_size++;
        }
        std::cout << "RL model loaded successfully!" << std::endl;
        return true;
    }

    void RlInferenceDummy::StartInference(void* state, void* cmd)
    {
        size_t loop = 0;
        for (loop = 0; loop < input_tensor_size; loop++)
        {
            auto inputTensor = infer_request.get_input_tensor(loop);
            float* input_data = inputTensor.data<float>();
            // make input tensor with state
        }
        // start inference
        //infer_request.infer();
        for (loop = 0; loop < output_tensor_size; loop++)
        {
            auto outputTensor = infer_request.get_output_tensor(loop);
            const float* output_data = outputTensor.data<const float>();
            size_t numElements = outputTensor.get_size();
            // make input tensor with state
        }
    }

    void RlInferenceDummy::Update(void* state, void* cmd)
    {
        auto t1=std::chrono::steady_clock::now();
        StartInference(state, cmd);
        auto t2=std::chrono::steady_clock::now();
        double dr_ms=std::chrono::duration<double,std::milli>(t2-t1).count();
    }
} // namespace inference
