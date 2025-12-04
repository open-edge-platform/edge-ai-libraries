#include "rl_stand_inference.h"
#include <vector>
#include <chrono>

namespace inference
{
    
    size_t RlStandInference::GetJointDim()
    {
        return _joint_dim;
    }

    bool RlStandInference::Init(const std::string& policyfile, const std::string& config, const std::string& csvFile, std::string& device)
    {
        input_tensor_size = 0;
        output_tensor_size = 0;
        // Load policy model and rl cfg
        if (!LoadModel(policyfile, config, device))
        {
            std::cout << "[StandInference] Failed to load the model. Ensure the path is correct and accessible." << std::endl;
            return false;
        }
        return true;
    }

    bool RlStandInference::LoadModel(const std::string& policyfile, const std::string& config, const std::string& device)
    {
        std::cout << "Load RL model from path : " << policyfile << std::endl;
        interpreter = ov_core.read_model(policyfile.c_str());
        compiled_model = ov_core.compile_model(interpreter, device);
        infer_request = compiled_model.create_infer_request();

        // Get input tensor information
        auto inputTensor = compiled_model.input(0);
        auto shape = inputTensor.get_shape();
        std::cout << "Input Shape: [";
        for (size_t j = 0; j < shape.size(); ++j)
        {
            std::cout << shape[j] << (j != shape.size() - 1 ? ", " : "");
        }
        std::cout << "]" << std::endl;

        // Get output tensor information
        auto outputTensor = compiled_model.output(0);
        auto out_shape = outputTensor.get_shape();
        std::cout << "Output Shape: [";
        for (size_t j = 0; j < out_shape.size(); ++j)
        {
            std::cout << out_shape[j] << (j != out_shape.size() - 1 ? ", " : "");
        }
        std::cout << "]" << std::endl;
        std::cout << "RL model loaded successfully!" << std::endl;
        return true;
    }

    void RlStandInference::StartInference(void* state, void* cmd)
    {

        // Directly use the 0-th input tensor
        auto inputTensor = infer_request.get_input_tensor(0);
        float* input_data = inputTensor.data<float>();
        size_t inputElements = inputTensor.get_size();

        // Ensure input is all zeros
        memset(input_data, 0, inputElements * sizeof(float));

        auto t1=std::chrono::steady_clock::now();
        // start inference
        infer_request.infer();
        auto t2=std::chrono::steady_clock::now();

        infer_stat.UpdateInferenceTime(std::chrono::duration<double,std::milli>(t2-t1).count());

        // Directly use the 0-th output tensor
        auto outputTensor = infer_request.get_output_tensor(0);
        const float* output_data = outputTensor.data<const float>();
        size_t outputElements = outputTensor.get_size();
    }

    void RlStandInference::Update(void* state, void* cmd)
    {
        auto t1=std::chrono::steady_clock::now();
        StartInference(state, cmd);
        auto t2=std::chrono::steady_clock::now();
        double dr_ms=std::chrono::duration<double,std::milli>(t2-t1).count();
    }
} // namespace inference
