// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { readFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";
import {
  buildPipeline,
  buildVariant,
  fulfillJson,
  linearGraph,
  mockApi,
} from "./fixtures/api";
import {
  buildModel,
  mockModelDownloads,
  type MockModel,
} from "./fixtures/model-hub";

const SUITE = "smart-nvr-suite";
const START_TIME = Date.UTC(2026, 10, 20, 10, 0, 0);

const PIPELINE = buildPipeline({
  id: "smart-nvr",
  name: "Smart NVR",
  description: "Detects vehicles and records the stream.",
  source: "PREDEFINED",
  variants: [
    buildVariant({
      id: "cpu",
      name: "CPU",
      pipeline_graph: linearGraph("traffic.mp4", [
        { id: "", type: "gvadetect", data: { model: "YOLO11s (INT8)" } },
      ]),
      pipeline_graph_simple: {
        nodes: [
          {
            id: "0",
            type: "source",
            data: { kind: "video", source: "traffic.mp4" },
          },
          { id: "1", type: "fakesink", data: {} },
        ],
        edges: [{ id: "e0", source: "0", target: "1" }],
      },
    }),
  ],
});

const BENCHMARK_SUITE = {
  id: 1,
  slug: SUITE,
  name: "Smart NVR Suite",
  description: "Measures Smart NVR throughput.",
  created_at: "2026-11-01T00:00:00Z",
  last_run_at: "2026-11-20T10:00:00Z",
  workloads: [
    {
      id: 11,
      pipeline_id: "smart-nvr",
      variants: "cpu",
      test_cases: [
        { id: 1, variant_id: "cpu", streams: 4 },
        { id: 2, variant_id: "cpu", streams: 1 },
      ],
    },
  ],
};

type RunStatus = "running" | "completed" | "failed";

const buildRun = (id: number, status: RunStatus, passed = 2) => ({
  id,
  suite_id: 1,
  suite_slug: SUITE,
  suite_name: BENCHMARK_SUITE.name,
  suite_description: BENCHMARK_SUITE.description,
  status,
  score_total: status === "running" ? null : 81.25,
  score_performance: status === "running" ? null : 90.5,
  score_efficiency: status === "running" ? null : 72,
  start_time: START_TIME,
  execution_time: 125_000,
  job_id: `bench-job-${id}`,
  total_test_cases: 2,
  passed_test_cases: passed,
});

const buildTestCaseRun = (
  id: number,
  streams: number,
  status: "completed" | "failed",
) => ({
  id,
  test_case_id: id,
  variant_id: "cpu",
  streams,
  workload_run_id: 70,
  start_time: START_TIME,
  execution_time: 60_000,
  total_fps: status === "completed" ? 118.4 : null,
  per_stream_fps: status === "completed" ? 29.6 : null,
  cpu_usage: 54.2,
  gpu_usage: null,
  npu_usage: null,
  media_usage: null,
  memory_usage: 12.5,
  power_usage: 21.3,
  latency_avg_ms: status === "completed" ? 18.24 : null,
  latency_avg_stddev_ms: status === "completed" ? 1.5 : null,
  latency_max_ms: status === "completed" ? 25.44 : null,
  latency_max_stddev_ms: null,
  latency_min_ms: status === "completed" ? 12.1 : null,
  latency_min_stddev_ms: status === "completed" ? 0.4 : null,
  score_total: status === "completed" ? 81.25 : null,
  score_performance: null,
  score_efficiency: null,
  metrics: null,
  job_id: `perf-job-${id}`,
  status,
});

const buildRunDetails = (id: number, status: RunStatus) => ({
  ...buildRun(id, status, 1),
  workload_runs: [
    {
      id: 70,
      workload_id: 11,
      pipeline_id: "smart-nvr",
      suite_run_id: id,
      status,
      score_total: 81.25,
      score_performance: 90.5,
      score_efficiency: 72,
      start_time: START_TIME,
      execution_time: 125_000,
      test_case_runs: [
        buildTestCaseRun(1, 4, "completed"),
        buildTestCaseRun(2, 1, "failed"),
      ],
      total_test_cases: 2,
      passed_test_cases: 1,
      failed_test_cases: 1,
      pass_rate: 50,
    },
  ],
});

type JobStatus = { id: string; suite_slug: string; state: string };

const buildJobStatus = (job: JobStatus) => ({
  ...job,
  suite_run_id: 99,
  start_time: START_TIME,
  elapsed_time: 5_000,
  details: [],
  total_test_cases: 2,
  completed_test_cases: 1,
  current_test_case_run_id: null,
  current_performance_job_id: null,
});

