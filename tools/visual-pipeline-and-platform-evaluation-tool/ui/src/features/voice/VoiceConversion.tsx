// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useRef, useState } from "react";
import {
  Download,
  FileAudio,
  LoaderCircle,
  Mic,
  Square,
  Volume2,
  X,
} from "lucide-react";
import { API_BASE_URL } from "@/api/apiSlice";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CONTENT_CONTAINER_CLASS } from "@/lib/utils";
import { captureWav } from "./recording";

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
  const [file, setFile] = useState<File | null>(null);
  const [language, setLanguage] = useState("en");
  const [text, setText] = useState("");
  const [transcription, setTranscription] = useState<string | null>(null);
  const [speech, setSpeech] = useState<Blob | null>(null);
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

  async function run(kind: "record" | "stt" | "tts") {
    const controller = new AbortController();
    operation.current = controller;
    setError(null);
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
        setTranscription(null);
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
        setTranscription(result.text);
      } else if (kind === "tts") {
        setSpeech(null);
        const response = await fetch(`${API_BASE_URL}/voice/speech`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ input: text.trim() }),
          signal: controller.signal,
          cache: "no-store",
        });
        await checkResponse(response);
        const result = await response.blob();
        controller.signal.throwIfAborted();
        setSpeech(result);
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
    <div className={CONTENT_CONTAINER_CLASS}>
      <h1 className="mb-6 text-3xl font-bold">Voice conversion</h1>
      <Tabs
        defaultValue="stt"
        onValueChange={() => {
          cancel();
          setError(null);
        }}
      >
        <TabsList className="mb-6 grid h-auto w-full max-w-lg grid-cols-2">
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
          <div className="grid min-w-0 gap-8 lg:grid-cols-2">
            <section className="min-w-0 space-y-4">
              <h2 className="text-lg font-semibold">Audio input</h2>
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => void run("record")} disabled={busy}>
                  <Mic />
                  Record
                </Button>
                {status === "recording" && (
                  <Button
                    variant="outline"
                    onClick={() => {
                      stopRecording.current?.();
                      setStatus("encoding");
                    }}
                  >
                    <Square />
                    Stop recording
                  </Button>
                )}
              </div>
              <div className="space-y-2">
                <Label htmlFor="voice-file">WAV file</Label>
                <Input
                  id="voice-file"
                  type="file"
                  accept=".wav,audio/wav"
                  disabled={busy}
                  onChange={(event) => {
                    const selected = event.target.files?.[0];
                    setError(null);
                    setTranscription(null);
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
              <div className="space-y-2">
                <Label htmlFor="voice-language">Recognition language</Label>
                <select
                  id="voice-language"
                  value={language}
                  disabled={busy}
                  onChange={(event) => setLanguage(event.target.value)}
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
                  {file.name}
                </p>
              )}
              {inputUrl && (
                <audio
                  key={inputUrl}
                  aria-label="Input recording"
                  src={inputUrl}
                  controls
                  className="w-full min-w-0"
                />
              )}
              <Button disabled={!file || busy} onClick={() => void run("stt")}>
                <FileAudio />
                Transcribe
              </Button>
            </section>
            <section className="min-w-0 space-y-4">
              <h2 className="text-lg font-semibold">Transcription</h2>
              <Textarea
                aria-label="Transcription"
                readOnly
                value={transcription ?? ""}
                className="min-h-48 resize-y"
              />
              {transcription !== null && (
                <p role="status" className="text-muted-foreground text-sm">
                  {transcription
                    ? "Transcription complete"
                    : "No speech detected"}
                </p>
              )}
            </section>
          </div>
        </TabsContent>
        <TabsContent value="tts" className="space-y-6">
          <div className="grid min-w-0 gap-8 lg:grid-cols-2">
            <section className="min-w-0 space-y-4">
              <Label htmlFor="voice-text" className="text-lg font-semibold">
                Text input (English)
              </Label>
              <Textarea
                id="voice-text"
                maxLength={5000}
                value={text}
                disabled={busy}
                onChange={(event) => setText(event.target.value)}
                className="min-h-48 resize-y"
              />
              <p className="text-muted-foreground text-right text-sm">
                {text.length} / 5000
              </p>
              <Button
                disabled={!text.trim() || busy}
                onClick={() => void run("tts")}
              >
                <Volume2 />
                Generate speech
              </Button>
            </section>
            <section className="min-w-0 space-y-4">
              <h2 className="text-lg font-semibold">Generated audio</h2>
              {speechUrl ? (
                <>
                  <audio
                    key={speechUrl}
                    aria-label="Generated speech"
                    src={speechUrl}
                    controls
                    className="w-full min-w-0"
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
          <p role="alert" className="text-destructive mt-6 break-words text-sm">
            {error}
          </p>
        )}
      </Tabs>
    </div>
  );
}
