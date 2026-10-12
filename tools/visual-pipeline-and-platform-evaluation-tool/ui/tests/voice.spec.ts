// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { expect, test, type Page, type Request } from "@playwright/test";
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
      audio: "OSR_us_000_0060_8k.wav",
      language: "en",
      text: null,
      voice: null,
    },
    available: true,
    unavailable_reason: null,
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
    available: true,
    unavailable_reason: null,
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

let ttsJobSequence = 0;

async function mockTtsJob(
  page: Page,
  {
    content = wav(),
    serviceMs = 250,
    status = "COMPLETED",
    error = null,
    waitForStart,
    inspectRequest,
  }: {
    content?: Buffer;
    serviceMs?: number | null;
    status?: "COMPLETED" | "FAILED";
    error?: string | null;
    waitForStart?: Promise<void>;
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
    `**/voice/jobs/${jobId}`,
    (route) =>
      route.fulfill({
        json: {
          id: jobId,
          pipeline_id: "text-to-speech",
          pipeline_name: "Text to Speech",
          variant_id: "cpu",
          variant_name: "CPU",
          device: "CPU",
          operation: "text_to_speech",
          status,
          created_at: "2026-10-09T10:00:00Z",
          modified_at: "2026-10-09T10:00:01Z",
          transcript: null,
          artifact_url: status === "COMPLETED" ? artifactUrl : null,
          service_round_trip_ms: serviceMs,
          error,
        },
      }),
    { times: 1 },
  );
  await page.route(
    `**/voice/jobs/${jobId}/artifact`,
    (route) => route.fulfill({ contentType: "audio/wav", body: content }),
    { times: 1 },
  );
}

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/voice/pipelines")) {
      await route.fulfill({ json: AUDIO_PIPELINES });
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

test("hides pipeline sections until the catalog finishes loading", async ({
  page,
}) => {
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
  await expect(
    page.getByRole("button", { name: "Create Pipeline" }),
  ).toBeVisible();
  await expect(page.getByRole("region", { name: "Vision" })).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Time Series" })).toHaveCount(
    0,
  );
  await expect(page.getByRole("region", { name: "Audio" })).toHaveCount(0);

  releaseRequests?.();

  await expect(page.getByRole("region", { name: "Vision" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Time Series" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Audio" })).toBeVisible();
});

