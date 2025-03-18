#include <cstdint>
#include <cstdio>
#include <iostream>
#include <memory>
#include <queue>
#include <fstream>
#include <cstdlib>
#include <string.h>

// Include the WeldSDK library header
#include "WeldSDK/WeldSDK.h"
using namespace WeldSDK;

// Pointer to the WeldCamera object
std::unique_ptr<WeldCamera> pCamera;
// Pointer to a CameraEventSink-inheriting object
std::unique_ptr<CameraEventSink> pCameraEvents;

// Buffer counter
uint32_t bufferCount = 0;
double	 firstTimestamp = 0;

#include "XVideoRecorderLib/XVideoRecorder.h"
using XVideoStream::XVideoRecorderLib::CXVideoRecorder;
std::shared_ptr<CXVideoRecorder> videoRecorder = std::make_shared<CXVideoRecorder>();

struct Frame {
	char* data;
	int height;
	int width;
	int channels;
	int bit_depth;
};

std::queue<Frame> frame_queue;

class XirisCameraEventSink : public CameraEventSink
{
public:
	/**
	 * Called when a camera is ready.
	 */
	virtual void OnCameraReady(CameraReadyEventArgs args);

	/**
	 * Called when a new camera image buffer is ready.
	 */
	virtual void OnBufferReady(BufferReadyEventArgs args);

	/**
	 * Called when the camera changes streaming states.
	 */
	// virtual void OnStreamingStateChanged(CameraStreamingEventArgs args);

	/**
	 * Called when the camera's reported capabilities change.
	 */
	virtual void OnDeviceCapabilitiesChanged(DeviceCapabilitiesEventArgs args);

};

class XirisDetectorEventSink : public CameraDetectorEventSink
{
public:
	/**
	 * Called when a camera is detected.
	 */
	virtual void OnCameraDetected(CameraEventArgs args);
	/**
	 * Called when a camera disconnects.
	 */
	virtual void OnCameraDisconnected(CameraEventArgs args);
	/**
	 * Called when the camera detector produces a log message.
	 */
	virtual void OnLogMessage(LogMessageArgs args);
};

XirisDetectorEventSink detectorEvents;