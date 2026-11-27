// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { expect, test } from "@playwright/test";
import {
  buildPipeline,
  buildVariant,
  fulfillJson,
  linearGraph,
  mockApi,
} from "./fixtures/api";

const pipelines = [
  buildPipeline({
    id: "pipeline-a",
    name: "Pipeline A",
    variants: [buildVariant({ pipeline_graph: linearGraph("a.mp4") })],
  }),
  buildPipeline({
    id: "pipeline-b",
    name: "Pipeline B",
    variants: [buildVariant({ pipeline_graph: linearGraph("b.mp4") })],
  }),
];

test.describe("Density tests - participation rates", () => {
  test("rates of rows using the same pipeline are changed independently", async ({
    page,
  }) => {
    await mockApi(page, { pipelines });
    await page.route("**/api/v1/tests/density", (route) =>
      fulfillJson(route, { job_id: "density-1" }, 202),
    );

    await page.goto("/tests/density");

    const classic = page.getByRole("tabpanel", { name: "Classic" });
    const rates = classic.getByRole("spinbutton");
    await expect(rates).toHaveCount(1);
    await expect(rates.first()).toHaveValue("100");

    await classic.getByRole("button", { name: "Add Pipeline" }).click();
    await expect(rates).toHaveCount(2);
    await expect(rates.nth(0)).toHaveValue("50");
    await expect(rates.nth(1)).toHaveValue("50");

    // Both rows point at the same pipeline - the case that used to update the wrong row.
    await classic.getByRole("combobox").nth(2).click();
    await page.getByRole("option", { name: "Pipeline A" }).click();
    await expect(classic.getByRole("combobox").nth(2)).toHaveText("Pipeline A");

    await rates.nth(1).fill("30");
    await expect(rates.nth(1)).toHaveValue("30");
    await expect(rates.nth(0)).toHaveValue("70");

    await rates.nth(0).fill("80");
    await expect(rates.nth(0)).toHaveValue("80");
    await expect(rates.nth(1)).toHaveValue("20");

    const runRequest = page.waitForRequest(
      (request) =>
        request.method() === "POST" &&
        request.url().endsWith("/api/v1/tests/density"),
    );
    await page.getByRole("button", { name: "Run density test" }).click();

    const body = (await runRequest).postDataJSON();
    expect(
      body.pipeline_density_specs.map(
        (spec: { stream_rate: number }) => spec.stream_rate,
      ),
    ).toEqual([80, 20]);
  });

  test("a single pipeline always gets 100%", async ({ page }) => {
    await mockApi(page, { pipelines });

    await page.goto("/tests/density");

    const classic = page.getByRole("tabpanel", { name: "Classic" });
    const rate = classic.getByRole("spinbutton");
    await rate.fill("40");

    await expect(rate).toHaveValue("100");
  });
});
