// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import {
  expect,
  test,
  type Locator,
  type Page,
  type Request,
} from "@playwright/test";
import { Buffer } from "node:buffer";
import process from "node:process";

const DEFAULT_TTS_TEXT =
  "Welcome to Intel Performance Studio. This audio pipeline demonstrates clear text-to-speech synthesis, measures service latency, and produces a WAV file ready for playback on supported edge hardware.";

const AUDIO_PIPELINES = [
  {
    id: "speech-to-text",
    name: "Speech to Text",
    description: "Transcribe the managed default recording.",
    type: "audio",
    operation: "speech_to_text",
    tags: ["Audio", "Speech Recognition"],
    thumbnail:
      "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADElEQVR42mNk+M/wHwAF/gL+X1Y4WQAAAABJRU5ErkJggg==",
    required_models: ["Whisper Base"],
    variants: [
      { id: "cpu", name: "CPU", device: "CPU" },
      { id: "gpu", name: "GPU", device: "GPU" },
      { id: "npu", name: "NPU", device: "NPU" },
    ],
    defaults: {
      audio: "sample_male.wav",
      language: "en",
      text: null,
      voice: null,
    },
  },
  {
    id: "text-to-speech",
    name: "Text to Speech",
    description: "Generate WAV audio from the default text.",
    type: "audio",
    operation: "text_to_speech",
    tags: ["Audio", "Speech Synthesis"],
    thumbnail:
      "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADElEQVR42mNk+M/wHwAF/gL+X1Y4WQAAAABJRU5ErkJggg==",
    required_models: ["SpeechT5"],
    variants: [
      { id: "cpu", name: "CPU", device: "CPU" },
      { id: "gpu", name: "GPU", device: "GPU" },
    ],
    defaults: {
      audio: null,
      language: null,
      text: DEFAULT_TTS_TEXT,
      voice: "Ryan",
    },
  },
];
const AUDIO_MODELS = [
  {
    name: "voice-whisper-base",
    display_name: "Whisper Base",
    description: "Speech recognition model",
    category: "automatic_speech_recognition",
    source: "huggingface",
    install_status: "installed",
    variants: [],
  },
  {
    name: "voice-speecht5",
    display_name: "SpeechT5",
    description: "Speech synthesis model",
    category: "text_to_speech",
    source: "huggingface",
    install_status: "installed",
    variants: [],
  },
];

const AUDIO_RECORDINGS = [
  {
    filename: "sample_male.wav",
    duration_seconds: 33,
    audio_url: "/api/v1/voice/recordings/sample_male.wav/audio",
  },
  {
    filename: "sample_female.wav",
    duration_seconds: 15,
    audio_url: "/api/v1/voice/recordings/sample_female.wav/audio",
  },
];
let recordingListRequests: string[] = [];
let recordingAudioRequests: string[] = [];

const VISION_PIPELINES = [
  "People Detection",
  "Smart Parking",
  "Defect Detection",
].map((name, index) => ({
  id: `vision-${index + 1}`,
  name,
  description: `${name} pipeline`,
  source: "PREDEFINED",
  type: "vision",
  tags: ["Vision"],
  variants: [
    {
      id: "default",
      name: "Default",
      read_only: true,
      pipeline_graph: { nodes: [], edges: [] },
      pipeline_graph_simple: { nodes: [], edges: [] },
      created_at: "2026-10-09T10:00:00Z",
      modified_at: "2026-10-09T10:00:00Z",
    },
  ],
  thumbnail:
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADElEQVR42mNk+M/wHwAF/gL+X1Y4WQAAAABJRU5ErkJggg==",
  created_at: "2026-10-09T10:00:00Z",
  modified_at: `2026-10-09T10:00:0${index}Z`,
}));

function wav(volume = 1): Buffer {
  const content = Buffer.alloc(32044);
  content.write("RIFF", 0);
  content.writeUInt32LE(content.length - 8, 4);
  content.write("WAVEfmt ", 8);
  content.writeUInt32LE(16, 16);
  content.writeUInt16LE(1, 20);
  content.writeUInt16LE(1, 22);
  content.writeUInt32LE(16000, 24);
  content.writeUInt32LE(32000, 28);
  content.writeUInt16LE(2, 32);
  content.writeUInt16LE(16, 34);
  content.write("data", 36);
  content.writeUInt32LE(32000, 40);
  for (let frame = 0; frame < 16000; frame++) {
    const envelope = 0.1 + 0.6 * Math.abs(Math.sin(frame / 900));
    content.writeInt16LE(
      Math.round(20000 * volume * envelope * Math.sin(frame * 0.15)),
      44 + frame * 2,
    );
  }
  return content;
}

async function chooseOption(page: Page, label: string, option: string) {
  await page.getByRole("combobox", { name: label }).click();
  await page.getByRole("option", { name: option, exact: true }).click();
}

async function expectMetricsEmpty(metrics: Locator) {
  for (const name of ["Request duration", "Service round trip"]) {
    await expect(metrics.getByRole("group", { name }).locator("p")).toHaveText(
      "--",
    );
  }
}

let ttsJobSequence = 0;
let sttJobSequence = 0;

async function mockSttJob(
  page: Page,
  {
    transcript = "Hello world",
    serviceMs = 250,
    status = "COMPLETED",
    error = null,
    inspectRequest,
  }: {
    transcript?: string | null;
    serviceMs?: number | null;
    status?: "COMPLETED" | "FAILED" | "CANCELLED";
    error?: string | null;
    inspectRequest?: (request: Request) => void;
  } = {},
) {
  const jobId = `stt-job-${++sttJobSequence}`;

  await page.route(
    "**/voice/pipelines/speech-to-text/variants/*/runs",
    async (route) => {
      inspectRequest?.(route.request());
      await route.fulfill({
        status: 202,
        json: { job_id: jobId, status: "QUEUED" },
      });
    },
    { times: 1 },
  );
  await page.route(
    `**/jobs/audio/${jobId}/status`,
    (route) =>
      route.fulfill({
        json: {
          id: jobId,
          pipeline_id: "speech-to-text",
          pipeline_name: "Speech to Text",
          variant_id: "cpu",
          variant_name: "CPU",
          device: "CPU",
          operation: "speech_to_text",
          state: status,
          created_at: "2026-10-09T10:00:00Z",
          modified_at: "2026-10-09T10:00:01Z",
          transcript: status === "COMPLETED" ? transcript : null,
          artifact_available: false,
          artifact_url: null,
          service_round_trip_ms: serviceMs,
          error,
        },
      }),
    { times: 1 },
  );
}

