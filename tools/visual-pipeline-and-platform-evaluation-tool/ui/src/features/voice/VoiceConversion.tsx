// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useRef, useState } from "react";
import {
  Download,
  FileAudio,
  LoaderCircle,
  Mic,
  Square,
  Upload,
  Volume2,
  X,
} from "lucide-react";
import { API_BASE_URL } from "@/api/apiSlice";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { MetricsDashboard } from "@/features/metrics/MetricsDashboard";
import { captureWav } from "./recording";
import { VoiceMetrics, type ConversionMetrics } from "./VoiceMetrics";
import { VoiceAudio } from "./VoiceAudio";

const SAMPLE_TEXTS = [
  "Welcome to Intel Performance Studio.",
  "Your audio is ready for playback.",
  "Hello, how can I assist you today?",
];

const SPEECH_VOICES = [
  "Ryan",
  "Miles",
  "Aaron",
  "Nora",
  "Elena",
  "Kabir",
  "Angus",
] as const;
type SpeechVoice = (typeof SPEECH_VOICES)[number];

function readConversionMetrics(
  response: Response,
  requestMs: number,
): ConversionMetrics {
  const raw = response.headers.get("X-Voice-Service-Duration-Ms");
  const serviceMs = raw && /^\d+(?:\.\d+)?$/.test(raw) ? Number(raw) : NaN;
  return {
    requestMs,
    serviceMs: Number.isFinite(serviceMs) ? serviceMs : null,
  };
}

async function checkResponse(response: Response): Promise<void> {
  if (response.ok) return;
  let detail: unknown;
  try {
    const payload: unknown = await response.json();
    if (payload && typeof payload === "object" && "detail" in payload)
      detail = payload.detail;
  } catch {
    // Non-JSON responses can originate from the reverse proxy.
  }
  throw new Error(
    typeof detail === "string"
      ? detail
      : response.status === 413
        ? "The input exceeds the upload limit."
        : `Conversion failed (HTTP ${response.status}). Check the input and service availability.`,
  );
}

function useAudioUrl(file: Blob | null): string | undefined {
  const [url, setUrl] = useState<string>();
  useEffect(() => {
    if (!file) {
      setUrl(undefined);
      return;
    }
    const nextUrl = URL.createObjectURL(file);
    setUrl(nextUrl);
    return () => URL.revokeObjectURL(nextUrl);
  }, [file]);
  return url;
}

