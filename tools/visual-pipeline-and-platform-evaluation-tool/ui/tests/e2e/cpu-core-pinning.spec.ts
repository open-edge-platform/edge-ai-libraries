// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { expect, test, type Page } from "@playwright/test";
import {
  buildCpuDevice,
  buildPipeline,
  buildVariant,
  buildVideo,
  fulfillJson,
  linearGraph,
  mockApi,
  type CpuCoreType,
} from "./fixtures/api";

const PIPELINE_ID = "pinning-pipeline";
const EDITOR_URL = `/pipelines/vision/${PIPELINE_ID}/cpu`;

const HYBRID_CORES: Array<{ cpu: number; core_type: CpuCoreType }> = [
  ...[0, 1, 2, 3].map((cpu) => ({ cpu, core_type: "P" as const })),
  ...[4, 5, 6, 7].map((cpu) => ({ cpu, core_type: "E" as const })),
  ...[8, 9].map((cpu) => ({ cpu, core_type: "LPE" as const })),
];

const setup = async (
  page: Page,
  {
    cores = HYBRID_CORES,
    mediaOnly = false,
    savedPinning = [],
  }: {
    cores?: typeof HYBRID_CORES | null;
    mediaOnly?: boolean;
    savedPinning?: number[];
  } = {},
) => {
  const graph = { ...linearGraph("traffic.mp4"), cpu_pinning: savedPinning };
  return mockApi(page, {
    devices: [buildCpuDevice(cores)],
    videos: [buildVideo("traffic.mp4")],
    pipelines: [
      buildPipeline({
        id: PIPELINE_ID,
        name: "Pinning pipeline",
        variants: [
          buildVariant({ pipeline_graph: graph, media_only: mediaOnly }),
        ],
      }),
    ],
  });
};

const pinButton = (page: Page) =>
  page.getByRole("button", { name: "CPU core pinning" });

const enableAdvancedMode = async (page: Page) => {
  await page.getByRole("button", { name: "Pipeline options" }).click();
  await page.getByRole("switch", { name: /Enable advanced mode/i }).click();
  await expect(
    page.getByRole("switch", { name: /Enable advanced mode/i }),
  ).toBeChecked();
  await page.keyboard.press("Escape");
};

const openPinningDialog = async (page: Page) => {
  await pinButton(page).click();
  const dialog = page.getByRole("dialog", { name: "CPU core pinning" });
  await expect(dialog).toBeVisible();
  return dialog;
};