async function mockTtsJob(
  page: Page,
  {
    content = wav(),
    serviceMs = 250,
    status = "COMPLETED",
    error = null,
    waitForStart,
    waitForStatus,
    inspectRequest,
  }: {
    content?: Buffer;
    serviceMs?: number | null;
    status?: "COMPLETED" | "FAILED" | "CANCELLED";
    error?: string | null;
    waitForStart?: Promise<void>;
    waitForStatus?: Promise<void>;
    inspectRequest?: (request: Request) => void;
  } = {},
) {
  const jobId = `tts-job-${++ttsJobSequence}`;
  const artifactUrl = `/api/v1/voice/jobs/${jobId}/artifact`;

  await page.route(
    "**/voice/pipelines/text-to-speech/variants/*/runs",
    async (route) => {
      inspectRequest?.(route.request());
      await waitForStart;
      await route
        .fulfill({
          status: 202,
          json: { job_id: jobId, status: "QUEUED" },
        })
        .catch(() => {});
    },
    { times: 1 },
  );
  await page.route(
    `**/jobs/audio/${jobId}/status`,
    async (route) => {
      await waitForStatus;
      await route
        .fulfill({
          json: {
            id: jobId,
            pipeline_id: "text-to-speech",
            pipeline_name: "Text to Speech",
            variant_id: "cpu",
            variant_name: "CPU",
            device: "CPU",
            operation: "text_to_speech",
            state: status,
            created_at: "2026-10-09T10:00:00Z",
            modified_at: "2026-10-09T10:00:01Z",
            transcript: null,
            artifact_available: status === "COMPLETED",
            artifact_url: status === "COMPLETED" ? artifactUrl : null,
            service_round_trip_ms: serviceMs,
            error,
          },
        })
        .catch(() => {});
    },
    { times: 1 },
  );
  await page.route(
    `**/voice/jobs/${jobId}/artifact`,
    (route) => route.fulfill({ contentType: "audio/wav", body: content }),
    { times: 1 },
  );
}

test.beforeEach(async ({ page }) => {
  recordingListRequests = [];
  recordingAudioRequests = [];
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/voice/pipelines")) {
      await route.fulfill({ json: AUDIO_PIPELINES });
      return;
    }
    if (path.endsWith("/voice/recordings")) {
      recordingListRequests.push(path);
      await route.fulfill({ json: AUDIO_RECORDINGS });
      return;
    }
    if (path.includes("/voice/recordings/") && path.endsWith("/audio")) {
      recordingAudioRequests.push(path);
      await route.fulfill({ contentType: "audio/wav", body: wav() });
      return;
    }
    if (path.endsWith("/models/check-status")) {
      const request = route.request().postDataJSON() as {
        display_names: string[];
      };
      await route.fulfill({
        json: {
          models: request.display_names.map((displayName) => ({
            name:
              AUDIO_MODELS.find((model) => model.display_name === displayName)
                ?.name ?? displayName,
            display_name: displayName,
            install_status: "installed",
          })),
        },
      });
      return;
    }
    if (path.endsWith("/models")) {
      await route.fulfill({ json: AUDIO_MODELS });
      return;
    }
    if (path.includes("/voice/")) return route.fallback();
    if (path.endsWith("/pipelines")) {
      await route.fulfill({ json: VISION_PIPELINES });
      return;
    }
    if (path.endsWith("/devices")) {
      await route.fulfill({
        json: [
          {
            device_name: "CPU",
            full_device_name: "Intel CPU",
            device_type: "INTEGRATED",
            device_family: "CPU",
            gpu_id: null,
          },
          {
            device_name: "GPU.0",
            full_device_name: "Intel GPU",
            device_type: "INTEGRATED",
            device_family: "GPU",
            gpu_id: 0,
          },
          {
            device_name: "NPU",
            full_device_name: "Intel NPU",
            device_type: "INTEGRATED",
            device_family: "NPU",
            gpu_id: null,
          },
        ],
      });
      return;
    }
    const body =
      path.endsWith("/status") || path.endsWith("/health")
        ? { status: "ready" }
        : [];
    await route.fulfill({ json: body });
  });
  await page.route("**/metrics/stream", (route) =>
    route.fulfill({ contentType: "text/event-stream", body: ": ready\n\n" }),
  );
  await page.goto(
    process.env.VOICE_UI_URL ??
      "http://127.0.0.1:5173/pipelines/audio/speech-to-text/cpu",
  );
});

test("shows a loader until the catalog finishes loading", async ({ page }) => {
  let releaseRequests: (() => void) | undefined;
  const pendingResponses = new Promise<void>((resolve) => {
    releaseRequests = resolve;
  });
  const timeSeriesPipeline = {
    ...VISION_PIPELINES[0],
    id: "time-series-1",
    name: "Anomaly Detection",
    type: "time_series",
  };

  await page.route("**/api/v1/pipelines", async (route) => {
    await pendingResponses;
    await route.fulfill({ json: [...VISION_PIPELINES, timeSeriesPipeline] });
  });
  await page.route("**/api/v1/voice/pipelines", async (route) => {
    await pendingResponses;
    await route.fulfill({ json: AUDIO_PIPELINES });
  });

  await page.goto(new URL("/pipelines", page.url()).toString(), {
    waitUntil: "domcontentloaded",
  });
  await expect(page.getByRole("tab", { name: "Vision" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Audio" })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Create Pipeline" }),
  ).toHaveCount(0);

  releaseRequests?.();

  await expect(
    page.getByRole("button", { name: "Create Pipeline" }),
  ).toBeVisible();
  await expect(
    page.getByText("People Detection", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Anomaly Detection")).toHaveCount(0);
});

test("shows no cards in the Audio tab when the Audio catalog is empty", async ({
  page,
}) => {
  await page.route("**/api/v1/voice/pipelines", (route) =>
    route.fulfill({ json: [] }),
  );

  await page.goto(new URL("/pipelines?tab=audio", page.url()).toString());

  await expect(page.getByRole("tab", { name: "Audio" })).toHaveAttribute(
    "data-state",
    "active",
  );
  await expect(page.locator('[data-slot="card"]')).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Create Pipeline" }),
  ).toBeDisabled();
});

test("lists Vision and Audio pipelines in separate tabs", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(new URL("/pipelines", page.url()).toString());

  const createPipeline = page.getByRole("button", { name: "Create Pipeline" });
  await expect(createPipeline).toHaveCount(1);
  await expect(
    page.getByRole("link", { name: "People Detection" }).first(),
  ).toHaveAttribute(
    "href",
    "/pipelines/vision/vision-1/default?source=pipelines",
  );
  await expect(page.getByText("Speech to Text")).toHaveCount(0);
  const visionCard = page.locator('[data-slot="card"]').first();
  const visionBox = await visionCard.boundingBox();

  await page.getByRole("tab", { name: "Audio" }).click();

  await expect(page).toHaveURL(/\/pipelines\?tab=audio$/);
  await expect(createPipeline).toBeDisabled();
  await expect(page.getByText("People Detection", { exact: true })).toHaveCount(
    0,
  );
  await expect(
    page.getByRole("link", { name: /Speech to Text/ }).first(),
  ).toHaveAttribute("href", "/pipelines/audio/speech-to-text/cpu");
  await expect(
    page.getByRole("link", { name: /Text to Speech/ }).first(),
  ).toHaveAttribute("href", "/pipelines/audio/text-to-speech/cpu");
  await expect(page.getByRole("img", { name: "Speech to Text" })).toBeVisible();
  await expect(page.getByRole("img", { name: "Text to Speech" })).toBeVisible();
  await expect(page.getByRole("link", { name: "NPU" })).toHaveAttribute(
    "href",
    "/pipelines/audio/speech-to-text/npu",
  );
  await expect(
    page.getByRole("button", { name: /Edit Pipeline|Delete/ }),
  ).toHaveCount(0);

  const audioBox = await page
    .locator('[data-slot="card"]')
    .first()
    .boundingBox();
  expect(visionBox).not.toBeNull();
  expect(audioBox).not.toBeNull();
  expect(audioBox!.width).toBeLessThanOrEqual(visionBox!.width + 8);
});

