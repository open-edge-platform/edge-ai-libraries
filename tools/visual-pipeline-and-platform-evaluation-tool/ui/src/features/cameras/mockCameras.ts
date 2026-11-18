import { type Camera } from "@/api/api.generated.ts";

const isMockCamerasFromEnv = import.meta.env.VITE_MOCK_CAMERAS === "1";

const isMockCamerasFromQuery =
  typeof window !== "undefined" &&
  new URLSearchParams(window.location.search).get("mockCameras") === "1";

export const isCameraMockEnabled =
  isMockCamerasFromEnv || isMockCamerasFromQuery;

export const mockCameras: Camera[] = [
  {
    device_id: "usb-1",
    device_name: "Thronmax StreamGo Webcam: Thron",
    device_type: "USB",
    details: {
      device_path: "/dev/video2",
      best_capture: {
        fourcc: "MJPG",
        width: 1920,
        height: 1080,
        fps: 30,
      },
    },
  },
  {
    device_id: "usb-2",
    device_name: "C270 HD WEBCAM",
    device_type: "USB",
    details: {
      device_path: "/dev/video0",
      best_capture: {
        fourcc: "MJPG",
        width: 1280,
        height: 720,
        fps: 30,
      },
    },
  },
  {
    device_id: "net-1",
    device_name: "ONVIF Camera 10.91.106.249",
    device_type: "NETWORK",
    details: {
      ip: "10.91.106.249",
      port: 1000,
      profiles: [],
      best_profile: null,
    },
  },
  {
    device_id: "gige-camera-basler-12345678",
    device_name: "Basler acA1920-25gc",
    device_type: "GIGE",
    details: {
      ip: "192.168.10.50",
      vendor: "Basler",
      model: "acA1920-25gc",
      serial: "12345678",
      current_capture: {
        pixel_format: "BayerRG8",
        width: 1920,
        height: 1080,
        fps: 25,
      },
    },
  },
];
