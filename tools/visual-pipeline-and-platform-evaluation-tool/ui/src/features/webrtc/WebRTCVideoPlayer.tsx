import { useEffect, useRef, useState } from "react";
import { MediaMTXWebRTCReader } from "./MediaMTXWebRTCReader.ts";

interface WebRTCVideoPlayerProps {
  pipelineId?: string;
}

const WebRTCVideoPlayer = ({ pipelineId }: WebRTCVideoPlayerProps) => {
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
    if (!pipelineId) {
      return;
    }

    const url = new URL(
      "whep",
      `${window.location.protocol}//${window.location.host}/streams/stream_${pipelineId}/`,
      //`http://<ip>:8889/stream_${pipelineId}/`,
    );

    const reader = new MediaMTXWebRTCReader({
      url: url.toString(),
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
  }, [defaultControls, pipelineId]);

  if (!pipelineId) {
    return null;
  }

  return (
    <div style={{ position: "relative" }}>
      <video ref={videoRef} style={{ maxHeight: 430 }} />
      {message && <div style={{ position: "absolute", top: 6 }}>{message}</div>}
    </div>
  );
};

export default WebRTCVideoPlayer;
