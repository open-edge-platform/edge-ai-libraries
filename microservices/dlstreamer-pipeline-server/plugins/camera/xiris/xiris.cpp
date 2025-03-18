#include <xiris.hpp>

void setEWIcameraSettings()
{
	std::cout << "Setting Xiris camera settings" << std::endl;

    // set tone map curve
    const char* ToneMapCurveType = getenv("tone_map_curve_type");
    const char* ToneMapCurveValue = getenv("tone_map_curve_value");

    //set gamma based on weld studio slider value
    float weldStudioGammaSlider = atof(ToneMapCurveValue);
    std::unordered_map<std::string, ToneMapCurveTypes> ToneMapCurveTypeMap = {
        {"linear", ToneMapCurveTypes::Linear},
        {"gamma", ToneMapCurveTypes::Gamma},
        {"scurve", ToneMapCurveTypes::SCurve}
    };
    // pCamera->setToneMapCurve(ToneMapCurveTypeMap[ToneMapCurveType]);
    if (strcmp(ToneMapCurveType, "linear") == 0) {
        pCamera->setToneMapCurve(ToneMapCurveTypeMap[ToneMapCurveType]);
        pCamera->setToneMapGamma(weldStudioGammaSlider);
    }
    else if (strcmp(ToneMapCurveType, "gamma") == 0) {
        pCamera->setToneMapCurve(ToneMapCurveTypeMap[ToneMapCurveType]);
        float gamma = pow(10.0, weldStudioGammaSlider / 10.0);
        pCamera->setToneMapGamma(gamma);
        std::cout << "setting gamma to slider value " << weldStudioGammaSlider << " which is gamma value " << gamma << std::endl;
    }
    else if (strcmp(ToneMapCurveType, "scurve") == 0) {
        // pCamera->setToneMapGamma(weldStudioGammaSlider);
        std::cout << "Warning: SCurve is currently not supported\n";
    }
    else {
        std::cout << "Warning: Unknown tone_map_curve_type provided\n";
    }

	//set the image flip orientation
    const char* FlipMode = getenv("flip_mode");
    std::unordered_map<std::string, FlipModes> FlipModeMap = {
        {"None", FlipModes::None},
        {"FlipVertical", FlipModes::FlipVertical},
        {"FlipHorizontal", FlipModes::FlipHorizontal},
        {"FlipBoth", FlipModes::FlipBoth}
    };
    pCamera->setFlip(FlipModeMap[FlipMode]);
	
	//set sharpen
    const char* SetSharpen = getenv("set_sharpen");
    std::unordered_map<std::string, bool> SetSharpenMap = {
        {"true", true},
        {"false", false}
    };
	pCamera->setSharpen(SetSharpenMap[SetSharpen]);

    //set the shutter mode
    // global shutter is needed to prevent image tearing when welding is occuring
    const char* ShutterMode = getenv("shutter_mode");
    std::unordered_map<std::string, ShutterModes> ShutterModeMap = {
        {"Rolling", ShutterModes::Rolling},
        {"Global", ShutterModes::Global}
    };
    pCamera->setShutterMode(ShutterModeMap[ShutterMode]);

    //rolling frame rate currently not being used because global shutter is set by exposure time
    if (strcmp(ShutterMode, "Rolling") == 0) {
        const char* RollingFrameRateEnv = getenv("FrameRate");
        std::stringstream RollingFrameRateStr;
        RollingFrameRateStr << RollingFrameRateEnv;
        double RollingFrameRate;
        RollingFrameRateStr >> RollingFrameRate;

        pCamera->setRollingFrameRate(RollingFrameRate);
    }

    if (strcmp(ShutterMode, "Global") == 0) {
        const char* ExposureTimeEnv = getenv("exposure_time");
        std::stringstream ExposureTimeStr;
        ExposureTimeStr << ExposureTimeEnv;
        float ExposureTime;
        ExposureTimeStr >> ExposureTime;
        // Sets the Exposure time in micro-seconds.
        pCamera->setExposureTimeGlobal(ExposureTime);

        //set the auto expose mode
        const char* AutoExposureMode = getenv("auto_exposure_mode");
        std::unordered_map<std::string, AutoControlModes> AutoExposureModeMap = {
            {"Off", AutoControlModes::Off},
            {"Once", AutoControlModes::Once},
            {"Continuous", AutoControlModes::Continuous}
        };
        pCamera->setAutoExposureMode(AutoExposureModeMap[AutoExposureMode]);
    }

    const char* PixelDepth = getenv("pixel_depth");
    std::unordered_map<std::string, PixelDepths> pixelDepthMap = {
        {"8", PixelDepths::Bpp8},
        {"12", PixelDepths::Bpp12},
        {"14", PixelDepths::Bpp14},
        {"16", PixelDepths::Bpp16}
    };
    pCamera->setPixelDepth(pixelDepthMap[PixelDepth]);
}

