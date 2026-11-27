// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import type { Page } from "@playwright/test";
import { fulfillJson, type MockApiState } from "./api";

export type MockModel = {
  name: string;
  display_name: string;
  description?: string | null;
  category?: string | null;
  source: string;
  install_status: "installed" | "not_installed" | "installing" | "failed";
  variants?: Array<{ name: string; display_name: string; precision: string }>;
  used_by_pipelines?: string[];
  link?: string | null;
  gated?: "false" | "auto" | "manual" | null;
};

export const buildModel = (
  name: string,
  overrides: Partial<MockModel> = {},
): MockModel => ({
  name,
  display_name: name,
  category: "object_detection",
  source: "omz",
  install_status: "installed",
  variants: [{ name: `${name}-fp16`, display_name: name, precision: "FP16" }],
  used_by_pipelines: [],
  link: null,
  gated: "false",
  ...overrides,
});

export type ModelDownloadRequest = {
  names: string[];
  hub?: string;
  category?: string;
  gated?: string;
};

/**
 * Accepts model downloads and completes each job on its first status poll,
 * marking the model as installed. Names listed in `rejections` are refused
 * with the given message instead.
 */
export const mockModelDownloads = async (
  page: Page,
  state: MockApiState,
  rejections: Record<string, string> = {},
) => {
  const requests: ModelDownloadRequest[] = [];
  const jobs = new Map<string, string>();

  await page.route("**/api/v1/models/download", (route) => {
    const body = route.request().postDataJSON() as ModelDownloadRequest;
    requests.push(body);

    const items = Object.fromEntries(
      body.names.map((name) => {
        if (rejections[name]) {
          return [
            name,
            { name, job_id: null, status_code: 409, message: rejections[name] },
          ];
        }
        const jobId = `model-job-${jobs.size + 1}`;
        jobs.set(jobId, name);
        return [
          name,
          { name, job_id: jobId, status_code: 202, message: "Accepted" },
        ];
      }),
    );
    const rejected = body.names.filter((name) => rejections[name]).length;
    const status =
      rejected === 0 ? 202 : rejected === body.names.length ? 409 : 207;
    return fulfillJson(route, { jobs: items }, status);
  });

  await page.route("**/api/v1/jobs/models/*/status", (route) => {
    const jobId = new URL(route.request().url()).pathname.split("/").at(-2)!;
    const name = jobs.get(jobId) ?? "";
    const request = requests.find((item) => item.names.includes(name));
    const models = state.models as MockModel[];
    const model = models.find((item) => item.name === name);
    if (model) {
      model.install_status = "installed";
    } else {
      models.push(
        buildModel(name, {
          category: request?.category ?? null,
          source: request?.hub ?? "custom",
        }),
      );
    }

    return fulfillJson(route, {
      id: jobId,
      model_name: name,
      source: request?.hub ?? "omz",
      start_time: Date.now(),
      elapsed_time: 1500,
      state: "COMPLETED",
      details: [],
    });
  });

  return requests;
};

export type HubListRequest = {
  hub: string;
  filters?: Record<string, string>;
  limit?: number;
  offset?: number;
};

/** Serves `POST /models/list`; `respond` gets each request body and returns the page items. */
export const mockHubList = async (
  page: Page,
  respond: (request: HubListRequest) => {
    items: Array<Record<string, unknown>>;
    has_more?: boolean;
    next_offset?: number | null;
    total?: number | null;
  },
) => {
  const requests: HubListRequest[] = [];
  await page.route("**/api/v1/models/list", (route) => {
    const body = route.request().postDataJSON() as HubListRequest;
    requests.push(body);
    const response = respond(body);
    return fulfillJson(route, {
      hub: body.hub,
      limit: body.limit ?? 13,
      offset: body.offset ?? 0,
      count: response.items.length,
      ...response,
    });
  });
  return requests;
};
