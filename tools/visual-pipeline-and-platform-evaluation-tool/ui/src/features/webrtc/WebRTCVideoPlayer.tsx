import { useEffect, useRef, useState } from "react";
import { MediaMTXWebRTCReader } from "./MediaMTXWebRTCReader.ts";
import { buildWhepUrl } from "./whepUrl.ts";

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

    const whepUrl = buildWhepUrl(window.location.origin, streamUrl, pipelineId);
    if (!whepUrl) {
      setMessage(
        "Live preview unavailable: the pipeline reported an unusable stream address. Restart the pipeline, and check the vippet service logs if it persists.",
      );
      if (videoRef.current) videoRef.current.controls = false;
      return;
    }

    const reader = new MediaMTXWebRTCReader({
      url: whepUrl,
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
