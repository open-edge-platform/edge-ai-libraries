#include "inference_config.h"

namespace inference
{
    std::vector<std::string> InferenceConfig::splitKey(const std::string& key)
    {
        std::vector<std::string> keys;
        std::string processed_key = key;

        // Remove leading '/' if present
        if (!processed_key.empty() && processed_key[0] == '/') {
            processed_key = processed_key.substr(1);
        }

        std::stringstream ss(processed_key);
        std::string item;
        
        // Use '/' as delimiter
        while (std::getline(ss, item, '/')) {
            if (!item.empty()) {
                keys.push_back(item);
            }
        }
        return keys;
    }

    bool InferenceConfig::LoadFile(const std::string& filename)
    {
        try {
            config_ = YAML::LoadFile(filename);
            return true;
        } catch (const YAML::Exception& e) {
            std::cerr << "Error loading YAML file: " << e.what() << std::endl;
            return false;
        }
    }
} // namespace inference