void getCameraSettings()
{
	//get shutter mode
	WeldSDK::ShutterModes shutterMode = pCamera->getShutterMode();
	std::cout << "Shutter mode: " << static_cast<int>(shutterMode) << std::endl;
	if(shutterMode == WeldSDK::ShutterModes::Global)
	{
		std::cout <<  "ShutterModes::Global" << std::endl;
	}
	if(shutterMode == WeldSDK::ShutterModes::Rolling)
	{
		std::cout <<  "ShutterModes::Rolling" << std::endl;
	}

    std::cout << "FrameRate: " << pCamera->getRollingFrameRate() << std::endl;
    
	//get exposure time
	float ExposureTimeValue = pCamera->getExposureTimeGlobal();
	std::cout << "ExposureTimeValue: " << ExposureTimeValue << std::endl;

	//get auto exposure mode
	WeldSDK::AutoControlModes exposureMode = pCamera->getAutoExposureMode();
	std::cout << "auto exposure mode: " << static_cast<int>(exposureMode) << std::endl;
	if(exposureMode == WeldSDK::AutoControlModes::Off)
	{
		std::cout <<  "WeldSDK::AutoControlModes::Off" << std::endl;
	}
	if(exposureMode == WeldSDK::AutoControlModes::Once)
	{
		std::cout <<  "WeldSDK::AutoControlModes::Once" << std::endl;
	}
	if(exposureMode == WeldSDK::AutoControlModes::Continuous)
	{
		std::cout <<  "WeldSDK::AutoControlModes::Continuous" << std::endl;
	}

	//get pixel bit depth:
	WeldSDK::PixelDepths pixelDepth = pCamera->getPixelDepth();
    if(pixelDepth == WeldSDK::PixelDepths::Bpp8)
	{
		std::cout << "WeldSDK::PixelDepths::Bpp8" << std::endl;
	}
	if(pixelDepth == WeldSDK::PixelDepths::Bpp12)
	{
		std::cout << "WeldSDK::PixelDepths::Bpp12" << std::endl;
	}
	if(pixelDepth == WeldSDK::PixelDepths::Bpp14)
	{
		std::cout << "WeldSDK::PixelDepths::Bpp14" << std::endl;
	}
	if(pixelDepth == WeldSDK::PixelDepths::Bpp16)
	{
		std::cout << "WeldSDK::PixelDepths::Bpp16" << std::endl;
	}

	//get saturation
	//should be 0

    //get tone map curve	
	if(pCamera->getToneMapCurve() == ToneMapCurveTypes::Linear)
	{
		std::cout << "ToneMapCurveTypes::Linear" << std::endl;
	}
	if(pCamera->getToneMapCurve() == ToneMapCurveTypes::Gamma)
	{
		std::cout << "ToneMapCurveTypes::Gamma" << std::endl;
	}
	if(pCamera->getToneMapCurve() == ToneMapCurveTypes::SCurve)
	{
		std::cout << "ToneMapCurveTypes::SCurve" << std::endl;
	}

	//get gamma
	float gamma = pCamera->getToneMapGamma();
	float weldStudioGammaSlider_ret = log10(gamma) * 10.0;
	std::cout << "raw gamma: " << gamma << ", slider equivalent: " << weldStudioGammaSlider_ret << std::endl;

	//get focus
	int32_t focus = pCamera->getCurrentFocus(); //getCommandedFocus()??
	std::cout << "focus: " << focus << std::endl;

	//get image flip
	WeldSDK::FlipModes flip = pCamera->getFlip();
    if(flip == WeldSDK::FlipModes::None)
	{
		std::cout << "WeldSDK::FlipModes::None" << std::endl;
	}
    if(flip == WeldSDK::FlipModes::FlipVertical)
	{
		std::cout << "WeldSDK::FlipModes::FlipVertical" << std::endl;
	}
    if(flip == WeldSDK::FlipModes::FlipHorizontal)
	{
		std::cout << "WeldSDK::FlipModes::FlipHorizontal" << std::endl;
	}
	if(flip == WeldSDK::FlipModes::FlipBoth)
	{
		std::cout << "WeldSDK::FlipModes::FlipBoth" << std::endl;
	}

	//get sharpen
	bool sharpen = pCamera->getSharpen();
	std::cout << "sharpen (bool): " << sharpen << std::endl;


	//get video averaging length
	int32_t averagingLength = pCamera->getAveragingLength();
	std::cout << "averagingLength: " << averagingLength << std::endl;

	//get pilot light
	bool PilotLightOnStatus = pCamera->getLightOn();
	std::cout << "PilotLightOnStatus (bool): " << PilotLightOnStatus << std::endl;

	//get pilot light power
	int32_t PilotLightPowerValue = pCamera->getLightPower();
	std::cout << "PilotLightPowerValue: " << PilotLightPowerValue << std::endl;
}

