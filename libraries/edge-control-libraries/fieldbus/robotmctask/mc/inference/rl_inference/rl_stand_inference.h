#pragma once

#include "inference.h"

namespace inference
{
    class RlStandInference : public Inference
    {
    public:
        RlStandInference() = default;
        ~RlStandInference() override = default;

        bool Init(const std::string& policyfile, const std::string& config, const std::string& csvFile, std::string& device) override;
        bool LoadModel(const std::string& policyfile, const std::string& config, const std::string& device) override;
        void Update(void* state, void* cmd) override;
        size_t GetJointDim();

    protected:

    private:
        void StartInference(void* state, void* cmd);
        size_t _joint_dim = 15;
    };

} // namespace inference
