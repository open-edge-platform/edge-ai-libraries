// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router";
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
import { useListAudioPipelinesVoicePipelinesGetQuery } from "@/api/api.generated";
import { BackButton } from "@/components/shared/BackButton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { MetricsDashboard } from "@/features/metrics/MetricsDashboard";
import { PipelineModelsRequiredDialog } from "@/features/models/PipelineModelsRequiredDialog";
import { useRequiredModelsStatus } from "@/features/models/useRequiredModelsStatus";
import { PipelineVariantSelect } from "@/features/pipelines/PipelineVariantSelect";
import { captureWav } from "./recording";
import {
  VoiceMetrics,
  type ConversionMetrics,
  type VoiceMetricsState,
} from "./VoiceMetrics";
import { VoiceAudio } from "./VoiceAudio";

const SAMPLE_TEXTS = [
  "Welcome to Intel Performance Studio.",
  "Your audio is ready for playback.",
  "Hello, how can I assist you today?",
];
const CUSTOM_SAMPLE_VALUE = "custom";
const MAX_SPEECH_TEXT_LENGTH = 200;

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

type AudioPipelineJob = {
  status: "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED";
  transcript: string | null;
  artifact_url: string | null;
  service_round_trip_ms: number | null;
  error: string | null;
};

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

function getMetricsState(
  metrics: ConversionMetrics | null,
  running: boolean,
  failed: boolean,
): VoiceMetricsState {
  if (running) return "running";
  if (failed) return "error";
  return metrics ? "success" : "idle";
}

