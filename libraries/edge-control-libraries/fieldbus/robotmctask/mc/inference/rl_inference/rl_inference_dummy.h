#pragma once

#include "inference.h"

namespace inference
{
    class RlInferenceDummy : public Inference
    {
    public:
        RlInferenceDummy() = default;
        ~RlInferenceDummy() override = default;

        bool Init(const std::string& policyfile, const std::string& config, const std::string& csvFile, std::string& device) override;
        bool LoadModel(const std::string& policyfile, const std::string& config, const std::string& device) override;
        void Update(void* state, void* cmd) override;

    protected:

    private:
        void StartInference(void* state, void* cmd);
    };

} // namespace inference