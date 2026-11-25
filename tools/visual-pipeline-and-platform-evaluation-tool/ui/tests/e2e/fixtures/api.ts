// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import type { Page, Route } from "@playwright/test";

const TIMESTAMP = "2026-01-01T00:00:00Z";

export type GraphNode = {
  id: string;
  type: string;
  data: Record<string, string>;
};

export type PipelineGraph = {
  cpu_pinning?: number[];
  nodes: GraphNode[];
  edges: Array<{ id: string; source: string; target: string }>;
};

export type MockVariant = {
  id: string;
  name: string;
  read_only?: boolean;
  media_only?: boolean;
  pipeline_graph: PipelineGraph;
  pipeline_graph_simple: PipelineGraph;
  created_at: string;
  modified_at: string;
};

export type MockPipeline = {
  id: string;
  name: string;
  description: string;
  source: "PREDEFINED" | "USER_CREATED" | "TEMPLATE";
  type: "vision" | "time_series";
  tags: string[];
  variants: MockVariant[];
  created_at: string;
  modified_at: string;
};

export type CpuCoreType = "P" | "E" | "LPE" | "UNIFORM";

export type MockVideo = {
  filename: string;
  width: number;
  height: number;
  fps: number;
  frame_count: number;
  codec: string;
  duration: number;
  source?: "auto" | "uploaded";
  path?: string;
};

export type MockDefaultRecording = {
  filename: string;
  source: string;
  status:
    | "available"
    | "queued"
    | "downloading"
    | "downloaded"
    | "failed"
    | "conflict";
  hevc_filename: string;
  conversion_status:
    | "not_converted"
    | "queued"
    | "converting"
    | "converted"
    | "failed"
    | "conflict"
    | "unsupported";
};

export type MockApiState = {
  pipelines: MockPipeline[];
  devices: unknown[];
  models: unknown[];
  videos: MockVideo[];
  defaultRecordings: MockDefaultRecording[];
};

export const fulfillJson = (route: Route, body: unknown, status = 200) =>
  route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });

/** `filesrc -> (extra nodes) -> fakesink` chain, the shape used by most predefined pipelines. */
export const linearGraph = (
  location: string,
  middle: GraphNode[] = [],
): PipelineGraph => {
  const nodes: GraphNode[] = [
    { id: "0", type: "filesrc", data: { location } },
    ...middle.map((node, index) => ({ ...node, id: String(index + 1) })),
    { id: String(middle.length + 1), type: "fakesink", data: {} },
  ];
  return {
    cpu_pinning: [],
    nodes,
    edges: nodes.slice(1).map((node, index) => ({
      id: `e${index}`,
      source: nodes[index].id,
      target: node.id,
    })),
  };
};

export const buildVariant = (
  overrides: Partial<MockVariant> & { pipeline_graph: PipelineGraph },
): MockVariant => ({
  id: "cpu",
  name: "CPU",
  read_only: false,
  media_only: false,
  pipeline_graph_simple: overrides.pipeline_graph,
  created_at: TIMESTAMP,
  modified_at: TIMESTAMP,
  ...overrides,
});

export const buildPipeline = (
  overrides: Partial<MockPipeline> & { id: string; variants: MockVariant[] },
): MockPipeline => ({
  name: overrides.id,
  description: `Pipeline ${overrides.id} used by e2e tests.`,
  source: "USER_CREATED",
  type: "vision",
  tags: [],
  created_at: TIMESTAMP,
  modified_at: TIMESTAMP,
  ...overrides,
});

export const buildCpuDevice = (
  cores: Array<{ cpu: number; core_type: CpuCoreType }> | null,
) => ({
  device_name: "CPU",
  full_device_name: "Intel(R) Core(TM) Ultra 7 165H",
  device_type: "INTEGRATED",
  device_family: "CPU",
  gpu_id: null,
  cpu_topology: cores
    ? {
        is_hybrid: new Set(cores.map((core) => core.core_type)).size > 1,
        source: "sysfs_pmu",
        cores: cores.map((core) => ({ ...core, core_id: core.cpu })),
      }
    : null,
});

export const buildVideo = (
  filename: string,
  overrides: Partial<MockVideo> = {},
): MockVideo => ({
  filename,
  width: 1920,
  height: 1080,
  fps: 30,
  frame_count: 900,
  codec: "h264",
  duration: 30,
  source: "auto",
  path: filename,
  ...overrides,
});

export const buildDefaultRecording = (
  filename: string,
  overrides: Partial<MockDefaultRecording> = {},
): MockDefaultRecording => ({
  filename,
  source: `https://example.com/samples/${filename}`,
  status: "available",
  hevc_filename: filename.replace(/\.mp4$/, "_h265.mp4"),
  conversion_status: "not_converted",
  ...overrides,
});

// At least one installed model keeps the "no models" warning toast out of the way.
const INSTALLED_MODEL = {
  name: "yolo11s",
  display_name: "YOLO11s",
  category: "detection",
  source: "ultralytics",
  install_status: "installed",
};

/**
 * Mocks the ViPPET REST API with a mutable in-memory state.
 *
 * Tests can change the returned state at any time (e.g. to finish a download);
 * polling queries pick the change up on their next request. Unmocked endpoints
 * answer 404 so a missing mock fails visibly instead of hitting a real backend.
 */
export const mockApi = async (
  page: Page,
  initial: Partial<MockApiState> = {},
): Promise<MockApiState> => {
  const state: MockApiState = structuredClone({
    pipelines: initial.pipelines ?? [],
    devices: initial.devices ?? [buildCpuDevice(null)],
    models: initial.models ?? [INSTALLED_MODEL],
    videos: initial.videos ?? [],
    defaultRecordings: initial.defaultRecordings ?? [],
  });

  // Routes are matched in reverse registration order, so the catch-all goes first.
  await page.route("**/api/v1/**", (route) =>
    fulfillJson(route, { detail: "Not mocked in e2e tests" }, 404),
  );
  await page.route("**/metrics/stream", (route) => route.abort());

  await page.route("**/api/v1/devices", (route) =>
    fulfillJson(route, state.devices),
  );
  await page.route("**/api/v1/models", (route) =>
    fulfillJson(route, state.models),
  );
  await page.route("**/api/v1/videos", (route) =>
    fulfillJson(route, state.videos),
  );
  await page.route("**/api/v1/videos/default-recordings", (route) =>
    fulfillJson(route, state.defaultRecordings),
  );
  await page.route("**/api/v1/pipelines", (route) =>
    fulfillJson(route, state.pipelines),
  );
  await page.route("**/api/v1/pipelines/*", (route) => {
    const id = decodeURIComponent(
      new URL(route.request().url()).pathname.split("/").pop() ?? "",
    );
    const pipeline = state.pipelines.find((item) => item.id === id);
    return pipeline
      ? fulfillJson(route, pipeline)
      : fulfillJson(route, { detail: "Pipeline not found" }, 404);
  });
  await page.route("**/api/v1/pipelines/*/variants/*", (route) => {
    const segments = new URL(route.request().url()).pathname.split("/");
    const variantId = decodeURIComponent(segments.pop() ?? "");
    segments.pop();
    const pipelineId = decodeURIComponent(segments.pop() ?? "");
    const variant = state.pipelines
      .find((item) => item.id === pipelineId)
      ?.variants.find((item) => item.id === variantId);

    if (!variant || route.request().method() !== "PATCH") {
      return fulfillJson(route, { detail: "Variant not found" }, 404);
    }

    Object.assign(variant, route.request().postDataJSON(), {
      modified_at: new Date().toISOString(),
    });
    return fulfillJson(route, variant);
  });

  return state;
};