test("returns from an Audio pipeline to the Audio tab", async ({ page }) => {
  const back = page.getByRole("link", { name: "Back" });
  await expect(back).toHaveAttribute("href", "/pipelines?tab=audio");
  await expect(page.getByText("Back to Pipelines")).toHaveCount(0);
  await back.click();
  await expect(page).toHaveURL(/\/pipelines\?tab=audio$/);
  await expect(page.getByRole("tab", { name: "Audio" })).toHaveAttribute(
    "data-state",
    "active",
  );
});

test("prompts to install Whisper Base when the STT model is missing", async ({
  page,
}) => {
  await page.route("**/models/check-status", (route) =>
    route.fulfill({
      json: {
        models: [
          {
            name: "voice-whisper-base",
            display_name: "Whisper Base",
            install_status: "not_installed",
          },
        ],
      },
    }),
  );
  await page.reload();

  const dialog = page.getByRole("dialog", {
    name: "Required models are missing",
  });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("Whisper Base")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Install" })).toBeVisible();
  await dialog.getByRole("button", { name: "Continue" }).click();
  await expect(
    page.getByRole("button", { name: "Transcribe", exact: true }),
  ).toBeDisabled();
});

test("prompts to install SpeechT5 when the TTS model is missing", async ({
  page,
}) => {
  await page.route("**/models/check-status", (route) =>
    route.fulfill({
      json: {
        models: [
          {
            name: "voice-speecht5",
            display_name: "SpeechT5",
            install_status: "not_installed",
          },
        ],
      },
    }),
  );
  await page.goto(
    new URL("/pipelines/audio/text-to-speech/cpu", page.url()).toString(),
  );

  const dialog = page.getByRole("dialog", {
    name: "Required models are missing",
  });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("SpeechT5")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Install" })).toBeVisible();
  await dialog.getByRole("button", { name: "Continue" }).click();
  await expect(
    page.getByRole("button", { name: "Generate speech" }),
  ).toBeDisabled();
});

