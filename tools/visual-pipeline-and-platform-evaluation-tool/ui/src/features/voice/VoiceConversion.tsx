// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
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
import {
  type AudioJobStatus,
  useListAudioPipelinesVoicePipelinesGetQuery,
  useListAudioRecordingsVoiceRecordingsGetQuery,
  useStopAudioJobMutation,
} from "@/api/api.generated";
import { BackButton } from "@/components/shared/BackButton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { MetricsDashboard } from "@/features/metrics/MetricsDashboard";
import { PipelineModelsRequiredDialog } from "@/features/models/PipelineModelsRequiredDialog";
import { useRequiredModelsStatus } from "@/features/models/useRequiredModelsStatus";
import { PipelineVariantSelect } from "@/features/pipelines/PipelineVariantSelect";
import { getErrorMessage, handleApiError } from "@/lib/apiUtils";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";
import { captureWav } from "./recording";
import { VoiceMetrics, type ConversionMetrics } from "./VoiceMetrics";
import { VoiceAudio } from "./VoiceAudio";

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

type InputSource = "record" | "upload" | "predefined";

type ManagedAudioRunBody =
  | FormData
  | { input: string; voice: SpeechVoice }
  | { recording: string; language: string };

function formatDuration(seconds: number): string {
  const rounded = Math.round(seconds);
  return `${Math.floor(rounded / 60)}:${(rounded % 60).toString().padStart(2, "0")}`;
}

class AudioPipelineCancelledError extends Error {}

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

function RequiresModels({
  missingModels,
  children,
}: {
  missingModels: string[];
  children: ReactNode;
}) {
  if (missingModels.length === 0) return children;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex">{children}</span>
      </TooltipTrigger>
      <TooltipContent side="bottom" className="max-w-80">
        <p>Install all required models first.</p>
        <p className="mt-1 text-xs text-muted-foreground break-words">
          Missing: {missingModels.join(", ")}
        </p>
      </TooltipContent>
    </Tooltip>
  );
}

const RUN_BUTTON_WIDTH = "w-44";

