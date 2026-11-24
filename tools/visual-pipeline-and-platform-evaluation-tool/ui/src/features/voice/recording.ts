// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

function encodeWav(audio: AudioBuffer): Blob {
  const buffer = new ArrayBuffer(44 + audio.length * 2);
  const view = new DataView(buffer);
  const writeText = (offset: number, text: string) => {
    for (let index = 0; index < text.length; index++) {
      view.setUint8(offset + index, text.charCodeAt(index));
    }
  };
  writeText(0, "RIFF");
  view.setUint32(4, 36 + audio.length * 2, true);
  writeText(8, "WAVE");
  writeText(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, audio.sampleRate, true);
  view.setUint32(28, audio.sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeText(36, "data");
  view.setUint32(40, audio.length * 2, true);
  const samples = audio.getChannelData(0);
  for (let index = 0; index < samples.length; index++) {
    const sample = Math.max(-1, Math.min(1, samples[index]));
    view.setInt16(44 + index * 2, sample * (sample < 0 ? 32768 : 32767), true);
  }
  return new Blob([buffer], { type: "audio/wav" });
}

export async function captureWav(
  signal: AbortSignal,
  onStarted: (stop: () => void) => void,
): Promise<File> {
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    throw new Error(
      "Microphone recording requires HTTPS or localhost and a supported browser.",
    );
  }
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
  });
  try {
    signal.throwIfAborted();
    const recording = await new Promise<Blob>((resolve, reject) => {
      const recorder = new MediaRecorder(stream);
      const chunks: Blob[] = [];
      let size = 0;
      let tooLarge = false;
      const stop = () => {
        if (recorder.state !== "inactive") recorder.stop();
      };
      const abort = () => stop();
      const timer = window.setTimeout(stop, 60_000);
      const cleanup = () => {
        window.clearTimeout(timer);
        signal.removeEventListener("abort", abort);
        stream.getTracks().forEach((track) => track.stop());
      };
      signal.addEventListener("abort", abort, { once: true });
      recorder.ondataavailable = (event) => {
        size += event.data.size;
        if (size > 10 * 1024 * 1024) {
          tooLarge = true;
          stop();
        } else {
          chunks.push(event.data);
        }
      };
      recorder.onerror = () => {
        cleanup();
        reject(new Error("Microphone recording failed."));
      };
      recorder.onstop = () => {
        cleanup();
        if (signal.aborted) reject(signal.reason);
        else if (tooLarge)
          reject(new Error("Recording exceeds the 10 MiB limit."));
        else resolve(new Blob(chunks, { type: recorder.mimeType }));
      };
      try {
        recorder.start(250);
        onStarted(stop);
      } catch (error) {
        cleanup();
        reject(error);
      }
    });
    signal.throwIfAborted();
    const context = new AudioContext();
    let decoded: AudioBuffer;
    try {
      decoded = await context.decodeAudioData(await recording.arrayBuffer());
    } finally {
      await context.close();
    }
    signal.throwIfAborted();
    const renderer = new OfflineAudioContext(
      1,
      Math.min(60 * 16000, Math.ceil(decoded.duration * 16000)),
      16000,
    );
    const source = renderer.createBufferSource();
    source.buffer = decoded;
    source.connect(renderer.destination);
    source.start();
    const rendered = await renderer.startRendering();
    signal.throwIfAborted();
    return new File([encodeWav(rendered)], "recording.wav", {
      type: "audio/wav",
    });
  } finally {
    stream.getTracks().forEach((track) => track.stop());
  }
}
