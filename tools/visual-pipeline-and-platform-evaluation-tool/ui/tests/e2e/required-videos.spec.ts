// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { expect, test } from "@playwright/test";
import {
  buildDefaultRecording,
  buildPipeline,
  buildVariant,
  buildVideo,
  fulfillJson,
  linearGraph,
  mockApi,
} from "./fixtures/api";

const PIPELINE_ID = "video-pipeline";
const EDITOR_URL = `/pipelines/vision/${PIPELINE_ID}/cpu`;

const pipelineReading = (location: string) =>
  buildPipeline({
    id: PIPELINE_ID,
    name: "Video pipeline",
    variants: [buildVariant({ pipeline_graph: linearGraph(location) })],
  });

test.describe("Pipeline editor - required input videos", () => {
  test("offers to download a missing sample video and unlocks the run", async ({
    page,
  }) => {
    const state = await mockApi(page, {
      pipelines: [pipelineReading("traffic.mp4")],
      defaultRecordings: [buildDefaultRecording("traffic.mp4")],
    });
    await page.route("**/api/v1/videos/download-default", (route) => {
      state.defaultRecordings[0].status = "downloading";
      return fulfillJson(
        route,
        { filename: "traffic.mp4", status: "queued" },
        202,
      );
    });

    await page.goto(EDITOR_URL);

    // The title falls back to the models text once no video is missing.
    const dialog = page.getByRole("dialog");
    await expect(
      dialog.getByRole("heading", { name: "Required videos are missing" }),
    ).toBeVisible();
    await expect(dialog.getByText("traffic.mp4")).toBeVisible();
    await expect(
      dialog.getByText("Not Downloaded", { exact: true }),
    ).toBeVisible();

    const downloadRequest = page.waitForRequest("**/videos/download-default");
    await dialog.getByRole("button", { name: "Download" }).click();
    expect((await downloadRequest).postDataJSON()).toEqual({
      filename: "traffic.mp4",
    });
    await expect(
      dialog.getByText("Downloading", { exact: true }),
    ).toBeVisible();

    state.defaultRecordings[0].status = "downloaded";
    state.videos.push(buildVideo("traffic.mp4"));

    await expect(page.getByText("Video traffic.mp4 downloaded")).toBeVisible();
    await expect(dialog.getByText("Downloaded", { exact: true })).toBeVisible();

    await dialog.getByRole("button", { name: "Continue" }).click();
    await expect(dialog).toBeHidden();
    await expect(
      page.getByRole("button", { name: "Run pipeline" }),
    ).toBeEnabled();
  });

  test("points to the Videos page when the video is not a sample", async ({
    page,
  }) => {
    await mockApi(page, { pipelines: [pipelineReading("my-recording.mp4")] });

    await page.goto(EDITOR_URL);

    const dialog = page.getByRole("dialog", {
      name: "Required videos are missing",
    });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText("my-recording.mp4")).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Download" })).toHaveCount(
      0,
    );
    await expect(
      dialog.getByRole("link", { name: "Videos page" }),
    ).toHaveAttribute("href", "/videos");

    await dialog.getByRole("button", { name: "Continue" }).click();
    await expect(
      page.getByRole("button", { name: "Run pipeline" }),
    ).toBeDisabled();
  });

  test("does not prompt when the input video is already available", async ({
    page,
  }) => {
    await mockApi(page, {
      pipelines: [pipelineReading("traffic.mp4")],
      videos: [buildVideo("traffic.mp4")],
      defaultRecordings: [
        buildDefaultRecording("traffic.mp4", { status: "downloaded" }),
      ],
    });

    await page.goto(EDITOR_URL);

    await expect(
      page.getByRole("button", { name: "Run pipeline" }),
    ).toBeEnabled();
    await expect(page.getByRole("dialog")).toHaveCount(0);
  });
});
