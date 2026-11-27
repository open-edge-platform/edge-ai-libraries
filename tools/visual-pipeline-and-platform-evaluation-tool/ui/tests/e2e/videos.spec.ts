// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { expect, test, type Page } from "@playwright/test";
import {
  buildDefaultRecording,
  buildVideo,
  fulfillJson,
  mockApi,
} from "./fixtures/api";

const HEVC_UNSUPPORTED_MESSAGE =
  "HEVC conversion needs an Intel GPU; start ViPPET with a GPU profile to enable it.";

const sampleRow = (page: Page, filename: string) =>
  page.getByRole("row").filter({ hasText: filename });

test.describe("Videos page - sample videos", () => {
  test("shows the status of every sample and uploaded video", async ({
    page,
  }) => {
    await mockApi(page, {
      videos: [
        buildVideo("downloaded.mp4", { width: 1280, height: 720 }),
        buildVideo("my-upload.mp4", { source: "uploaded" }),
      ],
      defaultRecordings: [
        buildDefaultRecording("available.mp4"),
        buildDefaultRecording("downloaded.mp4", {
          status: "downloaded",
          conversion_status: "unsupported",
        }),
        buildDefaultRecording("conflict.mp4", { status: "conflict" }),
        buildDefaultRecording("failed.mp4", { status: "failed" }),
      ],
    });

    await page.goto("/videos");

    // Only samples that are neither downloaded nor conflicting are bulk-downloadable.
    await expect(
      page.getByRole("button", { name: "Download all videos (2)" }),
    ).toBeEnabled();

    await expect(
      sampleRow(page, "available.mp4").getByRole("button", {
        name: "Download",
      }),
    ).toBeVisible();

    const downloaded = sampleRow(page, "downloaded.mp4");
    await expect(
      downloaded.getByRole("link", { name: "downloaded.mp4" }),
    ).toHaveAttribute("href", "/assets/videos/input/downloaded.mp4");
    await expect(downloaded.getByText("1280x720")).toBeVisible();
    await expect(
      downloaded.getByText("Downloaded", { exact: true }),
    ).toBeVisible();
    await expect(downloaded.getByText("HEVC unsupported")).toBeVisible();

    await expect(
      sampleRow(page, "conflict.mp4").getByText("Name conflict"),
    ).toBeVisible();
    await expect(
      sampleRow(page, "failed.mp4").getByRole("button", { name: "Retry" }),
    ).toBeVisible();
    await expect(
      sampleRow(page, "my-upload.mp4").getByText("Uploaded"),
    ).toBeVisible();
  });

  test("downloads a sample and starts the HEVC conversion afterwards", async ({
    page,
  }) => {
    const state = await mockApi(page, {
      defaultRecordings: [buildDefaultRecording("street.mp4")],
    });
    await page.route("**/api/v1/videos/download-default", (route) => {
      state.defaultRecordings[0].status = "downloading";
      return fulfillJson(
        route,
        { filename: "street.mp4", status: "queued" },
        202,
      );
    });
    await page.route("**/api/v1/videos/convert-hevc", (route) => {
      state.defaultRecordings[0].conversion_status = "unsupported";
      return fulfillJson(route, {
        filename: "street.mp4",
        hevc_filename: "street_h265.mp4",
        status: "unsupported",
      });
    });

    await page.goto("/videos");

    const row = sampleRow(page, "street.mp4");
    const downloadRequest = page.waitForRequest("**/videos/download-default");
    await row.getByRole("button", { name: "Download" }).click();

    expect((await downloadRequest).postDataJSON()).toEqual({
      filename: "street.mp4",
    });
    await expect(
      page.getByText("Sample video download started."),
    ).toBeVisible();
    await expect(row.getByText("Downloading", { exact: true })).toBeVisible();

    const conversionRequest = page.waitForRequest("**/videos/convert-hevc");
    state.defaultRecordings[0].status = "downloaded";
    state.videos.push(buildVideo("street.mp4"));

    expect((await conversionRequest).postDataJSON()).toEqual({
      filename: "street.mp4",
    });
    await expect(
      page.getByText("Sample video download completed."),
    ).toBeVisible();
    await expect(page.getByText(HEVC_UNSUPPORTED_MESSAGE)).toBeVisible();
    await expect(row.getByText("Downloaded", { exact: true })).toBeVisible();
    await expect(row.getByText("1920x1080")).toBeVisible();
  });

  test("reports a failed download and allows a retry", async ({ page }) => {
    const state = await mockApi(page, {
      defaultRecordings: [buildDefaultRecording("street.mp4")],
    });
    await page.route("**/api/v1/videos/download-default", (route) => {
      state.defaultRecordings[0].status = "downloading";
      return fulfillJson(
        route,
        { filename: "street.mp4", status: "queued" },
        202,
      );
    });

    await page.goto("/videos");

    const row = sampleRow(page, "street.mp4");
    await row.getByRole("button", { name: "Download" }).click();
    await expect(row.getByText("Downloading", { exact: true })).toBeVisible();

    state.defaultRecordings[0].status = "failed";

    await expect(
      page.getByText("Could not download 1 sample video(s)."),
    ).toBeVisible();
    await expect(row.getByRole("button", { name: "Retry" })).toBeVisible();
  });

  test("shows an error when the download cannot be started", async ({
    page,
  }) => {
    await mockApi(page, {
      defaultRecordings: [buildDefaultRecording("street.mp4")],
    });
    await page.route("**/api/v1/videos/download-default", (route) =>
      fulfillJson(route, { detail: "Storage is full" }, 500),
    );

    await page.goto("/videos");

    const row = sampleRow(page, "street.mp4");
    await row.getByRole("button", { name: "Download" }).click();

    await expect(
      page.getByText("Could not start the sample video download."),
    ).toBeVisible();
    await expect(row.getByRole("button", { name: "Download" })).toBeVisible();
  });
});
