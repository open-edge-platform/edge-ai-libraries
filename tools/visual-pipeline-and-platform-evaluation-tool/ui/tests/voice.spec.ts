// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { expect, test } from "@playwright/test";

function wav(): Buffer {
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
    await page.route("**/voice/transcriptions", async (route) => {
      expect(route.request().headers()["content-type"]).toContain(
        "multipart/form-data",
      );
      expect(route.request().postData()).not.toContain("session_id");
      await route.fulfill({ json: { text: "Hello world" } });
    });
    await page.route("**/voice/speech", async (route) => {
      expect(route.request().postDataJSON()).toEqual({ input: "Hello world" });
      await route.fulfill({ contentType: "audio/wav", body: wav() });
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
    await page.screenshot({
      path: `/tmp/voice-stt-${viewport.width}.png`,
      fullPage: true,
    });
    await page.getByRole("tab", { name: "Text to speech" }).click();
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
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `/tmp/voice-tts-${viewport.width}.png`,
      fullPage: true,
    });
  });
}

test("service failure and cancellation", async ({ page }) => {
  await page.getByRole("tab", { name: "Text to speech" }).click();
  await page.getByLabel("Text input (English)").fill("Hello world");
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
  let release: (() => void) | undefined;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/voice/speech", async (route) => {
    await pending;
    await route
      .fulfill({ contentType: "audio/wav", body: wav() })
      .catch(() => { });
  });
  await page.getByRole("button", { name: "Generate speech" }).click();
  await expect(
    page.getByRole("button", { name: "Cancel", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  release?.();
  await expect(
    page.getByRole("button", { name: "Generate speech" }),
  ).toBeEnabled();
  await expect(page.getByLabel("Generated speech")).toHaveCount(0);
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