test.describe("CPU core pinning", () => {
  test("is not available in simple mode", async ({ page }) => {
    await setup(page);
    await page.goto(EDITOR_URL);

    await expect(pinButton(page)).toHaveAttribute("aria-disabled", "true");
    // aria-disabled keeps the button clickable, so the guard lives in the handler.
    await pinButton(page).click({ force: true });
    await expect(page.getByRole("dialog")).toHaveCount(0);
  });

  test("groups cores by type and blocks an LPE-only selection", async ({
    page,
  }) => {
    await setup(page);
    await page.goto(EDITOR_URL);
    await enableAdvancedMode(page);

    const dialog = await openPinningDialog(page);

    await expect(dialog.getByText("Performance cores (P)")).toBeVisible();
    await expect(dialog.getByText("Efficient cores (E)")).toBeVisible();
    await expect(
      dialog.getByText("Low-power efficient cores (LPE)"),
    ).toBeVisible();
    await expect(
      dialog.getByText("No cores selected - all cores will be used."),
    ).toBeVisible();

    await dialog
      .getByRole("checkbox", {
        name: "Select all Low-power efficient cores (LPE)",
      })
      .click();

    await expect(
      dialog.getByText(/Only low-power efficient cores/),
    ).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Apply" })).toBeDisabled();

    await dialog.getByRole("checkbox", { name: "CPU 0", exact: true }).click();

    await expect(
      dialog.getByText(/Only low-power efficient cores/),
    ).toHaveCount(0);
    await expect(
      dialog.getByText("Selected 3 of 10 cores: 0,8-9"),
    ).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Apply" })).toBeEnabled();
  });

  test("selecting a whole group and Clear / Cancel keep the draft local", async ({
    page,
  }) => {
    await setup(page);
    await page.goto(EDITOR_URL);
    await enableAdvancedMode(page);

    let dialog = await openPinningDialog(page);
    await dialog
      .getByRole("checkbox", { name: "Select all Performance cores (P)" })
      .click();
    await expect(dialog.getByText("4 / 4 selected")).toBeVisible();
    await expect(dialog.getByText("Selected 4 of 10 cores: 0-3")).toBeVisible();

    await dialog.getByRole("button", { name: "Clear" }).click();
    await expect(
      dialog.getByText("No cores selected - all cores will be used."),
    ).toBeVisible();

    await dialog.getByRole("checkbox", { name: "CPU 5", exact: true }).click();
    await dialog.getByRole("button", { name: "Cancel" }).click();
    await expect(dialog).toBeHidden();

    await expect(
      page.getByRole("button", { name: "Save", exact: true }),
    ).toBeDisabled();

    dialog = await openPinningDialog(page);
    await expect(
      dialog.getByText("No cores selected - all cores will be used."),
    ).toBeVisible();
  });

  test("applied pinning is saved with the variant graph", async ({ page }) => {
    const state = await setup(page);
    await page.goto(EDITOR_URL);
    await enableAdvancedMode(page);

    const dialog = await openPinningDialog(page);
    await dialog.getByRole("checkbox", { name: "CPU 1", exact: true }).click();
    await dialog.getByRole("checkbox", { name: "CPU 4", exact: true }).click();
    await dialog.getByRole("button", { name: "Apply" }).click();
    await expect(dialog).toBeHidden();

    const saveButton = page.getByRole("button", { name: "Save", exact: true });
    await expect(saveButton).toBeEnabled();

    const saveRequest = page.waitForRequest(
      (request) =>
        request.method() === "PATCH" &&
        request.url().endsWith(`/pipelines/${PIPELINE_ID}/variants/cpu`),
    );
    await saveButton.click();

    expect((await saveRequest).postDataJSON()).toMatchObject({
      pipeline_graph: { cpu_pinning: [1, 4] },
    });
    await expect(saveButton).toBeDisabled();
    expect(state.pipelines[0].variants[0].pipeline_graph.cpu_pinning).toEqual([
      1, 4,
    ]);
  });

  test("restores saved pinning and sends it with a pipeline run", async ({
    page,
  }) => {
    await setup(page, { savedPinning: [2, 3] });
    await page.route("**/api/v1/tests/performance", (route) =>
      fulfillJson(route, { job_id: "job-1" }, 202),
    );
    await page.route("**/api/v1/jobs/tests/performance/job-1/status", (route) =>
      fulfillJson(route, {
        id: "job-1",
        start_time: Date.now(),
        elapsed_time: 1,
        state: "COMPLETED",
        details: [],
        total_fps: 30,
        per_stream_fps: 30,
        total_streams: 1,
        streams_per_pipeline: null,
        video_output_paths: null,
        live_stream_urls: null,
        metadata_stream_urls: null,
      }),
    );

    await page.goto(EDITOR_URL);
    await enableAdvancedMode(page);

    const dialog = await openPinningDialog(page);
    await expect(
      dialog.getByRole("checkbox", { name: "CPU 2", exact: true }),
    ).toBeChecked();
    await expect(dialog.getByText("Selected 2 of 10 cores: 2-3")).toBeVisible();
    await dialog.getByRole("button", { name: "Cancel" }).click();

    const runRequest = page.waitForRequest(
      (request) =>
        request.method() === "POST" &&
        request.url().endsWith("/api/v1/tests/performance"),
    );
    await page.getByRole("button", { name: "Run pipeline" }).click();

    const body = (await runRequest).postDataJSON();
    expect(body.execution_config.pinned_cpu_cores).toEqual([2, 3]);
    expect(
      body.pipeline_performance_specs[0].pipeline.pipeline_graph.cpu_pinning,
    ).toEqual([2, 3]);
  });

  test("media-only pipelines may run on LPE cores alone", async ({ page }) => {
    await setup(page, { mediaOnly: true });
    await page.goto(EDITOR_URL);
    await enableAdvancedMode(page);

    const dialog = await openPinningDialog(page);
    await dialog
      .getByRole("checkbox", {
        name: "Select all Low-power efficient cores (LPE)",
      })
      .click();

    await expect(
      dialog.getByText(/Only low-power efficient cores/),
    ).toHaveCount(0);
    await expect(dialog.getByRole("button", { name: "Apply" })).toBeEnabled();
  });

  test("explains when the CPU topology is unknown", async ({ page }) => {
    await setup(page, { cores: null });
    await page.goto(EDITOR_URL);
    await enableAdvancedMode(page);

    const dialog = await openPinningDialog(page);
    await expect(
      dialog.getByText(/CPU core types are not available on this system/),
    ).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Apply" })).toBeDisabled();
    await expect(dialog.getByRole("button", { name: "Clear" })).toBeDisabled();
  });
});