/**
 * Called when a camera is ready.
 */
void XirisCameraEventSink::OnCameraReady(CameraReadyEventArgs args)
{
    if (args.IsReady)
    {
        std::cout << "\n\nCamera initial settings:\n\n";
        getCameraSettings();

        setEWIcameraSettings();

        std::cout << "\n\nCamera settings made by user:\n\n";

        getCameraSettings();

        std::cout << "Camera is ready, starting streaming\n";
        pCamera->Start();
    }
    else
    {
        std::cout << "Camera is not connected.\n";
    }
}

/**
 * Called when a new camera image buffer is ready.
 */
void XirisCameraEventSink::OnBufferReady(BufferReadyEventArgs args)
{
    // Here is where you would do something meaningful with the
    // image, like display it.

    if (firstTimestamp == 0)
    {
        firstTimestamp = args.Timestamp;
    }
    std::cout << (args.Timestamp - firstTimestamp) << " " << ++bufferCount << "\r";

    // Frame frame;
    // frame.data = args.RawImage->data;
    // frame.height = args.RawImage->height;
    // frame.width = args.RawImage->width;
    // frame.channels = args.RawImage->channels;
    // frame.bit_depth = args.RawImage->depth;
    // frame_queue.push(frame);

    size_t size = args.ToneMappedImage->height * args.ToneMappedImage->widthStep;
    char* data = new char[size];
    memcpy(data, args.ToneMappedImage->data, size);
    
    Frame frame;
    frame.data = data;
    frame.height = args.ToneMappedImage->height;
    frame.width = args.ToneMappedImage->width;
    frame.channels = args.ToneMappedImage->channels;
    frame.bit_depth = args.ToneMappedImage->depth;
    frame_queue.push(frame);
}

/**
 * Called when the camera changes streaming states.
 */
// virtual void OnStreamingStateChanged(CameraStreamingEventArgs args)
// {
// 	// Here you might update a GUI element
// 	if (args.IsStreaming)
// 	{
// 		// e.g. distable a "Start" button and enable a "Stop" button
// 	}
// 	else
// 	{
// 		// e.g. distable a "Stop" button and enable a "Start" button

// 	}
// }

/**
 * Called when the camera's reported capabilities change.
 */