export function VoiceConversion() {
  const { pipelineId = "speech-to-text", variantId = "cpu" } = useParams();
  const {
    data: pipelines = [],
    error: catalogError,
    isLoading,
  } = useListAudioPipelinesVoicePipelinesGetQuery();
  const selectedPipeline = pipelines.find(
    (pipeline) => pipeline.id === pipelineId,
  );
  const selectedVariant = selectedPipeline?.variants.find(
    (variant) => variant.id === variantId,
  );
  const requiredModels = selectedPipeline?.required_models ?? [];
  const {
    modelStatuses,
    isDialogOpen: modelStatusDialogOpen,
    setIsDialogOpen: setModelStatusDialogOpen,
    refresh: refreshRequiredModels,
  } = useRequiredModelsStatus(requiredModels, {
    skip: !selectedPipeline || !selectedVariant,
    errorMessage: "Failed to check models used in Audio pipeline",
  });
  const modelsReady =
    requiredModels.length > 0 &&
    requiredModels.every((model) =>
      modelStatuses.some(
        (status) =>
          status.model === model && status.installStatus === "installed",
      ),
    );
  const activeTab =
    selectedPipeline?.operation === "text_to_speech" ? "tts" : "stt";
  const [file, setFile] = useState<File | null>(null);
  const [language, setLanguage] = useState("en");
  const [text, setText] = useState("");
  const [voice, setVoice] = useState<SpeechVoice>("Ryan");
  const [transcription, setTranscription] = useState<string | null>(null);
  const [speech, setSpeech] = useState<Blob | null>(null);
  const [sttMetrics, setSttMetrics] = useState<ConversionMetrics | null>(null);
  const [ttsMetrics, setTtsMetrics] = useState<ConversionMetrics | null>(null);
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
  const initializedPipelines = useRef(new Set<string>());
  const fileInput = useRef<HTMLInputElement | null>(null);
  const stopRecording = useRef<(() => void) | null>(null);
  const inputUrl = useAudioUrl(file);
  const speechUrl = useAudioUrl(speech);
  const busy = status !== "idle";

  useEffect(() => () => operation.current?.abort(), []);

  useEffect(() => {
    if (
      !selectedPipeline ||
      initializedPipelines.current.has(selectedPipeline.id)
    )
      return;
    initializedPipelines.current.add(selectedPipeline.id);
    const defaults = selectedPipeline.defaults;
    if (selectedPipeline.operation === "speech_to_text") {
      setLanguage(defaults.language ?? "en");
    } else {
      setText(defaults.text ?? "");
      setVoice((defaults.voice as SpeechVoice | null) ?? "Ryan");
    }
  }, [selectedPipeline]);

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

  async function waitForJob(
    jobId: string,
    controller: AbortController,
  ): Promise<AudioPipelineJob> {
    while (true) {
      const response = await fetch(`${API_BASE_URL}/voice/jobs/${jobId}`, {
        cache: "no-store",
        signal: controller.signal,
      });
      await checkResponse(response);
      const job = (await response.json()) as AudioPipelineJob;
      if (job.status === "COMPLETED") return job;
      if (job.status === "FAILED")
        throw new Error(job.error ?? "Audio pipeline execution failed.");
      await new Promise<void>((resolve, reject) => {
        const timeout = window.setTimeout(resolve, 500);
        controller.signal.addEventListener(
          "abort",
          () => {
            window.clearTimeout(timeout);
            reject(controller.signal.reason);
          },
          { once: true },
        );
      });
    }
  }

  async function runManagedPipeline(
    controller: AbortController,
    startedAt: number,
    ttsRequest?: { input: string; voice: SpeechVoice },
  ) {
    if (!selectedPipeline || !selectedVariant)
      throw new Error("Audio pipeline variant not found.");
    const response = await fetch(
      `${API_BASE_URL}/voice/pipelines/${selectedPipeline.id}/variants/${selectedVariant.id}/runs`,
      {
        method: "POST",
        headers: ttsRequest
          ? { "Content-Type": "application/json" }
          : undefined,
        body: ttsRequest ? JSON.stringify(ttsRequest) : undefined,
        cache: "no-store",
        signal: controller.signal,
      },
    );
    await checkResponse(response);
    const start: unknown = await response.json();
    if (
      !start ||
      typeof start !== "object" ||
      !("job_id" in start) ||
      typeof start.job_id !== "string"
    )
      throw new Error("The service returned an invalid Audio job.");
    const job = await waitForJob(start.job_id, controller);
    const metrics = {
      requestMs: performance.now() - startedAt,
      serviceMs: job.service_round_trip_ms,
    };
    if (selectedPipeline.operation === "speech_to_text") {
      setTranscription(job.transcript ?? "");
      setSttMetrics(metrics);
      return;
    }
    if (!job.artifact_url)
      throw new Error("The Audio job did not produce an artifact.");
    const artifact = await fetch(job.artifact_url, {
      cache: "no-store",
      signal: controller.signal,
    });
    await checkResponse(artifact);
    setSpeech(await artifact.blob());
    setTtsMetrics(metrics);
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
      1_210_000,
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
      } else if (
        kind === "stt" &&
        !file &&
        selectedPipeline?.operation === "speech_to_text" &&
        language === (selectedPipeline.defaults.language ?? "en")
      ) {
        await runManagedPipeline(controller, performance.now());
      } else if (kind === "stt" && file) {
        const data = new FormData();
        data.append("file", file);
        data.append("language", language);
        data.append("device", selectedVariant?.device ?? "CPU");
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
      } else if (
        kind === "tts" &&
        selectedPipeline?.operation === "text_to_speech"
      ) {
        await runManagedPipeline(controller, performance.now(), {
          input: text.trim(),
          voice,
        });
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

  if (isLoading)
    return (
      <p className="p-6 text-sm text-muted-foreground">
        Loading Audio pipeline...
      </p>
    );
  if (catalogError)
    return (
      <p role="alert" className="p-6 text-sm text-destructive">
        {catalogError}
      </p>
    );
  if (!selectedPipeline || !selectedVariant)
    return (
      <p role="alert" className="p-6 text-sm text-destructive">
        Audio pipeline not found.
      </p>
    );

  return (
    <div className="min-h-full w-full min-w-0 bg-muted text-foreground [color-scheme:light] dark:[color-scheme:dark]">
      <header className="flex h-[3.75rem] shrink-0 items-center gap-2 border-b transition-[width,height] ease-linear">
        <div className="flex flex-wrap items-center gap-2 px-2">
          <BackButton to="/pipelines" aria-label="Back" />
          <h1 className="font-medium">
            {activeTab === "stt"
              ? "Automatic Speech Recognition"
              : "Text to Speech"}
          </h1>
          <PipelineVariantSelect
            pipelineId={selectedPipeline.id}
            currentVariant={selectedVariant.id}
            variants={selectedPipeline.variants}
            routeBase={`/pipelines/audio/${selectedPipeline.id}`}
            disabled={busy}
          />
        </div>
      </header>
      <div className="mx-auto w-full max-w-[1600px] px-4 py-4 sm:px-8">
        <>
          {activeTab === "stt" && (
            <div className="grid min-w-0 gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(32rem,40rem)] xl:items-start">
              <div className="min-w-0 space-y-4 bg-background p-4 sm:p-5">
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
                        Audio file
                      </Label>
                      <Button
                        variant="outline"
                        disabled={busy}
                        onClick={() => fileInput.current?.click()}
                        className="h-28 w-full flex-col gap-2 whitespace-normal border-border bg-background"
                      >
                        <Upload className="size-6 text-brand-accent" />
                        <span>Upload audio</span>
                        <span className="text-xs leading-4 font-normal text-muted-foreground">
                          <span className="block">Maximum size: 200 MiB</span>
                          <span className="block">
                            Formats: WAV, MP3, M4A, MP4, MKV, MOV, AVI
                          </span>
                        </span>
                      </Button>
                      <Input
                        ref={fileInput}
                        id="voice-file"
                        type="file"
                        className="sr-only"
                        tabIndex={-1}
                        disabled={busy}
                        onChange={(event) => {
                          const selected = event.target.files?.[0];
                          setError(null);
                          setTranscription(null);
                          setSttMetrics(null);
                          setFile(null);
                          if (!selected) return;
                          setFile(selected);
                        }}
                      />
                    </div>
                  </div>
                  <div className="max-w-md">
                    <div className="space-y-2 bg-muted p-3">
                      <Label htmlFor="voice-language">
                        Recognition language
                      </Label>
                      <Select
                        value={language}
                        disabled={busy}
                        onValueChange={(value) => {
                          setLanguage(value);
                          setTranscription(null);
                          setSttMetrics(null);
                        }}
                      >
                        <SelectTrigger
                          id="voice-language"
                          className="h-10 w-full bg-background"
                        >
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="en">English</SelectItem>
                          <SelectItem value="pl">Polish</SelectItem>
                          <SelectItem value="de">German</SelectItem>
                          <SelectItem value="fr">French</SelectItem>
                          <SelectItem value="es">Spanish</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  {file && (
                    <p className="text-muted-foreground break-all text-sm">
                      Selected file: {file.name}
                    </p>
                  )}
                  {!file && selectedPipeline.defaults.audio && (
                    <p className="text-muted-foreground break-all text-sm">
                      Managed recording: {selectedPipeline.defaults.audio}
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
                      disabled={
                        !modelsReady ||
                        busy ||
                        (!file &&
                          language !==
                            (selectedPipeline.defaults.language ?? "en"))
                      }
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
                      className="min-h-24 resize-y bg-background text-foreground"
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
              <aside
                aria-label="Performance and platform metrics"
                className="min-w-0 space-y-4"
              >
                <VoiceMetrics
                  label="Speech to text metrics"
                  metrics={sttMetrics}
                  state={getMetricsState(
                    sttMetrics,
                    activeTab === "stt" && busy,
                    activeTab === "stt" && error !== null,
                  )}
                />
                <MetricsDashboard showVideoMetrics={false} />
              </aside>
            </div>
          )}
          {activeTab === "tts" && (
            <div className="grid min-w-0 gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(32rem,40rem)] xl:items-start">
              <div className="min-w-0 space-y-4 bg-background p-4 sm:p-5">
                <h2 className="text-base font-semibold">
                  Text to Speech Workload Configuration
                </h2>
                <section className="min-w-0 space-y-4 rounded-sm bg-muted p-3 sm:p-4">
                  <div className="grid max-w-4xl gap-4 md:grid-cols-2">
                    <div className="space-y-2">
                      <Label htmlFor="speech-voice">Voice</Label>
                      <Select
                        value={voice}
                        disabled={busy}
                        onValueChange={(value) =>
                          updateVoice(value as SpeechVoice)
                        }
                      >
                        <SelectTrigger
                          id="speech-voice"
                          className="h-10 w-full bg-background"
                        >
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {SPEECH_VOICES.map((voiceName) => (
                            <SelectItem key={voiceName} value={voiceName}>
                              {voiceName}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  <Label htmlFor="voice-text" className="text-sm font-semibold">
                    Text input (English)
                  </Label>
                  <Textarea
                    id="voice-text"
                    maxLength={MAX_SPEECH_TEXT_LENGTH}
                    value={text}
                    disabled={busy}
                    onChange={(event) => updateText(event.target.value)}
                    className="min-h-32 resize-y bg-background text-foreground"
                  />
                  <div className="flex flex-wrap items-center justify-between gap-4">
                    <div className="flex min-w-0 flex-wrap items-center gap-2">
                      <Label htmlFor="voice-sample" className="text-xs">
                        Sample text
                      </Label>
                      <Select
                        disabled={busy}
                        value={
                          SAMPLE_TEXTS.includes(text)
                            ? text
                            : CUSTOM_SAMPLE_VALUE
                        }
                        onValueChange={updateText}
                      >
                        <SelectTrigger
                          id="voice-sample"
                          className="h-9 w-full max-w-80 min-w-0 bg-background text-xs sm:w-80"
                        >
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value={CUSTOM_SAMPLE_VALUE} disabled>
                            Select a sample
                          </SelectItem>
                          {SAMPLE_TEXTS.map((sample) => (
                            <SelectItem key={sample} value={sample}>
                              {sample}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <p className="text-muted-foreground text-right text-xs">
                      {text.length} / {MAX_SPEECH_TEXT_LENGTH}
                    </p>
                  </div>
                  <div className="flex justify-end">
                    <Button
                      disabled={!modelsReady || !text.trim() || busy}
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
              <aside
                aria-label="Performance and platform metrics"
                className="min-w-0 space-y-4"
              >
                <VoiceMetrics
                  label="Text to speech metrics"
                  metrics={ttsMetrics}
                  state={getMetricsState(
                    ttsMetrics,
                    activeTab === "tts" && busy,
                    activeTab === "tts" && error !== null,
                  )}
                />
                <MetricsDashboard showVideoMetrics={false} />
              </aside>
            </div>
          )}
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
        </>
      </div>
      <PipelineModelsRequiredDialog
        open={modelStatusDialogOpen}
        onOpenChange={setModelStatusDialogOpen}
        models={modelStatuses}
        onModelsChanged={refreshRequiredModels}
      />
    </div>
  );
}
