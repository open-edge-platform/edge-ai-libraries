#include "inference.h"

namespace inference
{
    bool Inference::Init(const std::string& policyfile, const std::string& config, const std::string& csvFile, std::string& device)
    {
        // Load policy model and rl cfg
        if (!LoadModel(policyfile, config, device))
        {
            std::cout << "[RlInference] Failed to load the model. Ensure the path is correct and accessible." << std::endl;
            return false;
        }
        return true;
    }

    bool Inference::LoadModel(const std::string& policyfile, const std::string& config, const std::string& device)
    {
        std::cout << "Load inference model from path : " << policyfile << std::endl;

        interpreter = ov_core.read_model(policyfile.c_str());
        compiled_model = ov_core.compile_model(interpreter, device);
        infer_request = compiled_model.create_infer_request();

        std::cout << "Inference model loaded successfully!" << std::endl;
        return true;
    }

} // namespace inference