const setup = async (
  page: Page,
  {
    yoloStatus = "installed",
    runs = [] as ReturnType<typeof buildRun>[],
    jobs = [] as JobStatus[],
  }: {
    yoloStatus?: MockModel["install_status"];
    runs?: ReturnType<typeof buildRun>[];
    jobs?: JobStatus[];
  } = {},
) => {
  const state = await mockApi(page, {
    pipelines: [PIPELINE],
    models: [
      buildModel("yolo11s", {
        display_name: "YOLO11s",
        install_status: yoloStatus,
      }),
    ],
  });

  await page.route("**/api/v1/models/check-status", (route) => {
    const { display_names } = route.request().postDataJSON() as {
      display_names: string[];
    };
    return fulfillJson(route, {
      models: (state.models as MockModel[])
        .filter((model) => display_names.includes(model.display_name))
        .map(({ name, display_name, install_status }) => ({
          name,
          display_name,
          install_status,
        })),
    });
  });
  await page.route(`**/api/v1/benchmarks/${SUITE}`, (route) =>
    fulfillJson(route, BENCHMARK_SUITE),
  );
  await page.route(`**/api/v1/benchmarks/${SUITE}/runs`, (route) =>
    fulfillJson(route, runs),
  );
  await page.route("**/api/v1/jobs/tests/benchmark/status", (route) =>
    fulfillJson(route, jobs.map(buildJobStatus)),
  );
  await page.route("**/api/v1/jobs/tests/benchmark/*/status", (route) => {
    const id = new URL(route.request().url()).pathname.split("/").at(-2);
    const job = jobs.find((item) => item.id === id);
    return job
      ? fulfillJson(route, buildJobStatus(job))
      : fulfillJson(route, { message: "Job not found" }, 404);
  });

  return { state, jobs };
};

const runBenchmarkButton = (page: Page) =>
  // includeHidden: the modal dialog marks the rest of the page aria-hidden.
  page.getByRole("button", {
    name: /^(Run|Stop) Benchmark$/,
    includeHidden: true,
  });

const expectCsvDownload = async (page: Page, runId: number) => {
  const download = await page.waitForEvent("download");
  expect(download.suggestedFilename()).toMatch(
    new RegExp(`^${SUITE}-results-\\d{4}(-\\d{2}){5}-${runId}\\.csv$`),
  );
  expect(await readFile((await download.path())!, "utf8")).toContain(
    "smart-nvr",
  );
};

const mockCsvExport = (page: Page, runId: number) =>
  page.route(`**/api/v1/benchmarks/${SUITE}/run/${runId}/csv`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/csv",
      body: "workload,score_total\nsmart-nvr,81.25\n",
    }),
  );

test.describe("Benchmark details - required models", () => {
  test("blocks the run until missing models are installed", async ({
    page,
  }) => {
    const { state } = await setup(page, { yoloStatus: "not_installed" });
    const downloads = await mockModelDownloads(page, state);
    await page.goto(`/benchmarks/${SUITE}`);

    const dialog = page.getByRole("dialog", {
      name: "Required models are missing",
    });
    await expect(
      dialog.getByText(
        "One or more models used by this benchmark's workloads are not installed.",
      ),
    ).toBeVisible();
    await expect(runBenchmarkButton(page)).toBeDisabled();

    await dialog.getByRole("button", { name: "Install" }).click();

    await expect(page.getByText("Model installed successfully.")).toBeVisible();
    expect(downloads).toEqual([{ names: ["yolo11s"] }]);
    await expect(dialog).toBeHidden();
    await expect(runBenchmarkButton(page)).toBeEnabled();
  });

  test("describes the workloads of the suite", async ({ page }) => {
    await setup(page);
    await page.goto(`/benchmarks/${SUITE}`);

    await expect(
      page.getByRole("heading", { name: "Smart NVR Suite" }),
    ).toBeVisible();
    const workload = page.getByRole("row").filter({ hasText: "Smart NVR" });
    await expect(workload.getByText("Input: traffic.mp4")).toBeVisible();
    await expect(workload.getByText("Models: YOLO11s")).toBeVisible();
    await expect(
      workload.getByText("Tested stream counts: 1, 4"),
    ).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(0);
  });
});

test.describe("Benchmark details - running", () => {
  test("starts and stops a benchmark run", async ({ page }) => {
    const { jobs } = await setup(page);
    await page.route(`**/api/v1/benchmarks/${SUITE}/run`, (route) => {
      jobs.push({ id: "bench-job-1", suite_slug: SUITE, state: "RUNNING" });
      return fulfillJson(route, { job_id: "bench-job-1" }, 202);
    });
    await page.route("**/api/v1/jobs/tests/benchmark/bench-job-1", (route) => {
      if (route.request().method() !== "DELETE") return route.fallback();
      jobs[0].state = "COMPLETED";
      return fulfillJson(route, { message: "Benchmark stopped" });
    });
    await page.goto(`/benchmarks/${SUITE}`);

    await page.getByRole("button", { name: "Run Benchmark" }).click();

    const stopButton = page.getByRole("button", { name: "Stop Benchmark" });
    await expect(stopButton).toBeEnabled();

    const stopRequest = page.waitForRequest(
      (request) =>
        request.method() === "DELETE" &&
        request.url().endsWith("/jobs/tests/benchmark/bench-job-1"),
    );
    await stopButton.click();
    await stopRequest;

    await expect(
      page.getByRole("button", { name: "Run Benchmark" }),
    ).toBeEnabled();
  });

  test("cannot start while another suite is running", async ({ page }) => {
    await setup(page, {
      jobs: [{ id: "other-job", suite_slug: "other-suite", state: "RUNNING" }],
    });
    await page.goto(`/benchmarks/${SUITE}`);

    await expect(
      page.getByRole("button", { name: "Run Benchmark" }),
    ).toBeDisabled();
  });
});