test("hides Audio when the Audio catalog is empty", async ({ page }) => {
  await page.route("**/api/v1/voice/pipelines", (route) =>
    route.fulfill({ json: [] }),
  );

  await page.goto(new URL("/pipelines", page.url()).toString());

  await expect(page.getByRole("region", { name: "Vision" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Audio" })).toHaveCount(0);
});

test("groups Vision, Time Series, and Audio pipelines", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(new URL("/pipelines", page.url()).toString());

  const createPipeline = page.getByRole("button", { name: "Create Pipeline" });
  await expect(createPipeline).toBeVisible();
  await expect(createPipeline).toHaveCount(1);
  const vision = page.getByRole("region", { name: "Vision" });
  await expect(vision).toBeVisible();
  await expect(
    vision.getByRole("button", { name: "Create Pipeline" }),
  ).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Time Series" })).toHaveCount(
    0,
  );
  const audio = page.getByRole("region", { name: "Audio" });
  await expect(audio).toBeVisible();
  await expect(
    audio.getByRole("link", { name: /Speech to Text/ }),
  ).toHaveAttribute("href", "/pipelines/audio/speech-to-text/cpu");
  await expect(
    audio.getByRole("link", { name: /Text to Speech/ }),
  ).toHaveAttribute("href", "/pipelines/audio/text-to-speech/cpu");
  await expect(
    audio.getByRole("img", { name: "Speech to Text" }),
  ).toBeVisible();
  await expect(
    audio.getByRole("img", { name: "Text to Speech" }),
  ).toBeVisible();

  const visionCard = vision.locator('[data-slot="card"]').first();
  const audioCard = audio.locator('[data-slot="card"]').first();
  const visionBox = await visionCard.boundingBox();
  const audioBox = await audioCard.boundingBox();
  expect(visionBox).not.toBeNull();
  expect(audioBox).not.toBeNull();
  expect(audioBox!.width).toBeLessThanOrEqual(visionBox!.width + 8);
});

test("returns from an Audio pipeline to the pipeline catalog", async ({
  page,
}) => {
  const back = page.getByRole("link", { name: "Back" });
  await expect(back).toHaveAttribute("href", "/pipelines");
  await expect(page.getByText("Back to Pipelines")).toHaveCount(0);
  await back.click();
  await expect(page).toHaveURL(/\/pipelines$/);
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

test("runs the managed speech-to-text preset without an upload", async ({
  page,
}) => {
  await page.route(
    "**/voice/pipelines/speech-to-text/variants/cpu/runs",
    (route) =>
      route.fulfill({
        status: 202,
        json: { job_id: "stt-job", status: "QUEUED" },
      }),
  );
  await page.route("**/voice/jobs/stt-job", (route) =>
    route.fulfill({
      json: {
        id: "stt-job",
        pipeline_id: "speech-to-text",
        pipeline_name: "Speech to Text",
        variant_id: "cpu",
        variant_name: "CPU",
        device: "CPU",
        operation: "speech_to_text",
        status: "COMPLETED",
        created_at: "2026-10-09T10:00:00Z",
        modified_at: "2026-10-09T10:00:01Z",
        transcript: "The managed recording was transcribed.",
        artifact_url: null,
        service_round_trip_ms: 125,
        error: null,
      },
    }),
  );

  await page.goto(
    new URL("/pipelines/audio/speech-to-text/cpu", page.url()).toString(),
  );
  await expect(page.getByText("OSR_us_000_0060_8k.wav")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Transcribe", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Transcribe", exact: true }).click();
  await expect(page.getByLabel("Transcription")).toHaveValue(
    "The managed recording was transcribed.",
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
  await page.route("**/voice/jobs/tts-job", (route) =>
    route.fulfill({
      json: {
        id: "tts-job",
        pipeline_id: "text-to-speech",
        pipeline_name: "Text to Speech",
        variant_id: "cpu",
        variant_name: "CPU",
        device: "CPU",
        operation: "text_to_speech",
        status: "COMPLETED",
        created_at: "2026-10-09T10:00:00Z",
        modified_at: "2026-10-09T10:00:01Z",
        transcript: null,
        artifact_url: "/api/v1/voice/jobs/tts-job/artifact",
        service_round_trip_ms: 250,
        error: null,
      },
    }),
  );

  await page.goto(
    new URL("/pipelines/audio/text-to-speech/cpu", page.url()).toString(),
  );
  await expect(page.getByLabel("Text input (English)")).toHaveValue(
    DEFAULT_TTS_TEXT,
  );
  await expect(page.getByLabel("Voice")).toHaveText("Ryan");
  await page.getByRole("button", { name: "Generate speech" }).click();
  await expect(page.getByLabel("Generated speech")).toHaveJSProperty(
    "readyState",
    4,
  );
});

test("Audio variants control STT and TTS devices", async ({ page }) => {
  await page.route("**/voice/transcriptions", async (route) => {
    const body = route.request().postData() ?? "";
    expect(body).toContain('name="device"');
    expect(body).toContain("GPU");
    await route.fulfill({ json: { text: "Hello world" } });
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
  await expect(page.getByLabel("Text input (English)")).toHaveCount(0);
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
  await page.getByLabel("Text input (English)").fill("Hello world");
  await page.getByRole("button", { name: "Generate speech" }).click();
  await expect(page.getByLabel("Generated speech")).toHaveJSProperty(
    "readyState",
    4,
  );
  await expect(page.getByLabel("Speech to text device")).toHaveCount(0);
  await expect(page.getByLabel("Text to speech device")).toHaveCount(0);
});

test("submits audio formats for service-side validation", async ({ page }) => {
  await page.route("**/voice/transcriptions", async (route) => {
    const body = route.request().postData() ?? "";
    expect(body).toContain('filename="sample.mp3"');
    expect(body).toContain("Content-Type: audio/mpeg");
    await route.fulfill({ json: { text: "Service accepted audio" } });
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
  await page.route("**/voice/transcriptions", (route) =>
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
    await expect(sttMetrics).toContainText("Awaiting conversion");
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
    await page.route("**/voice/transcriptions", async (route) => {
      expect(route.request().headers()["content-type"]).toContain(
        "multipart/form-data",
      );
      expect(route.request().postData()).not.toContain("session_id");
      await route.fulfill({
        json: { text: "Hello world" },
        headers: { "X-Voice-Service-Duration-Ms": "250.000" },
      });
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
    await expect(
      page.getByRole("region", { name: "Text to speech metrics" }),
    ).toContainText("Awaiting conversion");
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
    await chooseOption(page, "Voice", "Angus");
    const textInput = page.getByLabel("Text input (English)");
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
    await expect(page.getByLabel("Text input (English)")).toHaveCSS(
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
    await expect(page.getByLabel("Text input (English)")).toHaveValue(
      "Hello world",
    );
    await expect(page.getByLabel("Generated speech")).toHaveCount(0);
    await expect(
      page.getByRole("region", { name: "Text to speech metrics" }),
    ).toContainText("Awaiting conversion");
    await chooseOption(
      page,
      "Sample text",
      "Welcome to Intel Performance Studio.",
    );
    await expect(page.getByLabel("Text input (English)")).toHaveValue(
      "Welcome to Intel Performance Studio.",
    );
    await expect(page.getByLabel("Generated speech")).toHaveCount(0);
    await expect(
      page.getByRole("region", { name: "Text to speech metrics" }),
    ).toContainText("Awaiting conversion");
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
  await page.getByLabel("Text input (English)").fill("Hello world");
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
  await page.getByLabel("Text input (English)").fill("Hello world");
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
  await expect(metrics).toContainText("Conversion failed");
  let release: (() => void) | undefined;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  await mockTtsJob(page, { serviceMs: 900, waitForStart: pending });
  await page.getByRole("button", { name: "Generate speech" }).click();
  await expect(
    page.getByRole("button", { name: "Cancel", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Generate speech" }),
  ).toBeEnabled();
  await expect(page.getByLabel("Generated speech")).toHaveCount(0);
  await expect(metrics).toContainText("Awaiting conversion");
  await mockTtsJob(page, { serviceMs: 700 });
  await page.getByRole("button", { name: "Generate speech" }).click();
  await expect(metrics).toContainText("700.00ms");
  release?.();
  await expect(metrics).not.toContainText("900.00ms");
});

test("missing or zero service timing does not break conversion", async ({
  page,
}) => {
  await page.goto(
    new URL("/pipelines/audio/text-to-speech/cpu", page.url()).toString(),
  );
  await page.getByLabel("Text input (English)").fill("Hello world");
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
  await chooseOption(page, "Sample text", "Your audio is ready for playback.");
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
