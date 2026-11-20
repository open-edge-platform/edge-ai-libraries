// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { expect, test, type Page } from "@playwright/test";
import type {
  DensityTestSpec,
  PipelineGraph,
} from "../../src/api/api.generated";

const graph = (
  decoder: string,
  caps = "",
  pinning: number[] = [],
): PipelineGraph => ({
  cpu_pinning: pinning,
  nodes: [
    { id: "0", type: "filesrc", data: { location: "people.mp4" } },
    { id: "1", type: decoder, data: caps ? { caps } : {} },
    { id: "2", type: "fakesink", data: { name: "default_output_sink" } },
  ],
  edges: [
    { id: "0", source: "0", target: "1" },
    { id: "1", source: "1", target: "2" },
  ],
});

const setup = async (
  page: Page,
  extraVideos = 0,
  missing?: "pipeline" | "hardware" | "cpu",
  isComplete = () => true,
) => {
  let submitted: DensityTestSpec | undefined;
  const timestamp = new Date().toISOString();
  const pipeline = {
    id: "media-decode",
    name: "Media Decode",
    type: "vision",
    source: "PREDEFINED",
    tags: [],
    description: "Media decode",
    created_at: timestamp,
    modified_at: timestamp,
    variants: [
      ["vdbox", "VDBox", graph("decodebin3", '"video/x-raw(memory:VAMemory)"')],
      ["cpu-h264", "CPU H264", graph("avdec_h264")],
      ["cpu-h265", "CPU H265", graph("avdec_h265", "", [12, 13])],
    ].map(([id, name, pipelineGraph]) => ({
      id,
      name,
      read_only: true,
      pipeline_graph: pipelineGraph,
      pipeline_graph_simple: pipelineGraph,
      created_at: timestamp,
      modified_at: timestamp,
    })),
  };
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let response: unknown = [];
    if (path === "/api/v1/devices") {
      response = [
        {
          device_name: "CPU",
          device_family: "CPU",
          cpu_topology: {
            source: "sysfs_cache",
            is_hybrid: true,
            cores: [0, 12, 13, 14, 15].map((cpu) => ({
              cpu,
              core_id: cpu,
              core_type: cpu === 0 ? "P" : "LPE",
            })),
          },
        },
      ];
    }
    if (path === "/api/v1/pipelines")
      response = [
        ...(missing === "pipeline"
          ? []
          : [
              {
                ...pipeline,
                variants: pipeline.variants.filter((variant) =>
                  missing === "hardware"
                    ? variant.id !== "vdbox"
                    : missing === "cpu"
                      ? variant.id !== "cpu-h265"
                      : true,
                ),
              },
            ]),
        {
          ...pipeline,
          id: "other-media",
          name: "Other Media",
          source: "USER_CREATED",
        },
      ];
    if (path === "/api/v1/videos")
      response = [
        ...Array.from({ length: extraVideos }, (_, index) => `clip-${index}`),
        "h264",
        "h265",
      ].map((name) => ({
        filename: `${name}.mp4`,
        width: 1920,
        height: 1080,
        fps: 30,
        frame_count: 302,
        duration: 10,
        codec: name === "h265" ? "h265" : "h264",
        path: `uploaded/${name}.mp4`,
        source: "uploaded",
      }));
    if (path === "/api/v1/tests/density") {
      submitted = route.request().postDataJSON() as DensityTestSpec;
      await route.fulfill({ status: 202, json: { job_id: "hybrid-test" } });
      return;
    }
    if (path === "/api/v1/jobs/tests/density/hybrid-test/status") {
      const now = Date.now();
      response = {
        id: "hybrid-test",
        state: isComplete() ? "COMPLETED" : "RUNNING",
        start_time: now - 10000,
        elapsed_time: 10000,
        details: [],
        total_streams: 5,
        per_stream_fps: 31,
        min_stream_fps: 30,
        selected_trial: 1,
        trials: [
          {
            index: 0,
            stage: "vdbox",
            streams_per_pipeline: { "hybrid-vdbox": 3 },
            min_stream_fps: 31,
            passed: true,
          },
          {
            index: 1,
            stage: "cpu",
            streams_per_pipeline: { "hybrid-vdbox": 3, "hybrid-cpu": 2 },
            min_stream_fps: 30,
            passed: true,
          },
          {
            index: 2,
            stage: "cpu",
            streams_per_pipeline: { "hybrid-vdbox": 3, "hybrid-cpu": 3 },
            min_stream_fps: 25,
            passed: false,
          },
          ...Array.from({ length: 6 }, (_, index) => ({
            index: index + 3,
            stage: "cpu",
            streams_per_pipeline: {
              "hybrid-vdbox": 3,
              "hybrid-cpu": index + 4,
            },
            min_stream_fps: 20,
            passed: false,
          })),
        ].map((trial) => ({
          ...trial,
          started_at: now - 10000,
          ended_at: now,
          measurement_started_at: now - 5000,
          measurement_ended_at: now,
        })),
      };
    }
    await route.fulfill({ json: response });
  });
  await page.goto("/tests/density");
  await page.getByRole("tab", { name: "Hybrid Decode" }).click();
  return () => submitted;
};