test.describe("Benchmark results", () => {
  test("lists runs and exports failed ones too", async ({ page }) => {
    await setup(page, {
      runs: [
        buildRun(9, "running", 0),
        buildRun(8, "completed"),
        buildRun(7, "failed", 1),
      ],
    });
    await mockCsvExport(page, 7);
    await page.goto(`/benchmarks/${SUITE}`);

    const failedRun = page.getByRole("row").filter({ hasText: "#7" });
    await expect(failedRun.getByText("Failed")).toBeVisible();
    await expect(failedRun.getByText("50.0% (1/2)")).toBeVisible();
    await expect(failedRun.getByText("81.25")).toBeVisible();

    // A running run only links to its details.
    await expect(
      page.getByRole("link", { name: "View details for run 9" }),
    ).toHaveAttribute("href", `/benchmarks/${SUITE}/run/9`);
    await expect(
      page.getByRole("button", { name: "Open actions for run 9" }),
    ).toHaveCount(0);

    await page.getByRole("button", { name: "Open actions for run 7" }).click();
    const download = expectCsvDownload(page, 7);
    await page.getByRole("menuitem", { name: "Export CSV" }).click();
    await download;
  });

  test("shows an error when the CSV export fails", async ({ page }) => {
    await setup(page, { runs: [buildRun(8, "completed")] });
    await page.route(`**/api/v1/benchmarks/${SUITE}/run/8/csv`, (route) =>
      fulfillJson(route, { message: "Export failed" }, 500),
    );
    await page.goto(`/benchmarks/${SUITE}`);

    await page.getByRole("button", { name: "Open actions for run 8" }).click();
    await page.getByRole("menuitem", { name: "Export CSV" }).click();

    await expect(
      page.getByText("Failed to export CSV for this run."),
    ).toBeVisible();
  });
});

const mockRunDetails = (
  page: Page,
  runId: number,
  details: ReturnType<typeof buildRunDetails>,
) =>
  page.route(`**/api/v1/benchmarks/${SUITE}/run/${runId}`, (route) =>
    fulfillJson(route, details),
  );

test.describe("Benchmark run details", () => {
  test("exports a failed run and shows per test case metrics", async ({
    page,
  }) => {
    await setup(page);
    await mockRunDetails(page, 7, buildRunDetails(7, "failed"));
    await mockCsvExport(page, 7);
    await page.goto(`/benchmarks/${SUITE}/run/7`);

    await expect(page.getByRole("heading", { name: /#7\)$/ })).toBeVisible();
    for (const chart of ["Total FPS", "Latency", "Power"]) {
      await expect(
        page.getByRole("heading", { name: chart, exact: true }),
      ).toBeVisible();
    }

    await expect(
      page.getByRole("cell", { name: "118.40", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("cell", { name: "29.60", exact: true }),
    ).toBeVisible();
    await page.getByText("25.4 ms", { exact: true }).hover();
    await expect(page.getByText("Latency Avg")).toBeVisible();
    await expect(page.getByText("18.2 ms", { exact: true })).toBeVisible();
    await expect(page.getByText("(std dev: N/A)")).toBeVisible();

    await page.getByRole("button", { name: "Export Results" }).click();
    const download = expectCsvDownload(page, 7);
    await page.getByRole("menuitem", { name: "Export to CSV" }).click();
    await download;
  });

  test("does not offer export while the run is in progress", async ({
    page,
  }) => {
    await setup(page);
    await mockRunDetails(page, 9, buildRunDetails(9, "running"));
    await page.goto(`/benchmarks/${SUITE}/run/9`);

    await expect(
      page.getByRole("heading", { name: "Running Smart NVR Suite (#9)" }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Export Results" }),
    ).toHaveCount(0);
  });

  test("collapses and expands workload details", async ({ page }) => {
    await setup(page);
    await mockRunDetails(page, 8, buildRunDetails(8, "completed"));
    await page.goto(`/benchmarks/${SUITE}/run/8`);

    const fpsCell = page.getByRole("cell", { name: "118.40", exact: true });
    await expect(fpsCell).toBeVisible();
    await page.getByRole("button", { name: "Collapse workload 70" }).click();
    await expect(fpsCell).toHaveCount(0);
    await page.getByRole("button", { name: "Expand workload 70" }).click();
    await expect(fpsCell).toBeVisible();
  });
});
