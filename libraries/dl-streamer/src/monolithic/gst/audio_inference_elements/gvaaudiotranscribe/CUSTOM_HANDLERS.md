# Custom Audio Transcription Handlers

This document explains how to implement custom model handlers for the GVA Audio Transcribe element.

## Overview

The GVA Audio Transcribe element uses an extensible handler interface that allows you to implement support for custom speech recognition models. Currently, Whisper is the only supported model type, but you can easily add support for other models.

## Implementing a Custom Handler

### 1. Create Handler Class

Create a new handler class that inherits from `GvaAudioTranscribeHandler`:

```cpp
#pragma once
#include "gstgvaaudiotranscribehandler.h"
#include <your_model_library.h>

class CustomModelHandler : public GvaAudioTranscribeHandler {
public:
    bool initialize(const std::string &model_path, const std::string &device,
                    const std::string &language, const std::string &task,
                    bool return_timestamps) override;

    std::string transcribe(const std::vector<float> &audio_data, GstBuffer *buf) override;

    void cleanup() override;

    std::map<std::string, std::string> get_info() const override;

private:
    // Your model-specific members
    YourModelType *model = nullptr;
    // Other configuration objects
};
```

### 2. Implement Required Methods

#### initialize()
Set up your model and configuration:

```cpp
bool CustomModelHandler::initialize(const std::string &model_path, const std::string &device,
                                    const std::string &language, const std::string &task,
                                    bool return_timestamps) {
    try {
        // Load your model
        model = new YourModelType(model_path, device);
        
        // Configure model settings
        model->set_language(language);
        model->set_task(task);
        model->set_timestamps(return_timestamps);
        
        GST_INFO("CustomModelHandler initialized successfully");
        return true;
    } catch (const std::exception &e) {
        GST_ERROR("CustomModelHandler initialization failed: %s", e.what());
        cleanup();
        return false;
    }
}
```

#### transcribe()
Perform the actual transcription:

```cpp
std::string CustomModelHandler::transcribe(const std::vector<float> &audio_data, GstBuffer *buf) {
    if (!model) {
        GST_ERROR("CustomModelHandler not initialized");
        return {};
    }
    
    try {
        // Your model's transcription logic
        auto result = model->transcribe(audio_data);
        return result.text;
    } catch (const std::exception &e) {
        GST_ERROR("CustomModelHandler transcription failed: %s", e.what());
        return {};
    }
}
```

#### cleanup()
Clean up resources:

```cpp
void CustomModelHandler::cleanup() {
    if (model) {
        delete model;
        model = nullptr;
    }
    GST_DEBUG("CustomModelHandler cleaned up");
}
```

#### get_info()
Provide handler information:

```cpp
std::map<std::string, std::string> CustomModelHandler::get_info() const {
    return {
        {"handler_type", "custom_model"},
        {"backend", "your_backend_name"},
        {"description", "Your custom model description"},
        {"status", "active"}
    };
}
```

### 3. Register Your Handler

Modify the `gst_gva_audio_transcribe_start()` function in `gstgvaaudiotranscribe.cpp` to include your handler:

```cpp
// Add your handler include
#include "yourcustomhandler.h"

// In the start function, add your model type check:
if (g_strcmp0(gvaaudiotranscribe->model_type, "whisper") == 0) {
    gvaaudiotranscribe->handler = new WhisperHandler();
} else if (g_strcmp0(gvaaudiotranscribe->model_type, "your_model_type") == 0) {
    gvaaudiotranscribe->handler = new CustomModelHandler();
} else {
    // Error message for unsupported types...
}
```

## Usage Example

Once implemented, users can use your custom handler like this:

```bash
gst-launch-1.0 audiotestsrc ! audioconvert ! audioresample ! \
    "audio/x-raw,format=S16LE,rate=16000,channels=1" ! \
    gvaaudiotranscribe model=/path/to/your/model model_type=your_model_type device=CPU ! \
    fakesink
```

## Audio Data Format

The `audio_data` parameter in `transcribe()` contains:
- Normalized float values (range: -1.0 to 1.0)
- 16kHz sample rate
- Mono channel (single channel)
- Raw audio samples ready for processing

## Best Practices

1. **Error Handling**: Always use try-catch blocks and provide meaningful error messages
2. **Resource Management**: Implement proper cleanup in both `cleanup()` and destructors
3. **Thread Safety**: The handler may be called from different threads, ensure thread safety if needed
4. **Logging**: Use GST_INFO, GST_DEBUG, GST_ERROR for consistent logging
5. **Memory Management**: Avoid memory leaks, use smart pointers when possible

## Contributing

If you implement a useful handler, consider contributing it back to the project:

1. Create a new header and implementation file
2. Add proper documentation
3. Include example usage
4. Submit a pull request

## Troubleshooting

- **Handler not found**: Ensure your handler is properly registered in the start function
- **Initialization fails**: Check model path, device availability, and dependencies
- **No transcription output**: Verify audio format compatibility and model configuration
- **Build errors**: Ensure all dependencies are properly linked

For more examples, see:
- The `WhisperHandler` implementation in `gstgvawhisperasrhandler.cpp` 
- The example custom handler in `examples/example_custom_handler.h` and `examples/example_custom_handler.cpp`