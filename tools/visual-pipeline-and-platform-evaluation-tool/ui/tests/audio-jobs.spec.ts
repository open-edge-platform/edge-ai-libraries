// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { expect, test } from "@playwright/test";

const completedSttJob = {
    id: "job-stt",
    pipeline_id: "speech-to-text",
    pipeline_name: "Speech to Text",
    operation: "speech_to_text",
    variant_id: "npu",
    variant_name: "NPU",
    device: "NPU",
    state: "COMPLETED",
    created_at: "2026-10-13T12:30:00Z",
    modified_at: "2026-10-13T12:30:02Z",
    service_round_trip_ms: 1250.25,
    artifact_available: false,
    error: null,
};

const completedTtsJob = {
    id: "job-tts",
    pipeline_id: "text-to-speech",
    pipeline_name: "Text to Speech",
    operation: "text_to_speech",
    variant_id: "gpu",
    variant_name: "GPU",
    device: "GPU",
    state: "COMPLETED",
    created_at: "2026-10-13T12:35:00Z",
    modified_at: "2026-10-13T12:35:01Z",
    service_round_trip_ms: 875.5,
    artifact_available: true,
    error: null,
};

test("lists Audio jobs without transcript content or stop actions", async ({
    page,
}) => {
    await page.route("**/api/v1/jobs/audio/status", (route) =>
        route.fulfill({
            json: [completedSttJob, completedTtsJob],
        }),
    );

    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/jobs/audio");

    await expect(page.getByRole("link", { name: "Audio" })).toHaveAttribute(
        "aria-current",
        "page",
    );
    await expect(
        page.getByRole("row").filter({ hasText: "job-stt" }),
    ).toContainText("Speech to Text");
    await expect(page.getByRole("row").nth(1)).toContainText("job-stt");
    await expect(page.getByRole("row").nth(2)).toContainText("job-tts");
    await expect(page.getByText("private transcript")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Stop" })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "View" })).toHaveCount(2);
    expect(
        await page.evaluate(
            () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
    ).toBe(true);

    await page.setViewportSize({ width: 390, height: 844 });
    await page.reload();
    const audioTab = page.getByRole("link", { name: "Audio" });
    await expect(audioTab).toBeVisible();
    await expect
        .poll(() =>
            audioTab.evaluate((element) => {
                const bounds = element.getBoundingClientRect();
                return bounds.left >= 0 && bounds.right <= window.innerWidth;
            }),
        )
        .toBe(true);
    expect(
        await page.evaluate(
            () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
    ).toBe(true);
});

test("stops an active Audio job from the jobs list", async ({ page }) => {
    const runningJob = {
        ...completedTtsJob,
        id: "job-running",
        state: "RUNNING",
        artifact_available: false,
        service_round_trip_ms: null,
    };
    const stopRequests: string[] = [];
    let stopped = false;
    await page.route("**/api/v1/jobs/audio/status", (route) =>
        route.fulfill({
            json: [
                completedSttJob,
                stopped ? { ...runningJob, state: "CANCELLED" } : runningJob,
            ],
        }),
    );
    await page.route("**/api/v1/jobs/audio/job-running", (route) => {
        stopRequests.push(
            `${route.request().method()} ${new URL(route.request().url()).pathname}`,
        );
        stopped = true;
        return route.fulfill({ json: { message: "Job job-running stopped" } });
    });

    await page.goto("/jobs/audio");

    await expect(page.getByRole("button", { name: "Stop" })).toHaveCount(1);
    expect(stopRequests).toEqual([]);

    await page.getByRole("button", { name: "Stop" }).click();

    await expect
        .poll(() => stopRequests)
        .toEqual(["DELETE /api/v1/jobs/audio/job-running"]);
    await expect(
        page.getByRole("row").filter({ hasText: "job-running" }),
    ).toContainText("CANCELLED");
    await expect(page.getByRole("button", { name: "Stop" })).toHaveCount(0);
});

test("shows Audio jobs loading and empty states", async ({ page }) => {
    let releaseRequest: (() => void) | undefined;
    const requestReleased = new Promise<void>((resolve) => {
        releaseRequest = resolve;
    });
    await page.route("**/api/v1/jobs/audio/status", async (route) => {
        await requestReleased;
        await route.fulfill({ json: [] });
    });

    await page.goto("/jobs/audio");
    await expect(page.getByText("Loading jobs...")).toBeVisible();
    releaseRequest?.();
    await expect(page.getByText("No audio jobs found")).toBeVisible();
});

test("shows STT job details and stops polling terminal jobs", async ({
    page,
}) => {
    let statusRequests = 0;
    await page.route("**/api/v1/jobs/audio/job-stt/status", (route) => {
        statusRequests += 1;
        return route.fulfill({
            json: { ...completedSttJob, transcript: "private transcript" },
        });
    });

    await page.goto("/jobs/audio/job-stt");

    await expect(
        page.getByRole("heading", { name: "Audio Job Details" }),
    ).toBeVisible();
    await expect(
        page.getByText("Speech to Text", { exact: true }).first(),
    ).toBeVisible();
    await expect(page.getByText("NPU", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("COMPLETED", { exact: true })).toBeVisible();
    await expect(page.getByText("private transcript")).toBeVisible();
    await expect(
        page.getByRole("link", { name: "Back to Audio Jobs" }),
    ).toHaveAttribute("href", "/jobs/audio");
    await page.waitForTimeout(2200);
    expect(statusRequests).toBe(1);
});

test("shows a downloadable WAV artifact for a TTS job", async ({ page }) => {
    await page.route("**/api/v1/jobs/audio/job-tts/status", (route) =>
        route.fulfill({
            json: {
                ...completedTtsJob,
                transcript: null,
                artifact_url: "/api/v1/voice/jobs/job-tts/artifact",
            },
        }),
    );
    await page.route("**/api/v1/voice/jobs/job-tts/artifact", (route) =>
        route.fulfill({
            headers: {
                "Content-Type": "audio/wav",
                "Content-Disposition": 'attachment; filename="speech.wav"',
            },
            body: Buffer.from("RIFF0000WAVE"),
        }),
    );

    await page.goto("/jobs/audio/job-tts");
    const downloadLink = page.getByRole("link", { name: "Download WAV" });
    await expect(downloadLink).toHaveAttribute(
        "href",
        "/api/v1/voice/jobs/job-tts/artifact",
    );
    await expect(downloadLink).toHaveAttribute("download", "");
});
