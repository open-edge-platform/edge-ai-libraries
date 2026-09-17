// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { expect, test } from "@playwright/test";
import { Buffer } from "node:buffer";
import process from "node:process";

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

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.includes("/voice/")) return route.fallback();
    const body =
      path.endsWith("/status") || path.endsWith("/health")
        ? { status: "ready" }
        : [];
    await route.fulfill({ json: body });
  });
  await page.route("**/metrics/stream", (route) =>
    route.fulfill({ contentType: "text/event-stream", body: ": ready\n\n" }),
  );
  await page.goto(process.env.VOICE_UI_URL ?? "http://127.0.0.1:5173/voice");
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
    await page.route("**/voice/speech", async (route) => {
      expect(route.request().postDataJSON()).toEqual({ input: "Hello world" });
      await route.fulfill({
        contentType: "audio/wav",
        body: wav(),
        headers: { "X-Voice-Service-Duration-Ms": "750.000" },
      });
    });
    await expect(
      page.getByRole("button", { name: "Transcribe", exact: true }),
    ).toBeDisabled();
    await page.getByLabel("WAV file").setInputFiles({
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
    const sttMetrics = page.getByRole("region", {
      name: "Speech to text metrics",
    });
    await expect(sttMetrics).toContainText("250.00ms");
    const requestDuration = sttMetrics
      .getByRole("heading", { name: "Request duration" })
      .locator("..")
      .locator("p");
    await expect(requestDuration).toHaveText(/^\d+\.\d{2}ms$/);
    expect(
      Number.parseFloat((await requestDuration.textContent())!),
    ).toBeGreaterThan(0);
    await sttMetrics.scrollIntoViewIfNeeded();
    await page.screenshot({
      path: `/tmp/voice-stt-${viewport.width}.png`,
      fullPage: true,
    });
    await page.getByRole("tab", { name: "Text to speech" }).click();
    await expect(
      page.getByRole("region", { name: "Text to speech metrics" }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "Generate speech" }),
    ).toBeDisabled();
    await page.getByLabel("Text input (English)").fill("Hello world");
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
    await page
      .getByLabel("Sample text")
      .selectOption("Welcome to Intel Performance Studio.");
    await expect(page.getByLabel("Text input (English)")).toHaveValue(
      "Welcome to Intel Performance Studio.",
    );
    await expect(page.getByLabel("Generated speech")).toHaveCount(0);
    await expect(
      page.getByRole("region", { name: "Text to speech metrics" }),
    ).toHaveCount(0);
    await page.getByRole("tab", { name: "Speech to text" }).click();
    await expect(sttMetrics).toContainText("250.00ms");
    await page.getByLabel("Recognition language").selectOption("pl");
    await expect(sttMetrics).toHaveCount(0);
    await page.getByRole("button", { name: "Transcribe", exact: true }).click();
    await expect(sttMetrics).toContainText("250.00ms");
    await page.getByLabel("WAV file").setInputFiles({
      name: "another.wav",
      mimeType: "audio/wav",
      buffer: wav(),
    });
    await expect(sttMetrics).toHaveCount(0);
    await page
      .getByText("Platform metrics (system-wide)", { exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "CPU Usage", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: /Frame Rate|Latency/ }),
    ).toHaveCount(0);
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
  await page.getByRole("tab", { name: "Text to speech" }).click();
  await page.getByLabel("Text input (English)").fill("Hello world");
  for (const volume of [0.01, 1, 0]) {
    const content = wav(volume);
    await page.route("**/voice/speech", (route) =>
      route.fulfill({ contentType: "audio/wav", body: content }),
    );
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
  await page.getByRole("tab", { name: "Text to speech" }).click();
  await page.getByLabel("Text input (English)").fill("Hello world");
  const metrics = page.getByRole("region", { name: "Text to speech metrics" });
  await page.route("**/voice/speech", (route) =>
    route.fulfill({
      contentType: "audio/wav",
      body: wav(),
      headers: { "X-Voice-Service-Duration-Ms": "250.000" },
    }),
  );
  await page.getByRole("button", { name: "Generate speech" }).click();
  await expect(metrics).toContainText("250.00ms");
  await page.route("**/voice/speech", (route) =>
    route.fulfill({
      status: 503,
      json: { detail: "The speech service is unavailable." },
    }),
  );
  await page.getByRole("button", { name: "Generate speech" }).click();
  await expect(page.getByRole("alert")).toHaveText(
    "The speech service is unavailable.",
  );
  await expect(metrics).toHaveCount(0);
  let release: (() => void) | undefined;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/voice/speech", async (route) => {
    await pending;
    await route
      .fulfill({
        contentType: "audio/wav",
        body: wav(),
        headers: { "X-Voice-Service-Duration-Ms": "900.000" },
      })
      .catch(() => { });
  });
  await page.getByRole("button", { name: "Generate speech" }).click();
  await expect(
    page.getByRole("button", { name: "Cancel", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Generate speech" }),
  ).toBeEnabled();
  await expect(page.getByLabel("Generated speech")).toHaveCount(0);
  await expect(metrics).toHaveCount(0);
  await page.route("**/voice/speech", (route) =>
    route.fulfill({
      contentType: "audio/wav",
      body: wav(),
      headers: { "X-Voice-Service-Duration-Ms": "700.000" },
    }),
  );
  await page.getByRole("button", { name: "Generate speech" }).click();
  await expect(metrics).toContainText("700.00ms");
  release?.();
  await expect(metrics).not.toContainText("900.00ms");
});

test("missing or invalid service timing does not break conversion", async ({
  page,
}) => {
  await page.getByRole("tab", { name: "Text to speech" }).click();
  await page.getByLabel("Text input (English)").fill("Hello world");
  for (const value of [
    null,
    "",
    "NaN",
    "Infinity",
    "-1",
    "12ms",
    "0x10",
    "9".repeat(310),
    "0",
  ]) {
    await page.route("**/voice/speech", (route) =>
      route.fulfill({
        contentType: "audio/wav",
        body: wav(),
        headers: value === null ? {} : { "X-Voice-Service-Duration-Ms": value },
      }),
    );
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
    if (value === "0") {
      await expect(metrics).toContainText("0.00ms");
      await expect(
        metrics.getByText("Service round trip unavailable"),
      ).toHaveCount(0);
    } else {
      await expect(
        metrics.getByText("Service round trip unavailable"),
      ).toBeVisible();
      await expect(
        metrics.getByRole("heading", {
          name: "Service round trip",
          exact: true,
        }),
      ).toHaveCount(0);
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
  await page.reload();
  await page.getByRole("tab", { name: "Text to speech" }).click();
  await page
    .getByLabel("Sample text")
    .selectOption("Your audio is ready for playback.");
  await page.route("**/voice/speech", (route) =>
    route.fulfill({
      contentType: "audio/wav",
      body: wav(),
      headers: { "X-Voice-Service-Duration-Ms": "120.000" },
    }),
  );
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
