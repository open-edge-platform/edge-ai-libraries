import { useEffect, useRef, useState } from "react";
import { MediaMTXWebRTCReader } from "./MediaMTXWebRTCReader.ts";

interface WebRTCVideoPlayerProps {
  pipelineId?: string;
  streamUrl?: string;
}

const WebRTCVideoPlayer = ({
  pipelineId,
  streamUrl,
}: WebRTCVideoPlayerProps) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [message, setMessage] = useState<string>("");
  const [defaultControls, setDefaultControls] = useState<boolean>(true);

  const parseBoolString = (
    str: string | null,
    defaultVal: boolean,
  ): boolean => {
    str = str ?? "";
    if (["1", "yes", "true"].includes(str.toLowerCase())) return true;
    if (["0", "no", "false"].includes(str.toLowerCase())) return false;
    return defaultVal;
  };

  // Load video attributes from query string
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const controls = parseBoolString(params.get("controls"), true);
    const muted = parseBoolString(params.get("muted"), true);
    const autoplay = parseBoolString(params.get("autoplay"), true);
    const playsInline = parseBoolString(params.get("playsinline"), true);

    if (videoRef.current) {
      videoRef.current.controls = controls;
      videoRef.current.muted = muted;
      videoRef.current.autoplay = autoplay;
      videoRef.current.playsInline = playsInline;
    }
    setDefaultControls(controls);
  }, []);

  useEffect(() => {
    if (!pipelineId && !streamUrl) {
      return;
    }

    let whepPath: string;
    if (streamUrl) {
      // Convert RTSP URL to WHEP URL
      // RTSP format: rtsp://mediamtx:8554/stream-name
      // Extract stream name and build relative WHEP URL for proxy
      if (streamUrl.startsWith("rtsp://")) {
        const rtspUrl = new URL(streamUrl);
        const streamName = rtspUrl.pathname.substring(1); // Remove leading '/'
        // Use relative URL to leverage Vite/nginx proxy
        whepPath = `/${streamName}/whep`;
      } else {
        // Assume it's already a WHEP URL
        whepPath = streamUrl;
      }
    } else {
      // Build URL from pipelineId
      whepPath = `/stream_${pipelineId}/whep`;
    }

    // Convert relative path to absolute URL
    const absoluteUrl = new URL(whepPath, window.location.origin).toString();

    const reader = new MediaMTXWebRTCReader({
      url: absoluteUrl,
      onError: (err: string) => {
        setMessage(err);
        if (videoRef.current) videoRef.current.controls = false;
      },
      onTrack: (evt: RTCTrackEvent) => {
        setMessage("");
        if (videoRef.current) {
          videoRef.current.srcObject = evt.streams[0];
          videoRef.current.controls = defaultControls;
        }
      },
    });

    return () => {
      reader?.close();
    };
  }, [defaultControls, pipelineId, streamUrl]);

  if (!pipelineId && !streamUrl) {
    return null;
  }

  return (
    <div className="relative h-full w-full">
      <video ref={videoRef} className="h-full w-full object-cover" />
      {message && (
        <div className="absolute top-1.5 left-1.5 rounded bg-black/50 px-2 py-1 text-xs text-white">
          {message}
        </div>
      )}
    </div>
  );
};

export default WebRTCVideoPlayer;