void XirisCameraEventSink::OnDeviceCapabilitiesChanged(DeviceCapabilitiesEventArgs args)
{
    if (pCamera->getDeviceCapability().ColorSensor().IsAvailable())
        std::cout << "Sensor type: Color\n";
    else
        std::cout << "Sensor type: Mono\n";

    if (pCamera->getDeviceCapability().FocusControl().IsAvailable())
        std::cout << "Focus control: Yes\n";
    else
        std::cout << "Focus control: No\n";

	//set focus
    //this must be set after the focus controller is ready, in OnDeviceCapabilitiesChanged()
    const char* FocusEnv = getenv("focus");
    std::stringstream FocusStr;
    FocusStr << FocusEnv;
    int Focus;
    FocusStr >> Focus;
    pCamera->setCommandedFocus(Focus);
	
	//set pilot light
    const char* PilotLightOn = getenv("pilot_light_on");
    std::unordered_map<std::string, bool> PilotLightOnMap = {
        {"true", true},
        {"false", false}
    };
	pCamera->setLightOn(PilotLightOnMap[PilotLightOn]);

	//set pilot light power
    //this must be set after the focus controller is ready, in OnDeviceCapabilitiesChanged()
    const char* PilotLightPowerEnv = getenv("pilot_light_power");
    std::stringstream PilotLightPowerStr;
    PilotLightPowerStr << PilotLightPowerEnv;
    int PilotLightPower;
    PilotLightPowerStr >> PilotLightPower;
    pCamera->setLightPower(PilotLightPower);

    std::cout << "\n\nCamera settings after device capabilities changed that affects focus and pilot light:\n\n";
    getCameraSettings();
}


/**
 * Called when a camera is detected.
 */
void XirisDetectorEventSink::OnCameraDetected(CameraEventArgs args)
{
    if (args.CanConnect)
    {
        pCamera = std::make_unique <WeldCamera>();
        pCameraEvents = std::make_unique<XirisCameraEventSink>();

        pCamera->AttachEventSink(pCameraEvents.get());
        std::string CameraIP;
        char* XirisCameraIP = getenv("XirisCameraIP");
        if (XirisCameraIP != NULL)
        {
            std::cout << "XirisCameraIP env variable is set.. connecting to camera IP:" << XirisCameraIP << std::endl;
            if (XirisCameraIP != args.CameraIPAddress)
            {
                std::cout << "Wrong XirisCameraIP provided. Using auto discovery of the correct IP..." << std::endl;
                CameraIP = args.CameraIPAddress;
            }
            else {
                CameraIP = XirisCameraIP;
            }
        } else {
                std::cout << "XirisCameraIP env variable is not set.. using auto discovery\n";
                CameraIP = args.CameraIPAddress;
        }
        pCamera->Connect(CameraIP, args.CameraType);
    }
}

/**
 * Called when a camera disconnects.
 */
void XirisDetectorEventSink::OnCameraDisconnected(CameraEventArgs args)
{
    std::cout << "Camera disconnected. MAC=" << args.CameraMACAddress << " IP=" << args.CameraIPAddress << "\n";
}

/**
 * Called when the camera detector produces a log message.
 */
void XirisDetectorEventSink::OnLogMessage(LogMessageArgs args)
{
    // Only output critical messages
    if (args.Level == 0)
        std::cout << args.Message << std::endl;
}

extern "C"
Frame get_frame()
{
	if (!frame_queue.empty()) {
		Frame frame = frame_queue.front();
		frame_queue.pop();
		return frame;
	} else {
		Frame frame = {NULL,0,0,0,0};
		return frame;
	}

}

extern "C"
void free_frame(char* dataPtr)
{
    // std::cout << "extern c free_frame()" << std::endl;
    delete[] dataPtr;
}

extern "C"
void start()
{
	// Create an attach an event sink for the CameraDetector
	CameraDetector::GetInstance()->AttachEventSink(&detectorEvents);

        std::cout << "Start called..\n";
}

extern "C"
void stop()
{

        // Disconnect the event sink and camera
        std::cout << "stop called..\n";
	CameraDetector::GetInstance()->DetachEventSink(&detectorEvents);
        if (pCamera)
        {
                if (pCameraEvents)
                        pCamera->DetachEventSink(pCameraEvents.get());

                pCamera->Disconnect();
        }
}