for (const width of [1100, 390]) {
  test(`shared video source remains stable when scrolling to the last video at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 600 });
    await setup(page, 80);
    const trigger = page.getByRole("combobox", { name: "Video source" });
    await trigger.click();
    const list = page.getByRole("listbox");
    const bounds = await list.boundingBox();
    expect(bounds).not.toBeNull();
    expect(bounds!.height).toBeLessThanOrEqual(300);
    const viewport = list.locator("[data-radix-select-viewport]");
    await viewport.hover();
    await page.mouse.wheel(0, 10000);
    const lastVideo = page.getByRole("option", { name: /h265.mp4/ });
    await lastVideo.hover();
    await expect(lastVideo).toBeInViewport();
    await expect
      .poll(() => viewport.evaluate((element) => element.scrollTop))
      .toBeGreaterThan(0);
    await lastVideo.click();
    await expect(trigger).toContainText("h265.mp4");
    await trigger.click();
    await expect(lastVideo).toBeInViewport();
    await lastVideo.click();
    await expect(trigger).toContainText("h265.mp4");
  });
}

test("HEVC hybrid request preserves pinning and marks the best configuration", async ({
  page,
}) => {
  let completed = false;
  const submission = await setup(page, 0, undefined, () => completed);
  await page.getByRole("combobox", { name: "Video source" }).click();
  await page.getByRole("option", { name: /h265.mp4/ }).click();
  const targetFps = page.getByLabel("Target FPS", { exact: true });
  await targetFps.clear();
  await expect(targetFps).toHaveValue("");
  await expect(
    page.getByRole("button", { name: "Run hybrid decode" }),
  ).toBeDisabled();
  await targetFps.pressSequentially("30");
  await expect(targetFps).toHaveValue("30");
  await expect(page.getByRole("combobox", { name: "Video source" })).toHaveText(
    "h265.mp4 · H.265",
  );
  await expect(
    page.getByText("Video format", { exact: true }).locator("..").locator("dd"),
  ).toHaveText("H.265");
  await expect(
    page
      .getByRole("region", { name: "Hybrid decode test" })
      .getByRole("combobox"),
  ).toHaveCount(1);
  await expect(
    page.getByText("VDBox / decodebin3", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("avdec_h265", { exact: true })).toBeVisible();
  await expect(page.getByText("CPU ids: 12, 13")).toBeVisible();
  await page.getByRole("button", { name: "Select CPU cores" }).click();
  const pinning = page.getByRole("dialog", { name: "CPU core pinning" });
  await pinning.getByRole("checkbox", { name: /Select all Low-power/ }).check();
  await expect(pinning.getByText(/OpenVINO refuses/)).toHaveCount(0);
  await pinning.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByText("CPU ids: 12, 13, 14, 15")).toBeVisible();
  await page.getByRole("button", { name: "Run hybrid decode" }).click();
  const trials = page.getByRole("region", { name: "Measured configurations" });
  await expect(trials).toBeVisible();
  await expect(
    page.getByRole("heading", { name: /^(VDBox|CPU) search$/ }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "Selected configuration" }),
  ).toHaveCount(0);
  await expect(trials.getByText("Best configuration")).toHaveCount(0);
  expect(
    await trials.evaluate(
      (element) => element.scrollHeight > element.clientHeight,
    ),
  ).toBe(true);
  completed = true;
  const selectedHeading = page.getByRole("heading", {
    name: "Selected configuration",
  });
  await expect(selectedHeading).toBeVisible();
  const selectedBounds = await selectedHeading.boundingBox();
  const tableBounds = await trials.boundingBox();
  expect(selectedBounds?.y ?? Infinity).toBeLessThan(tableBounds?.y ?? 0);
  const request = submission();
  expect(request?.execution_config?.max_runtime).toBe(30);
  expect(request?.execution_config?.output_mode).toBe("disabled");
  const specs = request?.pipeline_density_specs ?? [];
  expect(specs).toHaveLength(2);
  for (const spec of specs) {
    expect(spec.streams).toBeUndefined();
    if (spec.pipeline.source !== "graph")
      throw new Error("Expected inline graph");
    expect(
      spec.pipeline.pipeline_graph.nodes.find((node) => node.type === "filesrc")
        ?.data.location,
    ).toBe("h265.mp4");
  }
  const software = specs[1].pipeline;
  expect(
    software.source === "graph" && software.pipeline_graph.cpu_pinning,
  ).toEqual([12, 13, 14, 15]);
  await expect(page.getByText("VDBox 3 + CPU 2 = 5 streams")).toBeVisible();
  const best = trials
    .getByRole("row")
    .filter({ hasText: "Best configuration" });
  await expect(best).toHaveCount(1);
  await expect(best).toHaveClass(/bg-success\/15.*text-success/);
  await expect(trials.getByRole("button", { name: /Inspect/ })).toHaveCount(0);
  await expect(
    page.getByRole("cell", { name: "Below rate", exact: true }).first(),
  ).toBeVisible();
  await page.screenshot({
    path: "/tmp/vippet-hybrid-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("button", { name: "Run hybrid decode" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "/tmp/vippet-hybrid-mobile.png",
    fullPage: true,
  });
});

test("classic and mixed density accept clearing and retyping target FPS", async ({
  page,
}) => {
  await setup(page);
  for (const mode of ["Classic", "Mixed"]) {
    await page.getByRole("tab", { name: mode, exact: true }).click();
    const fps = page.getByLabel("Set target FPS");
    await fps.clear();
    await expect(fps).toHaveValue("");
    await expect(
      page.getByRole("button", { name: "Run density test" }),
    ).toBeDisabled();
    await fps.pressSequentially("45");
    await expect(fps).toHaveValue("45");
    await expect(
      page.getByRole("button", { name: "Run density test" }),
    ).toBeEnabled();
  }
  await page.getByRole("tab", { name: "Classic" }).click();
  const participation = page.getByRole("tabpanel").getByRole("spinbutton");
  await participation.clear();
  await expect(participation).toHaveValue("");
  await participation.pressSequentially("100");
  await expect(participation).toHaveValue("100");
});

test("hybrid test automatically matches the codec and requires a stable runtime", async ({
  page,
}) => {
  const submission = await setup(page);
  const run = page.getByRole("button", { name: "Run hybrid decode" });
  await expect(run).toBeDisabled();
  await page.getByRole("combobox", { name: "Video source" }).click();
  await page.getByRole("option", { name: /h265.mp4/ }).click();
  await expect(run).toBeEnabled();
  const duration = page.getByLabel("Iteration duration (s)");
  await duration.clear();
  await expect(duration).toHaveValue("");
  await expect(run).toBeDisabled();
  await duration.pressSequentially("5");
  await expect(run).toBeDisabled();
  await duration.fill("30");
  await page.getByRole("combobox", { name: "Video source" }).click();
  await page.getByRole("option", { name: /h264.mp4/ }).click();
  await expect(page.getByText("avdec_h264", { exact: true })).toBeVisible();
  await expect(page.getByText("All CPU cores", { exact: true })).toBeVisible();
  await expect(run).toBeEnabled();
  await run.click();
  await expect(
    page.getByRole("heading", { name: "Selected configuration" }),
  ).toBeVisible();
  const software = submission()?.pipeline_density_specs[1].pipeline;
  expect(
    software?.source === "graph" &&
      software.pipeline_graph.nodes.some((node) => node.type === "avdec_h264"),
  ).toBe(true);
  expect(
    software?.source === "graph" && software.pipeline_graph.cpu_pinning,
  ).toEqual([]);
});

for (const missing of ["pipeline", "hardware", "cpu"] as const) {
  test(`hybrid test rejects missing Media Decode ${missing} without falling back`, async ({
    page,
  }) => {
    await setup(page, 0, missing);
    await page.getByRole("combobox", { name: "Video source" }).click();
    await page.getByRole("option", { name: /h265.mp4/ }).click();
    await expect(
      page.getByRole("alert").filter({ hasText: "Required Media Decode" }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Run hybrid decode" }),
    ).toBeDisabled();
  });
}