function StopButton({
  stopping,
  onStop,
}: {
  stopping: boolean;
  onStop: () => void;
}) {
  return (
    <Button
      variant="destructive"
      className={RUN_BUTTON_WIDTH}
      disabled={stopping}
      onClick={onStop}
    >
      {stopping ? <LoaderCircle className="animate-spin" /> : <Square />}
      Stop
    </Button>
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
    missingModels,
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
  const [inputSource, setInputSource] = useState<InputSource>("predefined");
  const [recordedFile, setRecordedFile] = useState<File | null>(null);
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [selectedRecording, setSelectedRecording] = useState<string | null>(
    null,
  );
  const file =
    inputSource === "record"
      ? recordedFile
      : inputSource === "upload"
        ? uploadedFile
        : null;
  const {
    data: recordingCatalog,
    isError: recordingsFailed,
    isLoading: recordingsLoading,
  } = useListAudioRecordingsVoiceRecordingsGetQuery(undefined, {
    skip: activeTab !== "stt",
  });
  const recordings = useMemo(() => recordingCatalog ?? [], [recordingCatalog]);
  const predefinedRecording = recordings.find(
    (item) => item.filename === selectedRecording,
  );
  const [language, setLanguage] = useState("en");
  const [text, setText] = useState("");
  const [voice, setVoice] = useState<SpeechVoice>("Ryan");
  const [transcription, setTranscription] = useState<string | null>(null);
  const [speech, setSpeech] = useState<Blob | null>(null);
  const [sttMetrics, setSttMetrics] = useState<ConversionMetrics | null>(null);
  const [ttsMetrics, setTtsMetrics] = useState<ConversionMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [recordError, setRecordError] = useState<string | null>(null);
  const [stopping, setStopping] = useState(false);
  const [stopAudioJob] = useStopAudioJobMutation();
  const [status, setStatus] = useState<
    | "idle"
    | "starting"
    | "recording"
    | "encoding"
    | "transcribing"
    | "synthesizing"
  >("idle");
  const operation = useRef<AbortController | null>(null);
  const activeJobId = useRef<string | null>(null);
  const initializedPipelines = useRef(new Set<string>());
  const fileInput = useRef<HTMLInputElement | null>(null);
  const stopRecording = useRef<(() => void) | null>(null);
  const inputUrl = useAudioUrl(file);
  const previewUrl =
    inputSource === "predefined" ? predefinedRecording?.audio_url : inputUrl;
  const hasInput =
    inputSource === "predefined" ? predefinedRecording !== undefined : !!file;
  const speechUrl = useAudioUrl(speech);
  const busy = status !== "idle";

  useEffect(
    () => () => {
      const controller = operation.current;
      operation.current = null;
      activeJobId.current = null;
      controller?.abort();
    },
    [],
  );

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

  useEffect(() => {
    if (selectedRecording !== null || recordings.length === 0) return;
    const preferred = selectedPipeline?.defaults.audio;
    setSelectedRecording(
      recordings.find((item) => item.filename === preferred)?.filename ??
        recordings[0].filename,
    );
  }, [recordings, selectedRecording, selectedPipeline]);

  function selectInputSource(source: InputSource) {
    setInputSource(source);
    setTranscription(null);
    setSttMetrics(null);
    setError(null);
  }

  function cancel() {
    operation.current?.abort();
    operation.current = null;
    activeJobId.current = null;
    stopRecording.current = null;
    setStatus("idle");
  }

  async function stop() {
    const jobId = activeJobId.current;
    if (jobId === null) {
      cancel();
      return;
    }
    setStopping(true);
    try {
      await stopAudioJob({ jobId }).unwrap();
    } catch (failure) {
      setStopping(false);
      handleApiError(failure, "Failed to stop Audio pipeline run");
    }
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
  ): Promise<AudioJobStatus> {
    while (true) {
      const response = await fetch(
        `${API_BASE_URL}/jobs/audio/${jobId}/status`,
        {
          cache: "no-store",
          signal: controller.signal,
        },
      );
      await checkResponse(response);
      const job = (await response.json()) as AudioJobStatus;
      if (job.state === "COMPLETED") return job;
      if (job.state === "FAILED")
        throw new Error(job.error ?? "Audio pipeline execution failed.");
      if (job.state === "CANCELLED")
        throw new AudioPipelineCancelledError(
          job.error ?? "Audio pipeline execution was cancelled.",
        );
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
    requestBody: ManagedAudioRunBody,
  ) {
    if (!selectedPipeline || !selectedVariant)
      throw new Error("Audio pipeline variant not found.");
    const multipart = requestBody instanceof FormData;
    const response = await fetch(
      `${API_BASE_URL}/voice/pipelines/${selectedPipeline.id}/variants/${selectedVariant.id}/runs`,
      {
        method: "POST",
        headers: multipart ? undefined : { "Content-Type": "application/json" },
        body: multipart ? requestBody : JSON.stringify(requestBody),
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
    controller.signal.throwIfAborted();
    if (operation.current !== controller) return;
    activeJobId.current = start.job_id;
    toast.success("Audio pipeline run started", {
      description: new Date().toISOString(),
    });
    const job = await waitForJob(start.job_id, controller);
    controller.signal.throwIfAborted();
    if (operation.current !== controller) return;
    const metrics = {
      requestMs: performance.now() - startedAt,
      serviceMs: job.service_round_trip_ms ?? null,
    };
    if (selectedPipeline.operation === "speech_to_text") {
      setTranscription(job.transcript ?? "");
      setSttMetrics(metrics);
    } else {
      if (!job.artifact_url)
        throw new Error("The Audio job did not produce an artifact.");
      const artifact = await fetch(job.artifact_url, {
        cache: "no-store",
        signal: controller.signal,
      });
      await checkResponse(artifact);
      const content = await artifact.blob();
      controller.signal.throwIfAborted();
      if (operation.current !== controller) return;
      setSpeech(content);
      setTtsMetrics(metrics);
    }
    toast.success("Audio pipeline run completed", {
      description: new Date().toISOString(),
    });
  }

  async function run(kind: "record" | "stt" | "tts") {
    operation.current?.abort();
    activeJobId.current = null;
    const controller = new AbortController();
    operation.current = controller;
    setError(null);
    setRecordError(null);
    setStopping(false);
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
        setRecordedFile(recording);
        setInputSource("record");
        setTranscription(null);
      } else if (
        kind === "stt" &&
        selectedPipeline?.operation === "speech_to_text"
      ) {
        if (inputSource === "predefined") {
          if (!predefinedRecording)
            throw new Error("Select a predefined recording.");
          await runManagedPipeline(controller, performance.now(), {
            recording: predefinedRecording.filename,
            language,
          });
        } else {
          if (!file) throw new Error("Record or upload audio first.");
          const requestBody = new FormData();
          requestBody.append("file", file);
          requestBody.append("language", language);
          await runManagedPipeline(controller, performance.now(), requestBody);
        }
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
        const message =
          failure instanceof Error ? failure.message : "Conversion failed.";
        if (failure instanceof AudioPipelineCancelledError) {
          toast.info("Audio pipeline run cancelled", {
            description: new Date().toISOString(),
          });
        } else if (kind === "record") {
          setRecordError(message);
        } else {
          setError(message);
          toast.error("Audio pipeline run failed", { description: message });
        }
      }
    } finally {
      window.clearTimeout(timer);
      if (operation.current === controller) {
        operation.current = null;
        activeJobId.current = null;
        stopRecording.current = null;
        setStatus("idle");
        setStopping(false);
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
        {getErrorMessage(catalogError)}
      </p>
    );
  if (!selectedPipeline || !selectedVariant)
    return (
      <p role="alert" className="p-6 text-sm text-destructive">
        Audio pipeline not found.
      </p>
    );

  return (
    <div className="min-h-full w-full min-w-0 self-start bg-muted text-foreground [color-scheme:light] dark:[color-scheme:dark]">
      <header className="flex h-[3.75rem] shrink-0 items-center gap-2 border-b transition-[width,height] ease-linear">
        <div className="flex flex-wrap items-center gap-2 px-2">
          <BackButton to="/pipelines?tab=audio" aria-label="Back" />
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
            <div className="grid min-w-0 gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(32rem,40rem)]">
              <div className="min-w-0 space-y-4 bg-background p-4 sm:p-5">
                <h2 className="text-base font-semibold">
                  Workload Configuration
                </h2>
                <section className="min-w-0 space-y-4">
                  <h3 className="text-base font-semibold">1. Select input</h3>
                  <RadioGroup
                    aria-label="Input source"
                    value={inputSource}
                    disabled={busy}
                    onValueChange={(value) =>
                      selectInputSource(value as InputSource)
                    }
                    className="grid min-w-0 grid-cols-1 gap-3"
                  >
                    <div
                      className={cn(
                        "min-w-0 space-y-3 border bg-muted p-3",
                        inputSource === "predefined"
                          ? "border-brand-accent"
                          : "border-transparent",
                      )}
                    >
                      <div className="flex items-center gap-2">
                        <RadioGroupItem
                          value="predefined"
                          id="voice-source-predefined"
                        />
                        <Label htmlFor="voice-source-predefined">
                          Available audio samples
                        </Label>
                      </div>
                      {recordingsLoading ? (
                        <p className="text-muted-foreground text-sm">
                          Loading recordings...
                        </p>
                      ) : recordingsFailed ? (
                        <p role="alert" className="text-destructive text-sm">
                          Unable to load predefined recordings.
                        </p>
                      ) : recordings.length === 0 ? (
                        <p className="text-muted-foreground text-sm">
                          No predefined recordings available.
                        </p>
                      ) : (
                        <Select
                          value={selectedRecording ?? undefined}
                          disabled={busy}
                          onValueChange={(value) => {
                            setSelectedRecording(value);
                            selectInputSource("predefined");
                          }}
                        >
                          <SelectTrigger
                            aria-label="Predefined recording"
                            className="h-10 w-full bg-background"
                          >
                            <SelectValue placeholder="Select a recording" />
                          </SelectTrigger>
                          <SelectContent>
                            {recordings.map((item) => (
                              <SelectItem
                                key={item.filename}
                                value={item.filename}
                              >
                                {`${item.filename} (${formatDuration(item.duration_seconds)})`}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      )}
                    </div>
                    <div
                      className={cn(
                        "min-w-0 space-y-3 border bg-muted p-3",
                        inputSource === "upload"
                          ? "border-brand-accent"
                          : "border-transparent",
                      )}
                    >
                      <div className="flex items-center gap-2">
                        <RadioGroupItem
                          value="upload"
                          id="voice-source-upload"
                        />
                        <Label htmlFor="voice-source-upload">Upload</Label>
                      </div>
                      <Button
                        variant="outline"
                        disabled={busy}
                        onClick={() => fileInput.current?.click()}
                        className="h-auto min-h-20 w-full flex-col gap-1 whitespace-normal border-border bg-background py-3"
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
                        aria-label="Audio file"
                        type="file"
                        className="sr-only w-px"
                        tabIndex={-1}
                        disabled={busy}
                        onChange={(event) => {
                          const selected = event.target.files?.[0];
                          setError(null);
                          setTranscription(null);
                          setSttMetrics(null);
                          setUploadedFile(selected ?? null);
                          if (selected) setInputSource("upload");
                        }}
                      />
                    </div>
                    <div
                      className={cn(
                        "min-w-0 space-y-3 border bg-muted p-3",
                        inputSource === "record"
                          ? "border-brand-accent"
                          : "border-transparent",
                      )}
                    >
                      <div className="flex items-center gap-2">
                        <RadioGroupItem
                          value="record"
                          id="voice-source-record"
                        />
                        <Label htmlFor="voice-source-record">Microphone</Label>
                      </div>
                      <Button
                        variant="outline"
                        className="h-20 w-full flex-col gap-1 whitespace-normal border-border bg-background"
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
                            : status === "starting"
                              ? "Waiting for microphone..."
                              : "Record from microphone"}
                        </span>
                        <span className="text-xs font-normal text-muted-foreground">
                          Up to 60 seconds
                        </span>
                      </Button>
                      {recordError && (
                        <p
                          role="alert"
                          className="text-destructive break-words text-sm"
                        >
                          {recordError}
                        </p>
                      )}
                    </div>
                  </RadioGroup>
                </section>
                <section className="min-w-0 space-y-4">
                  <h3 className="text-base font-semibold">
                    2. Verify audio (optional)
                  </h3>
                  {previewUrl ? (
                    <VoiceAudio
                      src={previewUrl}
                      label="Input recording"
                      title="Selected audio"
                      showHeader={false}
                    />
                  ) : (
                    <p className="text-muted-foreground border border-dashed border-border p-3 text-sm">
                      No audio selected.
                    </p>
                  )}
                  {inputSource !== "predefined" && file && (
                    <p className="text-muted-foreground break-all text-sm">
                      Selected file: {file.name}
                    </p>
                  )}
                </section>
                <section className="min-w-0 space-y-2">
                  <h3 className="text-base font-semibold">
                    3. Select language
                  </h3>
                  <div className="min-w-0 bg-muted p-3">
                    <Label htmlFor="voice-language" className="sr-only">
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
                        className="h-10 w-full bg-background md:max-w-xs"
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
                </section>
                <section className="flex min-w-0 justify-end">
                  <RequiresModels
                    missingModels={missingModels.map((item) => item.model)}
                  >
                    {status === "transcribing" ? (
                      <StopButton
                        stopping={stopping}
                        onStop={() => void stop()}
                      />
                    ) : (
                      <Button
                        className={RUN_BUTTON_WIDTH}
                        disabled={!modelsReady || busy || !hasInput}
                        onClick={() => void run("stt")}
                      >
                        <FileAudio />
                        Transcribe
                      </Button>
                    )}
                  </RequiresModels>
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
                />
                <MetricsDashboard showVideoMetrics={false} />
              </aside>
            </div>
          )}
          {activeTab === "tts" && (
            <div className="grid min-w-0 gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(32rem,40rem)]">
              <div className="min-w-0 space-y-4 bg-background p-4 sm:p-5">
                <h2 className="text-base font-semibold">
                  Workload Configuration
                </h2>
                <section className="grid min-w-0 gap-4 bg-muted p-3 sm:p-4">
                  <div className="min-w-0 space-y-2">
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
                  <div className="min-w-0 space-y-2">
                    <Label
                      htmlFor="voice-text"
                      className="text-sm font-semibold"
                    >
                      Text input
                    </Label>
                    <Textarea
                      id="voice-text"
                      maxLength={MAX_SPEECH_TEXT_LENGTH}
                      value={text}
                      disabled={busy}
                      onChange={(event) => updateText(event.target.value)}
                      className="min-h-32 resize-y bg-background text-foreground"
                    />
                    <p className="text-muted-foreground text-right text-xs">
                      {text.length} / {MAX_SPEECH_TEXT_LENGTH}
                    </p>
                  </div>
                  <div className="flex justify-end">
                    <RequiresModels
                      missingModels={missingModels.map((item) => item.model)}
                    >
                      {status === "synthesizing" ? (
                        <StopButton
                          stopping={stopping}
                          onStop={() => void stop()}
                        />
                      ) : (
                        <Button
                          className={RUN_BUTTON_WIDTH}
                          disabled={!modelsReady || !text.trim() || busy}
                          onClick={() => void run("tts")}
                        >
                          <Volume2 />
                          Generate speech
                        </Button>
                      )}
                    </RequiresModels>
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
              {(status === "starting" ||
                status === "recording" ||
                status === "encoding") && (
                <Button variant="ghost" size="sm" onClick={cancel}>
                  <X />
                  Cancel
                </Button>
              )}
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
