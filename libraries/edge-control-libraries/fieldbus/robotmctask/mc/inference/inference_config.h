#pragma once

#include <iostream>
#include <vector>
#include <string>
#include <yaml-cpp/yaml.h>

namespace inference
{
    class InferenceConfig
    {
    public:
        InferenceConfig() = default;
        virtual ~InferenceConfig() = default;

        bool LoadFile(const std::string& filename);
        template<typename T>
        bool getParam(const std::string& key, T& Value)
        {
            try {
                    std::vector<std::string> keys = splitKey(key);
                    YAML::Node current = YAML::Clone(config_);

                    for (const auto& k : keys){
                        if (current[k].IsDefined()) {
                            current = current[k];
                        } else {
                            std::cerr << "Error getting value for key '" << key << "' " << std::endl;
                            return false;
                        }
                    }
                    //std::cerr << "getting value for key '" << key << "' "<< current << "' " << std::endl;
                    Value = current.as<T>();

                    return true;
                } catch (const YAML::Exception& e) {
                    std::cerr << "Error getting value for key '" << key << "'： " << e.what() << std::endl;
                    return false;
            }
            return false;
        }

    private:
        YAML::Node config_;
        std::vector<std::string> splitKey(const std::string& key);
        template<typename T>
        std::string vectorToString(const std::vector<T>& vec) {
            std::ostringstream oss;
            oss << "[";
            for (size_t i = 0; i < vec.size(); ++i) {
                oss << "\"" << vec[i] << "\"";
                if (i < vec.size() - 1) {
                    oss << ", ";
                }
            }
            oss << "]";
            return oss.str();
        }
    };
} // namespace inference