test("runs the predefined speech-to-text recording by default", async ({
  page,
}) => {
  await page.route(
    "**/voice/pipelines/speech-to-text/variants/cpu/runs",
    (route) => {
      expect(route.request().postDataJSON()).toEqual({
        recording: "sample_male.wav",
        language: "en",
      });
      return route.fulfill({
        status: 202,
        json: { job_id: "stt-job", status: "QUEUED" },
      });
    },
  );
  await page.route("**/jobs/audio/stt-job/status", (route) =>
    route.fulfill({
      json: {
        id: "stt-job",
        pipeline_id: "speech-to-text",
        pipeline_name: "Speech to Text",
        variant_id: "cpu",
        variant_name: "CPU",
        device: "CPU",
        operation: "speech_to_text",
        state: "COMPLETED",
        created_at: "2026-10-09T10:00:00Z",
        modified_at: "2026-10-09T10:00:01Z",
        transcript: "The managed recording was transcribed.",
        artifact_available: false,
        artifact_url: null,
        service_round_trip_ms: 125,
        error: null,
      },
    }),
  );

  await page.goto(
    new URL("/pipelines/audio/speech-to-text/cpu", page.url()).toString(),
  );
  await expect(
    page.getByRole("combobox", { name: "Predefined recording" }),
  ).toContainText("sample_male.wav");
  await expect(
    page.getByRole("button", { name: "Transcribe", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Transcribe", exact: true }).click();
  await expect(page.getByLabel("Transcription")).toHaveValue(
    "The managed recording was transcribed.",
  );
  await expect(page.getByText("Audio pipeline run started")).toHaveCount(1);
  await expect(page.getByText("Audio pipeline run completed")).toHaveCount(1);
});

test("lists predefined recordings from the recordings endpoint", async ({
  page,
}) => {
  const select = page.getByRole("combobox", { name: "Predefined recording" });
  await expect(select).toContainText("sample_male.wav");
  expect(recordingListRequests).toEqual(["/api/v1/voice/recordings"]);

  await select.click();
  await expect(page.getByRole("option")).toHaveText([
    "sample_male.wav (0:33)",
    "sample_female.wav (0:15)",
  ]);
  await page.getByRole("option", { name: /sample_female\.wav/ }).click();

  const preview = page.getByLabel("Input recording");
  await expect(preview).toHaveAttribute(
    "src",
    "/api/v1/voice/recordings/sample_female.wav/audio",
  );
  await expect(select).toContainText("sample_female.wav");
  await expect
    .poll(() => recordingAudioRequests)
    .toContain("/api/v1/voice/recordings/sample_female.wav/audio");

  await chooseOption(page, "Recognition language", "German");
  await mockSttJob(page, {
    transcript: "Hallo Welt",
    inspectRequest: (request) => {
      expect(request.url()).toContain(
        "/voice/pipelines/speech-to-text/variants/cpu/runs",
      );
      expect(request.postDataJSON()).toEqual({
        recording: "sample_female.wav",
        language: "de",
      });
    },
  });
  await page.getByRole("button", { name: "Transcribe", exact: true }).click();
  await expect(page.getByLabel("Transcription")).toHaveValue("Hallo Welt");
});

test("previews the selected audio for every input source", async ({ page }) => {
  const preview = page.getByLabel("Input recording");
  const transcribe = page.getByRole("button", {
    name: "Transcribe",
    exact: true,
  });
  await expect(
    page.getByRole("radio", { name: "Available audio samples" }),
  ).toBeChecked();
  await expect(preview).toHaveAttribute("src", /\/voice\/recordings\//);

  await page.getByRole("radio", { name: "Upload" }).click();
  await expect(page.getByText("No audio selected.")).toBeVisible();
  await expect(preview).toHaveCount(0);
  await expect(transcribe).toBeDisabled();

  await page.getByLabel("Audio file").setInputFiles({
    name: "sentence.wav",
    mimeType: "audio/wav",
    buffer: wav(),
  });
  await expect(page.getByRole("radio", { name: "Upload" })).toBeChecked();
  await expect(preview).toHaveAttribute("src", /^blob:/);
  await expect(page.getByText("Selected file: sentence.wav")).toBeVisible();
  await expect(transcribe).toBeEnabled();

  await page.getByRole("radio", { name: "Available audio samples" }).click();
  await expect(preview).toHaveAttribute(
    "src",
    "/api/v1/voice/recordings/sample_male.wav/audio",
  );
  await expect(page.getByText("Selected file:")).toHaveCount(0);

  await page.getByRole("radio", { name: "Microphone" }).click();
  await expect(page.getByText("No audio selected.")).toBeVisible();
  await expect(transcribe).toBeDisabled();
});

test("keeps upload available when predefined recordings fail to load", async ({
  page,
}) => {
  await page.route("**/api/v1/voice/recordings", (route) =>
    route.fulfill({ status: 500, json: { detail: "Unexpected error" } }),
  );
  await page.reload();

  await expect(page.getByRole("alert")).toHaveText(
    "Unable to load predefined recordings.",
  );
  await expect(
    page.getByRole("button", { name: "Transcribe", exact: true }),
  ).toBeDisabled();
  await mockSttJob(page, { transcript: "Uploaded fallback" });
  await page.getByLabel("Audio file").setInputFiles({
    name: "sentence.wav",
    mimeType: "audio/wav",
    buffer: wav(),
  });
  await page.getByRole("button", { name: "Transcribe", exact: true }).click();
  await expect(page.getByLabel("Transcription")).toHaveValue(
    "Uploaded fallback",
  );
});

test("runs the managed text-to-speech preset with YAML defaults", async ({
  page,
}) => {
  await page.route(
    "**/voice/pipelines/text-to-speech/variants/cpu/runs",
    (route) => {
      expect(route.request().postDataJSON()).toEqual({
        input: DEFAULT_TTS_TEXT,
        voice: "Ryan",
      });
      return route.fulfill({
        status: 202,
        json: { job_id: "tts-job", status: "QUEUED" },
      });
    },
  );
  await page.route("**/voice/jobs/tts-job/artifact", (route) =>
    route.fulfill({ contentType: "audio/wav", body: wav() }),
  );
  await page.route("**/jobs/audio/tts-job/status", (route) =>
    route.fulfill({
      json: {
        id: "tts-job",
        pipeline_id: "text-to-speech",
        pipeline_name: "Text to Speech",
        variant_id: "cpu",
        variant_name: "CPU",
        device: "CPU",
        operation: "text_to_speech",
        state: "COMPLETED",
        created_at: "2026-10-09T10:00:00Z",
        modified_at: "2026-10-09T10:00:01Z",
        transcript: null,
        artifact_available: true,
        artifact_url: "/api/v1/voice/jobs/tts-job/artifact",
        service_round_trip_ms: 250,
        error: null,
      },
    }),
  );

  await page.goto(
    new URL("/pipelines/audio/text-to-speech/cpu", page.url()).toString(),
  );
  await expect(page.getByLabel("Text input")).toHaveValue(DEFAULT_TTS_TEXT);
  await expect(page.getByLabel("Voice")).toHaveText("Ryan");
  await page.getByRole("button", { name: "Generate speech" }).click();
  await expect(page.getByLabel("Generated speech")).toHaveJSProperty(
    "readyState",
    4,
  );
  await expect(page.getByText("Audio pipeline run started")).toHaveCount(1);
  await expect(page.getByText("Audio pipeline run completed")).toHaveCount(1);
});

test("Audio variants control STT and TTS devices", async ({ page }) => {
  await mockSttJob(page, {
    inspectRequest: (request) => {
      const body = request.postData() ?? "";
      expect(request.url()).toContain(
        "/voice/pipelines/speech-to-text/variants/gpu/runs",
      );
      expect(request.headers()["content-type"]).toContain(
        "multipart/form-data",
      );
      expect(body).toContain('name="file"');
      expect(body).toContain('name="language"');
      expect(body).not.toContain('name="device"');
    },
  });
  await mockTtsJob(page, {
    inspectRequest: (request) => {
      expect(request.url()).toContain(
        "/voice/pipelines/text-to-speech/variants/gpu/runs",
      );
      expect(request.postDataJSON()).toEqual({
        input: "Hello world",
        voice: "Ryan",
      });
    },
  });

  await page.getByRole("button", { name: "Switch variant" }).click();
  await expect(page.getByRole("menuitem")).toHaveText(["CPU", "GPU", "NPU"]);
  await page.getByRole("menuitem", { name: "GPU", exact: true }).click();
  await expect(page).toHaveURL(/\/pipelines\/audio\/speech-to-text\/gpu$/);
  await expect(page.getByText("(GPU)", { exact: true })).toBeVisible();
  await expect(page.getByRole("tab")).toHaveCount(0);
  await expect(page.getByLabel("Text input")).toHaveCount(0);
  await page.getByLabel("Audio file").setInputFiles({
    name: "sentence.wav",
    mimeType: "audio/wav",
    buffer: wav(),
  });
  await page.getByRole("button", { name: "Transcribe", exact: true }).click();
  await expect(page.getByLabel("Transcription")).toHaveValue("Hello world");

  await page.goto(
    new URL("/pipelines/audio/text-to-speech/cpu", page.url()).toString(),
  );
  await expect(page.getByRole("tab")).toHaveCount(0);
  await expect(page.getByLabel("Audio file")).toHaveCount(0);
  await page.getByRole("button", { name: "Switch variant" }).click();
  await expect(page.getByRole("menuitem")).toHaveText(["CPU", "GPU"]);
  await page.getByRole("menuitem", { name: "GPU", exact: true }).click();
  await expect(page.getByText("(GPU)", { exact: true })).toBeVisible();
  await page.getByLabel("Text input").fill("Hello world");
  await page.getByRole("button", { name: "Generate speech" }).click();
  await expect(page.getByLabel("Generated speech")).toHaveJSProperty(
    "readyState",
    4,
  );
  await expect(page.getByLabel("Speech to text device")).toHaveCount(0);
  await expect(page.getByLabel("Text to speech device")).toHaveCount(0);
});

test("submits audio formats for service-side validation", async ({ page }) => {
  await mockSttJob(page, {
    transcript: "Service accepted audio",
    inspectRequest: (request) => {
      const body = request.postData() ?? "";
      expect(body).toContain('filename="sample.mp3"');
      expect(body).toContain("Content-Type: audio/mpeg");
    },
  });

  await expect(page.getByText("Maximum size: 200 MiB")).toBeVisible();
  await expect(
    page.getByText("Formats: WAV, MP3, M4A, MP4, MKV, MOV, AVI"),
  ).toBeVisible();
  await page.getByLabel("Audio file").setInputFiles({
    name: "sample.mp3",
    mimeType: "audio/mpeg",
    buffer: wav(),
  });
  await expect(
    page.getByRole("button", { name: "Transcribe", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Transcribe", exact: true }).click();
  await expect(page.getByLabel("Transcription")).toHaveValue(
    "Service accepted audio",
  );
});

test("shows Audio Analyzer file validation errors", async ({ page }) => {
  await page.route(
    "**/voice/pipelines/speech-to-text/variants/*/runs",
    (route) =>
      route.fulfill({
        status: 400,
        json: { detail: "File too large" },
      }),
  );

  await page.getByLabel("Audio file").setInputFiles({
    name: "large.wav",
    mimeType: "audio/wav",
    buffer: wav(),
  });
  await page.getByRole("button", { name: "Transcribe", exact: true }).click();

  await expect(page.getByRole("alert")).toHaveText("File too large");
  await expect(page.getByText("Audio pipeline run failed")).toHaveCount(1);
  await expect(page.getByText("File too large")).toHaveCount(2);
});

for (const viewport of [
  { width: 1440, height: 900 },
  { width: 390, height: 844 },
]) {
  test(`independent conversions at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await expect(
      page.getByText("There are no models in the system."),
    ).toHaveCount(0);
    await expect(
      page.getByRole("heading", {
        name: "Automatic Speech Recognition",
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", {
        name: "Automatic Speech Recognition Workload Configuration",
        exact: true,
      }),
    ).toBeVisible();
    await expect(page.getByText(/Pipelines \/ Audio/)).toHaveCount(0);
    const recordBox = await page
      .getByRole("button", { name: "Record", exact: true })
      .boundingBox();
    const uploadBox = await page
      .getByRole("button", { name: /^Upload audio/ })
      .boundingBox();
    const predefinedSelect = page.getByRole("combobox", {
      name: "Predefined recording",
    });
    await expect(predefinedSelect).toBeVisible();
    const predefinedBox = await predefinedSelect.boundingBox();
    const languageBox = await page
      .getByLabel("Recognition language")
      .boundingBox();
    expect(recordBox).not.toBeNull();
    expect(uploadBox).not.toBeNull();
    expect(predefinedBox).not.toBeNull();
    expect(languageBox).not.toBeNull();
    expect(Math.abs(recordBox!.width - uploadBox!.width)).toBeLessThan(2);
    expect(Math.abs(recordBox!.width - predefinedBox!.width)).toBeLessThan(2);
    expect(uploadBox!.y).toBeGreaterThan(predefinedBox!.y);
    expect(recordBox!.y).toBeGreaterThan(uploadBox!.y);
    expect(languageBox!.y).toBeGreaterThan(recordBox!.y);
    const horizontalOverflow = await page.evaluate(() => {
      let element: HTMLElement | null = document.querySelector("#voice-file");
      while (
        element &&
        !["auto", "scroll"].includes(getComputedStyle(element).overflowX)
      ) {
        element = element.parentElement;
      }
      return element ? element.scrollWidth - element.clientWidth : 0;
    });
    expect(horizontalOverflow).toBeLessThanOrEqual(1);
    const sttMetrics = page.getByRole("region", {
      name: "Speech to text metrics",
    });
    const requestDurationCard = sttMetrics.getByRole("group", {
      name: "Request duration",
    });
    const serviceRoundTripCard = sttMetrics.getByRole("group", {
      name: "Service round trip",
    });
    const metricsRail = page.getByRole("complementary", {
      name: "Performance and platform metrics",
    });
    await expectMetricsEmpty(sttMetrics);
    await expect(requestDurationCard).toBeVisible();
    await expect(serviceRoundTripCard).toBeVisible();
    const requestCardBox = await requestDurationCard.boundingBox();
    const serviceCardBox = await serviceRoundTripCard.boundingBox();
    expect(requestCardBox).not.toBeNull();
    expect(serviceCardBox).not.toBeNull();
    if (viewport.width >= 1280) {
      expect(Math.abs(serviceCardBox!.y - requestCardBox!.y)).toBeLessThan(2);
      expect(serviceCardBox!.x).toBeGreaterThan(requestCardBox!.x);
    } else {
      expect(serviceCardBox!.y).toBeGreaterThan(requestCardBox!.y);
    }
    await expect(
      sttMetrics.getByRole("heading", { name: "Recent service round trips" }),
    ).toHaveCount(0);
    await expect(
      sttMetrics.getByText("Requested device", { exact: true }),
    ).toHaveCount(0);
    await expect(
      sttMetrics.getByText("Input audio", { exact: true }),
    ).toHaveCount(0);
    await expect(
      metricsRail.getByRole("heading", { name: "CPU Usage", exact: true }),
    ).toBeVisible();
    const workflowBox = await page
      .getByRole("heading", {
        name: "Automatic Speech Recognition Workload Configuration",
        exact: true,
      })
      .boundingBox();
    const metricsBox = await metricsRail.boundingBox();
    expect(workflowBox).not.toBeNull();
    expect(metricsBox).not.toBeNull();
    if (viewport.width >= 1280) {
      expect(metricsBox!.x).toBeGreaterThan(workflowBox!.x);
    } else {
      expect(metricsBox!.y).toBeGreaterThan(workflowBox!.y);
    }
    await mockSttJob(page, {
      serviceMs: 250,
      inspectRequest: (request) => {
        expect(request.headers()["content-type"]).toContain(
          "multipart/form-data",
        );
        expect(request.postData()).not.toContain("session_id");
      },
    });
    await mockTtsJob(page, {
      serviceMs: 750,
      inspectRequest: (request) => {
        expect(request.postDataJSON()).toEqual({
          input: "Hello world",
          voice: "Angus",
        });
      },
    });
    await expect(
      page.getByRole("button", { name: "Transcribe", exact: true }),
    ).toBeEnabled();
    await page.getByLabel("Audio file").setInputFiles({
      name: "sentence.wav",
      mimeType: "audio/wav",
      buffer: wav(),
    });
    await page.getByRole("button", { name: "Transcribe", exact: true }).click();
    await expect(
      page.getByRole("textbox", { name: "Transcription", exact: true }),
    ).toHaveValue("Hello world");
    const inputWaveform = page.getByRole("img", {
      name: "Selected audio waveform",
    });
    await expect(inputWaveform).toHaveAttribute("aria-busy", "false");
    await expect(inputWaveform.locator(".recharts-bar-rectangle")).toHaveCount(
      160,
    );
    await page
      .getByRole("heading", {
        name: "Automatic Speech Recognition",
        exact: true,
      })
      .scrollIntoViewIfNeeded();
    await page.screenshot({
      path: `/tmp/voice-redesign-stt-${viewport.width}.png`,
      fullPage: true,
    });
    await expect(sttMetrics).toContainText("250.00ms");
    const requestDuration = requestDurationCard.locator("p");
    await expect(requestDuration).toHaveText(/^\d+\.\d{2}ms$/);
    expect(
      Number.parseFloat((await requestDuration.textContent())!),
    ).toBeGreaterThan(0);
    await sttMetrics.scrollIntoViewIfNeeded();
    await page.screenshot({
      path: `/tmp/voice-stt-${viewport.width}.png`,
      fullPage: true,
    });
    await page.goto(
      new URL("/pipelines/audio/text-to-speech/cpu", page.url()).toString(),
    );
    await expectMetricsEmpty(
      page.getByRole("region", { name: "Text to speech metrics" }),
    );
    const ttsMetricsPanel = page.getByRole("region", {
      name: "Text to speech metrics",
    });
    await expect(
      ttsMetricsPanel.getByText("Requested device", { exact: true }),
    ).toHaveCount(0);
    await expect(
      ttsMetricsPanel.getByText("Characters", { exact: true }),
    ).toHaveCount(0);
    await expect(
      ttsMetricsPanel.getByText("Output audio", { exact: true }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "Generate speech" }),
    ).toBeEnabled();
    await expect(page.getByLabel("Voice")).toHaveText("Ryan");
    const voiceBox = await page.getByLabel("Voice").boundingBox();
    const textBox = await page.getByLabel("Text input").boundingBox();
    expect(voiceBox).not.toBeNull();
    expect(textBox).not.toBeNull();
    expect(Math.abs(textBox!.width - voiceBox!.width)).toBeLessThan(2);
    expect(Math.abs(textBox!.x - voiceBox!.x)).toBeLessThan(2);
    expect(textBox!.y).toBeGreaterThan(voiceBox!.y);
    await expect(page.getByLabel("Sample text")).toHaveCount(0);
    await chooseOption(page, "Voice", "Angus");
    const textInput = page.getByLabel("Text input");
    await expect(textInput).toHaveAttribute("maxlength", "200");
    await textInput.fill("Hello world");
    await expect(
      page.getByText("11 / 200", { exact: true }).first(),
    ).toBeVisible();
    await page.getByRole("button", { name: "Generate speech" }).click();
    await expect(page.getByLabel("Generated speech")).toHaveJSProperty(
      "readyState",
      4,
    );
    await expect(
      page.getByRole("link", { name: "Download WAV" }),
    ).toBeVisible();
    await expect(
      page.getByRole("region", { name: "Text to speech metrics" }),
    ).toContainText("750.00ms");
    const waveform = page.getByRole("img", {
      name: "Synthesized audio waveform",
    });
    await expect(waveform).toHaveAttribute("aria-busy", "false");
    const heights = await waveform
      .locator(".recharts-bar-rectangle path")
      .evaluateAll((elements) =>
        elements.map(
          (element) => (element as SVGGraphicsElement).getBBox().height,
        ),
      );
    expect(heights.length).toBe(160);
    expect(Math.max(...heights) - Math.min(...heights)).toBeGreaterThan(10);
    await page
      .getByLabel("Generated speech")
      .evaluate((element: HTMLAudioElement) => element.play());
    await expect(page.getByLabel("Generated speech")).toHaveJSProperty(
      "paused",
      false,
    );
    await page
      .getByLabel("Generated speech")
      .evaluate((element: HTMLAudioElement) => element.pause());
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("link", { name: "Download WAV" }).click();
    expect((await downloadPromise).suggestedFilename()).toBe("speech.wav");
    await page
      .getByRole("heading", { name: "Text to Speech", exact: true })
      .scrollIntoViewIfNeeded();
    await page.screenshot({
      path: `/tmp/voice-redesign-tts-${viewport.width}.png`,
      fullPage: true,
    });
    await page.getByRole("button", { name: "Toggle theme" }).click();
    await expect(page.locator("html")).toHaveClass(/dark/);
    await expect(page.getByLabel("Text input")).toHaveCSS(
      "color",
      "oklch(1 0 0)",
    );
    await page.screenshot({
      path: `/tmp/voice-redesign-dark-${viewport.width}.png`,
      fullPage: true,
    });
    await page.getByRole("button", { name: "Toggle theme" }).click();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page
      .getByRole("region", { name: "Text to speech metrics" })
      .scrollIntoViewIfNeeded();
    await page.screenshot({
      path: `/tmp/voice-tts-${viewport.width}.png`,
      fullPage: true,
    });
    await chooseOption(page, "Voice", "Miles");
    await expect(page.getByLabel("Text input")).toHaveValue("Hello world");
    await expect(page.getByLabel("Generated speech")).toHaveCount(0);
    await expectMetricsEmpty(
      page.getByRole("region", { name: "Text to speech metrics" }),
    );
    await page
      .getByLabel("Text input")
      .fill("Welcome to Intel Performance Studio.");
    await expect(page.getByLabel("Text input")).toHaveValue(
      "Welcome to Intel Performance Studio.",
    );
    await expect(page.getByLabel("Generated speech")).toHaveCount(0);
    await expectMetricsEmpty(
      page.getByRole("region", { name: "Text to speech metrics" }),
    );
    await expect(
      metricsRail.getByRole("heading", { name: "CPU Usage", exact: true }),
    ).toBeVisible();
    await expect(
      metricsRail.getByRole("heading", { name: /Frame Rate|Latency/ }),
    ).toHaveCount(0);
    const voiceMetricsBox = await ttsMetricsPanel.boundingBox();
    const platformMetricsBox = await metricsRail
      .getByRole("heading", { name: "CPU Usage", exact: true })
      .boundingBox();
    expect(voiceMetricsBox).not.toBeNull();
    expect(platformMetricsBox).not.toBeNull();
    expect(platformMetricsBox!.y).toBeGreaterThan(voiceMetricsBox!.y);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page
      .getByText("CPU Usage Over Time", { exact: true })
      .scrollIntoViewIfNeeded();
    await page.screenshot({
      path: `/tmp/voice-platform-${viewport.width}.png`,
      fullPage: true,
    });
  });
}

test("waveform scales quiet audio and keeps silence flat", async ({ page }) => {
  await page.goto(
    new URL("/pipelines/audio/text-to-speech/cpu", page.url()).toString(),
  );
  await page.getByLabel("Text input").fill("Hello world");
  for (const volume of [0.01, 1, 0]) {
    const content = wav(volume);
    await mockTtsJob(page, { content });
    await page.getByRole("button", { name: "Generate speech" }).click();
    const waveform = page.getByRole("img", {
      name: "Synthesized audio waveform",
    });
    await expect(waveform).toHaveAttribute("aria-busy", "false");
    const heights = await waveform
      .locator(".recharts-bar-rectangle path")
      .evaluateAll((elements) =>
        elements.map(
          (element) => (element as SVGGraphicsElement).getBBox().height,
        ),
      );
    if (volume === 0) {
      expect(heights.every((height) => height === 0)).toBe(true);
    } else {
      expect(heights).toHaveLength(160);
      expect(Math.max(...heights)).toBeGreaterThan(48);
      expect(Math.max(...heights)).toBeLessThan(56);
      expect(Math.max(...heights) - Math.min(...heights)).toBeGreaterThan(20);
    }
    const audioBytes = await page
      .getByLabel("Generated speech")
      .evaluate(async (element: HTMLAudioElement) =>
        Array.from(
          new Uint8Array(await (await fetch(element.src)).arrayBuffer()),
        ),
      );
    expect(Buffer.from(audioBytes)).toEqual(content);
    if (volume === 0.01) {
      await waveform.scrollIntoViewIfNeeded();
      await page.screenshot({
        path: "/tmp/voice-waveform-quiet.png",
        fullPage: true,
      });
    }
  }
});

test("service failure and cancellation", async ({ page }) => {
  await page.goto(
    new URL("/pipelines/audio/text-to-speech/cpu", page.url()).toString(),
  );
  await page.getByLabel("Text input").fill("Hello world");
  const metrics = page.getByRole("region", { name: "Text to speech metrics" });
  await mockTtsJob(page, { serviceMs: 250 });
  await page.getByRole("button", { name: "Generate speech" }).click();
  await expect(metrics).toContainText("250.00ms");
  await mockTtsJob(page, {
    status: "FAILED",
    serviceMs: null,
    error: "The speech service is unavailable.",
  });
  await page.getByRole("button", { name: "Generate speech" }).click();
  await expect(page.getByRole("alert")).toHaveText(
    "The speech service is unavailable.",
  );
  await expect(page.getByText("Audio pipeline run failed")).toHaveCount(1);
  await expectMetricsEmpty(metrics);
  let release: (() => void) | undefined;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  await mockTtsJob(page, { serviceMs: 900, waitForStart: pending });
  await page.getByRole("button", { name: "Generate speech" }).click();
  await expect(
    page.getByRole("button", { name: "Stop", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Stop", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Generate speech" }),
  ).toBeEnabled();
  await expect(page.getByLabel("Generated speech")).toHaveCount(0);
  await expectMetricsEmpty(metrics);
  await mockTtsJob(page, { serviceMs: 700 });
  await page.getByRole("button", { name: "Generate speech" }).click();
  await expect(metrics).toContainText("700.00ms");
  release?.();
  await expect(metrics).not.toContainText("900.00ms");
  await expect(page.getByText("Audio pipeline run completed")).toHaveCount(2);
});

test("shows a backend cancelled job as cancelled, not failed", async ({
  page,
}) => {
  await page.goto(
    new URL("/pipelines/audio/text-to-speech/cpu", page.url()).toString(),
  );
  await page.getByLabel("Text input").fill("Hello world");

  await mockTtsJob(page, {
    status: "CANCELLED",
    serviceMs: null,
    error: "Audio pipeline execution was cancelled.",
  });
  await page.getByRole("button", { name: "Generate speech" }).click();
  await expect(page.getByText("Audio pipeline run cancelled")).toHaveCount(1);
  await expect(page.getByText("Audio pipeline run failed")).toHaveCount(0);
});

for (const scenario of [
  {
    name: "speech-to-text",
    path: "/pipelines/audio/speech-to-text/cpu",
    run: "Transcribe",
    operation: "speech_to_text",
  },
  {
    name: "text-to-speech",
    path: "/pipelines/audio/text-to-speech/cpu",
    run: "Generate speech",
    operation: "text_to_speech",
  },
] as const) {
  test(`Stop cancels a running ${scenario.name} job through the stop endpoint`, async ({
    page,
  }) => {
    const jobId = `cancel-${scenario.name}`;
    const stopRequests: string[] = [];
    let stopped = false;
    await page.route(
      `**/voice/pipelines/${scenario.name}/variants/*/runs`,
      (route) =>
        route.fulfill({
          status: 202,
          json: { job_id: jobId, status: "QUEUED" },
        }),
    );
    await page.route(`**/jobs/audio/${jobId}/status`, (route) =>
      route.fulfill({
        json: {
          id: jobId,
          pipeline_id: scenario.name,
          pipeline_name: scenario.name,
          variant_id: "cpu",
          variant_name: "CPU",
          device: "CPU",
          operation: scenario.operation,
          state: stopped ? "CANCELLED" : "RUNNING",
          created_at: "2026-10-09T10:00:00Z",
          modified_at: "2026-10-09T10:00:01Z",
          transcript: null,
          artifact_available: false,
          artifact_url: null,
          service_round_trip_ms: null,
          error: null,
        },
      }),
    );
    await page.route(`**/api/v1/jobs/audio/${jobId}`, (route) => {
      stopRequests.push(
        `${route.request().method()} ${new URL(route.request().url()).pathname}`,
      );
      stopped = true;
      return route.fulfill({ json: { message: `Job ${jobId} stopped` } });
    });

    await page.goto(new URL(scenario.path, page.url()).toString());
    if (scenario.name === "text-to-speech") {
      await page.getByLabel("Text input").fill("Hello world");
    }
    const run = page.getByRole("button", { name: scenario.run, exact: true });
    await expect(run).toBeEnabled();
    await run.click();

    const stop = page.getByRole("button", { name: "Stop", exact: true });
    await expect(stop).toBeVisible();
    await expect(run).toHaveCount(0);
    await expect(page.getByText("Audio pipeline run started")).toHaveCount(1);
    expect(stopRequests).toEqual([]);

    await stop.click();

    await expect(page.getByText("Audio pipeline run cancelled")).toHaveCount(1);
    await expect(page.getByText("Audio pipeline run failed")).toHaveCount(0);
    expect(stopRequests).toEqual([`DELETE /api/v1/jobs/audio/${jobId}`]);
    await expect(
      page.getByRole("button", { name: scenario.run, exact: true }),
    ).toBeEnabled();
    await expect(stop).toHaveCount(0);
  });
}

test("reports a failed stop request and keeps the job running", async ({
  page,
}) => {
  const jobId = "stop-failure";
  await page.route(
    "**/voice/pipelines/text-to-speech/variants/*/runs",
    (route) =>
      route.fulfill({ status: 202, json: { job_id: jobId, status: "QUEUED" } }),
  );
  await page.route(`**/jobs/audio/${jobId}/status`, (route) =>
    route.fulfill({
      json: {
        id: jobId,
        pipeline_id: "text-to-speech",
        pipeline_name: "Text to Speech",
        variant_id: "cpu",
        variant_name: "CPU",
        device: "CPU",
        operation: "text_to_speech",
        state: "RUNNING",
        created_at: "2026-10-09T10:00:00Z",
        modified_at: "2026-10-09T10:00:01Z",
        transcript: null,
        artifact_available: false,
        artifact_url: null,
        service_round_trip_ms: null,
        error: null,
      },
    }),
  );
  await page.route(`**/api/v1/jobs/audio/${jobId}`, (route) =>
    route.fulfill({
      status: 409,
      json: { message: `Audio pipeline job '${jobId}' is not running.` },
    }),
  );
  await page.goto(
    new URL("/pipelines/audio/text-to-speech/cpu", page.url()).toString(),
  );
  await page.getByLabel("Text input").fill("Hello world");
  await page.getByRole("button", { name: "Generate speech" }).click();

  const stop = page.getByRole("button", { name: "Stop", exact: true });
  await stop.click();

  await expect(stop).toBeEnabled();
  await expect(page.getByText("Audio pipeline run cancelled")).toHaveCount(0);
});

test("missing or zero service timing does not break conversion", async ({
  page,
}) => {
  await page.goto(
    new URL("/pipelines/audio/text-to-speech/cpu", page.url()).toString(),
  );
  await page.getByLabel("Text input").fill("Hello world");
  for (const value of [null, 0]) {
    await mockTtsJob(page, { serviceMs: value });
    await page.getByRole("button", { name: "Generate speech" }).click();
    await expect(page.getByLabel("Generated speech")).toHaveJSProperty(
      "readyState",
      4,
    );
    const metrics = page.getByRole("region", {
      name: "Text to speech metrics",
    });
    await expect(
      metrics.getByRole("heading", { name: "Request duration" }),
    ).toBeVisible();
    if (value === 0) {
      await expect(metrics).toContainText("0.00ms");
    } else {
      const serviceDuration = metrics
        .getByRole("group", {
          name: "Service round trip",
        })
        .locator("p");
      await expect(serviceDuration).toHaveText("--");
    }
  }
});

test("recording produces mono PCM WAV and releases microphone", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const original = navigator.mediaDevices.getUserMedia.bind(
      navigator.mediaDevices,
    );
    navigator.mediaDevices.getUserMedia = async (constraints) => {
      const stream = await original(constraints);
      Object.assign(window, { voiceTestStream: stream });
      return stream;
    };
  });
  await page.reload();
  await page.getByRole("button", { name: "Record", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Stop recording" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Stop recording" }).click();
  await expect(page.getByRole("radio", { name: "Microphone" })).toBeChecked();
  await expect(page.getByLabel("Input recording")).toHaveJSProperty(
    "readyState",
    4,
  );
  const result = await page
    .getByLabel("Input recording")
    .evaluate(async (element: HTMLAudioElement) => {
      const data = new DataView(await (await fetch(element.src)).arrayBuffer());
      return {
        channels: data.getUint16(22, true),
        sampleRate: data.getUint32(24, true),
        bits: data.getUint16(34, true),
      };
    });
  expect(result).toEqual({ channels: 1, sampleRate: 16000, bits: 16 });
  expect(
    await page.evaluate(() => {
      const stream = (window as unknown as { voiceTestStream: MediaStream })
        .voiceTestStream;
      return stream.getTracks().every((track) => track.readyState === "ended");
    }),
  ).toBe(true);
});

test("shows microphone errors inside the Microphone card", async ({ page }) => {
  await page.addInitScript(() => {
    navigator.mediaDevices.getUserMedia = () =>
      Promise.reject(new Error("Permission denied"));
  });
  await page.reload();
  await page.getByRole("button", { name: "Record", exact: true }).click();

  const alert = page.getByRole("alert");
  await expect(alert).toHaveText("Permission denied");
  await expect(alert).toBeInViewport();
  await expect(
    page.getByRole("button", { name: "Record", exact: true }),
  ).toBeEnabled();
});

test("waveform failure preserves audio playback and conversion metrics", async ({
  page,
}) => {
  await page.addInitScript(() => {
    window.OfflineAudioContext = class {
      constructor() {
        throw new Error("Waveform decoder unavailable");
      }
    } as unknown as typeof OfflineAudioContext;
  });
  await page.goto(
    new URL("/pipelines/audio/text-to-speech/cpu", page.url()).toString(),
  );
  await page.getByLabel("Text input").fill("Your audio is ready for playback.");
  await mockTtsJob(page, { serviceMs: 120 });
  await page.getByRole("button", { name: "Generate speech" }).click();
  await expect(
    page.getByText("Waveform unavailable", { exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Generated speech")).toHaveJSProperty(
    "readyState",
    4,
  );
  await expect(
    page.getByRole("region", { name: "Text to speech metrics" }),
  ).toContainText("120.00ms");
});