export function VoiceConversion() {
  const [activeTab, setActiveTab] = useState("stt");
  const [file, setFile] = useState<File | null>(null);
  const [language, setLanguage] = useState("en");
  const [text, setText] = useState("");
  const [voice, setVoice] = useState<SpeechVoice>("Ryan");
  const [transcription, setTranscription] = useState<string | null>(null);
  const [speech, setSpeech] = useState<Blob | null>(null);
  const [sttMetrics, setSttMetrics] = useState<ConversionMetrics | null>(null);
  const [ttsMetrics, setTtsMetrics] = useState<ConversionMetrics | null>(null);
  const [showPlatformMetrics, setShowPlatformMetrics] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<
    | "idle"
    | "starting"
    | "recording"
    | "encoding"
    | "transcribing"
    | "synthesizing"
  >("idle");
  const operation = useRef<AbortController | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);
  const stopRecording = useRef<(() => void) | null>(null);
  const inputUrl = useAudioUrl(file);
  const speechUrl = useAudioUrl(speech);
  const busy = status !== "idle";

  useEffect(() => () => operation.current?.abort(), []);

  function cancel() {
    operation.current?.abort();
    operation.current = null;
    stopRecording.current = null;
    setStatus("idle");
  }

  function updateText(value: string) {
    setText(value);
    setSpeech(null);
    setTtsMetrics(null);
    setError(null);
  }

  function updateVoice(value: SpeechVoice) {
    setVoice(value);
    setSpeech(null);
    setTtsMetrics(null);
    setError(null);
  }

  async function run(kind: "record" | "stt" | "tts") {
    operation.current?.abort();
    const controller = new AbortController();
    operation.current = controller;
    setError(null);
    if (kind === "tts") {
      setSpeech(null);
      setTtsMetrics(null);
    } else {
      setTranscription(null);
      setSttMetrics(null);
    }
    setStatus(
      kind === "record"
        ? "starting"
        : kind === "stt"
          ? "transcribing"
          : "synthesizing",
    );
    const timer = window.setTimeout(
      () => controller.abort(new Error("Conversion timed out.")),
      130_000,
    );
    try {
      if (kind === "record") {
        const recording = await captureWav(controller.signal, (stop) => {
          stopRecording.current = stop;
          setStatus("recording");
        });
        controller.signal.throwIfAborted();
        setFile(recording);
        setTranscription(null);
      } else if (kind === "stt" && file) {
        const data = new FormData();
        data.append("file", file);
        data.append("language", language);
        const startedAt = performance.now();
        const response = await fetch(`${API_BASE_URL}/voice/transcriptions`, {
          method: "POST",
          body: data,
          signal: controller.signal,
          cache: "no-store",
        });
        await checkResponse(response);
        const result: unknown = await response.json();
        if (
          !result ||
          typeof result !== "object" ||
          !("text" in result) ||
          typeof result.text !== "string"
        ) {
          throw new Error("The service returned an invalid transcription.");
        }
        controller.signal.throwIfAborted();
        if (operation.current !== controller) return;
        setTranscription(result.text);
        setSttMetrics(
          readConversionMetrics(response, performance.now() - startedAt),
        );
      } else if (kind === "tts") {
        const startedAt = performance.now();
        const response = await fetch(`${API_BASE_URL}/voice/speech`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ input: text.trim(), voice }),
          signal: controller.signal,
          cache: "no-store",
        });
        await checkResponse(response);
        const result = await response.blob();
        controller.signal.throwIfAborted();
        if (operation.current !== controller) return;
        setSpeech(result);
        setTtsMetrics(
          readConversionMetrics(response, performance.now() - startedAt),
        );
      }
    } catch (failure) {
      if (operation.current === controller) {
        setError(
          failure instanceof Error ? failure.message : "Conversion failed.",
        );
      }
    } finally {
      window.clearTimeout(timer);
      if (operation.current === controller) {
        operation.current = null;
        stopRecording.current = null;
        setStatus("idle");
      }
    }
  }

  return (
    <div className="min-h-full w-full min-w-0 bg-muted text-foreground [color-scheme:light] dark:[color-scheme:dark]">
      <header className="bg-primary px-5 py-4 text-primary-foreground sm:px-8">
        <p className="mb-2 text-xs">
          Voice / {activeTab === "stt" ? "Speech to text" : "Text to speech"}
        </p>
        <h1 className="text-2xl font-medium">
          {activeTab === "stt"
            ? "Automatic Speech Recognition"
            : "Text to Speech"}
        </h1>
      </header>
      <div className="mx-auto w-full max-w-[1600px] px-4 py-4 sm:px-8">
        <Tabs
          value={activeTab}
          onValueChange={(value) => {
            cancel();
            setError(null);
            setActiveTab(value);
          }}
        >
          <TabsList className="mb-4 grid h-auto w-full max-w-lg grid-cols-2">
            <TabsTrigger value="stt" className="min-h-10 whitespace-normal">
              <Mic />
              Speech to text
            </TabsTrigger>
            <TabsTrigger value="tts" className="min-h-10 whitespace-normal">
              <Volume2 />
              Text to speech
            </TabsTrigger>
          </TabsList>
          <TabsContent value="stt" className="space-y-6">
            <div className="space-y-4 bg-background p-4 sm:p-5">
              <h2 className="text-base font-semibold">
                Automatic Speech Recognition Workload Configuration
              </h2>
              <section className="min-w-0 space-y-4">
                <h3 className="text-sm font-medium">Select source</h3>
                <div className="grid gap-4 md:max-w-4xl md:grid-cols-2">
                  <div className="space-y-3 rounded-sm bg-muted p-3">
                    <h4 className="text-xs text-muted-foreground">
                      Record audio
                    </h4>
                    <Button
                      variant="outline"
                      className="h-24 w-full flex-col gap-2 whitespace-normal border-border bg-background"
                      disabled={busy && status !== "recording"}
                      onClick={() => {
                        if (status === "recording") {
                          stopRecording.current?.();
                          setStatus("encoding");
                        } else {
                          void run("record");
                        }
                      }}
                      aria-label={
                        status === "recording" ? "Stop recording" : "Record"
                      }
                    >
                      {status === "recording" ? (
                        <Square className="size-6 text-destructive" />
                      ) : (
                        <Mic className="size-6 text-brand-accent" />
                      )}
                      <span>
                        {status === "recording"
                          ? "Stop recording"
                          : "Record from microphone"}
                      </span>
                      <span className="text-xs font-normal text-muted-foreground">
                        Up to 60 seconds
                      </span>
                    </Button>
                  </div>
                  <div className="space-y-3 rounded-sm bg-muted p-3">
                    <Label
                      htmlFor="voice-file"
                      className="text-xs font-normal text-muted-foreground"
                    >
                      WAV file
                    </Label>
                    <Button
                      variant="outline"
                      disabled={busy}
                      onClick={() => fileInput.current?.click()}
                      className="h-24 w-full flex-col gap-2 whitespace-normal border-border bg-background"
                    >
                      <Upload className="size-6 text-brand-accent" />
                      <span>Upload WAV</span>
                      <span className="text-xs font-normal text-muted-foreground">
                        Mono PCM 16-bit / 10 MiB maximum
                      </span>
                    </Button>
                    <Input
                      ref={fileInput}
                      id="voice-file"
                      type="file"
                      className="sr-only"
                      tabIndex={-1}
                      accept=".wav,audio/wav"
                      disabled={busy}
                      onChange={(event) => {
                        const selected = event.target.files?.[0];
                        setError(null);
                        setTranscription(null);
                        setSttMetrics(null);
                        setFile(null);
                        if (!selected) return;
                        if (
                          !selected.name.toLowerCase().endsWith(".wav") ||
                          selected.size > 10 * 1024 * 1024 ||
                          selected.size === 0
                        ) {
                          setError("Select a non-empty WAV file up to 10 MiB.");
                          event.target.value = "";
                          return;
                        }
                        setFile(selected);
                      }}
                    />
                  </div>
                </div>
                <div className="max-w-sm space-y-2 bg-muted p-3">
                  <Label htmlFor="voice-language">Recognition language</Label>
                  <select
                    id="voice-language"
                    value={language}
                    disabled={busy}
                    onChange={(event) => {
                      setLanguage(event.target.value);
                      setTranscription(null);
                      setSttMetrics(null);
                    }}
                    className="border-input bg-background h-10 w-full rounded-md border px-3 text-sm"
                  >
                    <option value="en">English</option>
                    <option value="pl">Polish</option>
                    <option value="de">German</option>
                    <option value="fr">French</option>
                    <option value="es">Spanish</option>
                  </select>
                </div>
                {file && (
                  <p className="text-muted-foreground break-all text-sm">
                    Selected file: {file.name}
                  </p>
                )}
                {inputUrl && (
                  <VoiceAudio
                    src={inputUrl}
                    label="Input recording"
                    title="Selected audio"
                  />
                )}
                <div className="flex justify-end">
                  <Button
                    disabled={!file || busy}
                    onClick={() => void run("stt")}
                  >
                    <FileAudio />
                    Transcribe
                  </Button>
                </div>
              </section>
              <section className="min-w-0 space-y-4">
                <h2 className="text-lg font-semibold">Transcription</h2>
                <div className="bg-muted p-3">
                  <Textarea
                    aria-label="Transcription"
                    readOnly
                    value={transcription ?? ""}
                    className="min-h-24 resize-y bg-background text-foreground dark:bg-background"
                  />
                </div>
                {transcription !== null && (
                  <p role="status" className="text-muted-foreground text-sm">
                    {transcription
                      ? "Transcription complete"
                      : "No speech detected"}
                  </p>
                )}
              </section>
            </div>
            <VoiceMetrics label="Speech to text metrics" metrics={sttMetrics} />
          </TabsContent>
          <TabsContent value="tts" className="space-y-6">
            <div className="space-y-4 bg-background p-4 sm:p-5">
              <h2 className="text-base font-semibold">
                Text to Speech Workload Configuration
              </h2>
              <section className="min-w-0 space-y-4 rounded-sm bg-muted p-3 sm:p-4">
                <div className="max-w-sm space-y-2">
                  <Label htmlFor="speech-voice">Voice</Label>
                  <select
                    id="speech-voice"
                    value={voice}
                    disabled={busy}
                    onChange={(event) =>
                      updateVoice(event.target.value as SpeechVoice)
                    }
                    className="border-input h-10 w-full rounded-md border bg-background px-3 text-sm"
                  >
                    {SPEECH_VOICES.map((voiceName) => (
                      <option key={voiceName} value={voiceName}>
                        {voiceName}
                      </option>
                    ))}
                  </select>
                </div>
                <Label htmlFor="voice-text" className="text-sm font-semibold">
                  Text input (English)
                </Label>
                <Textarea
                  id="voice-text"
                  maxLength={5000}
                  value={text}
                  disabled={busy}
                  onChange={(event) => updateText(event.target.value)}
                  className="min-h-32 resize-y bg-background text-foreground dark:bg-background"
                />
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div className="flex min-w-0 flex-wrap items-center gap-2">
                    <Label htmlFor="voice-sample" className="text-xs">
                      Sample text
                    </Label>
                    <select
                      id="voice-sample"
                      disabled={busy}
                      value={SAMPLE_TEXTS.includes(text) ? text : ""}
                      onChange={(event) => updateText(event.target.value)}
                      className="h-9 w-full max-w-80 min-w-0 rounded-sm border border-border bg-background px-2 text-xs sm:w-80"
                    >
                      <option value="" disabled>
                        Select a sample
                      </option>
                      {SAMPLE_TEXTS.map((sample) => (
                        <option key={sample} value={sample}>
                          {sample}
                        </option>
                      ))}
                    </select>
                  </div>
                  <p className="text-muted-foreground text-right text-xs">
                    {text.length} / 5000
                  </p>
                </div>
                <div className="flex justify-end">
                  <Button
                    disabled={!text.trim() || busy}
                    onClick={() => void run("tts")}
                  >
                    <Volume2 />
                    Generate speech
                  </Button>
                </div>
              </section>
              <section className="min-w-0 space-y-4">
                <h2 className="text-lg font-semibold">Generated audio</h2>
                {speechUrl ? (
                  <>
                    <VoiceAudio
                      src={speechUrl}
                      label="Generated speech"
                      title="Synthesized audio"
                    />
                    <a
                      href={speechUrl}
                      download="speech.wav"
                      className="text-primary inline-flex items-center gap-2 text-sm underline underline-offset-4"
                    >
                      <Download className="size-4" />
                      Download WAV
                    </a>
                  </>
                ) : (
                  <p className="text-muted-foreground text-sm">
                    No audio generated
                  </p>
                )}
              </section>
            </div>
            <VoiceMetrics label="Text to speech metrics" metrics={ttsMetrics} />
          </TabsContent>
          {busy && (
            <div
              role="status"
              className="mt-6 flex flex-wrap items-center gap-3 text-sm"
            >
              <LoaderCircle className="size-4 animate-spin" />
              {status === "recording"
                ? "Recording"
                : status === "starting"
                  ? "Waiting for microphone"
                  : status === "encoding"
                    ? "Preparing audio"
                    : status === "transcribing"
                      ? "Transcribing"
                      : "Generating speech"}
              <Button variant="ghost" size="sm" onClick={cancel}>
                <X />
                Cancel
              </Button>
            </div>
          )}
          {error && (
            <p
              role="alert"
              className="text-destructive mt-6 break-words text-sm"
            >
              {error}
            </p>
          )}
        </Tabs>
        <details
          className="mt-8 border-t pt-6"
          onToggle={(event) => setShowPlatformMetrics(event.currentTarget.open)}
        >
          <summary className="cursor-pointer text-lg font-semibold">
            Platform metrics (system-wide)
          </summary>
          {showPlatformMetrics && (
            <MetricsDashboard className="mt-4" showVideoMetrics={false} />
          )}
        </details>
      </div>
    </div>
  );
}
