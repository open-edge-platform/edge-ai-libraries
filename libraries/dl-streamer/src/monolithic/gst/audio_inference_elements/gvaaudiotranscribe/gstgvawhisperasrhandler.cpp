#include "gstgvawhisperasrhandler.h"
#include <gst/gst.h>

bool WhisperHandler::initialize(const std::string &model_path, const std::string &device,
                                const std::string &language, const std::string &task,
                                bool return_timestamps) {
    try {
        GST_INFO("Initializing Whisper handler with model: %s, device: %s", 
                 model_path.c_str(), device.c_str());
                 
        pipeline = new ov::genai::WhisperPipeline(model_path, device);
        config = new ov::genai::WhisperGenerationConfig();
        *config = pipeline->get_generation_config();
        
        config->language = language;
        config->task = task;
        config->return_timestamps = return_timestamps;
        
        GST_INFO("WhisperHandler initialized successfully (language=%s, task=%s, timestamps=%s)", 
                 language.c_str(), task.c_str(), return_timestamps ? "true" : "false");
        return true;
    } catch (const std::exception &e) {
        GST_ERROR("WhisperHandler initialization failed: %s", e.what());
        cleanup(); // Ensure clean state on failure
        return false;
    }
}

std::string WhisperHandler::transcribe(const std::vector<float> &audio_data, GstBuffer * /*buf*/) {
    if (!pipeline || !config) {
        GST_ERROR("WhisperHandler not properly initialized");
        return {};
    }
    
    try {
        ov::genai::RawSpeechInput input = audio_data;
        auto result = pipeline->generate(input, *config);
        
        if (result.texts.empty()) {
            GST_DEBUG("WhisperHandler: No transcription result");
            return {};
        }
        
        return result.texts[0];
    } catch (const std::exception &e) {
        GST_ERROR("WhisperHandler transcription failed: %s", e.what());
        return {};
    }
}

void WhisperHandler::cleanup() {
    if (pipeline) { 
        delete pipeline; 
        pipeline = nullptr; 
    }
    if (config) { 
        delete config; 
        config = nullptr; 
    }
    GST_DEBUG("WhisperHandler cleaned up");
}

std::map<std::string, std::string> WhisperHandler::get_info() const {
    return {
        {"handler_type", "whisper"},
        {"backend", "openvino_genai"},
        {"description", "OpenVINO GenAI Whisper speech recognition"},
        {"status", "active"}
    };
}
