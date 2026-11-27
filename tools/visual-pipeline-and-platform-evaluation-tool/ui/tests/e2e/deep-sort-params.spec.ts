// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { expect, test, type Page } from "@playwright/test";
import {
  buildPipeline,
  buildVariant,
  buildVideo,
  linearGraph,
  mockApi,
} from "./fixtures/api";

// Deep SORT is offered only for this predefined pipeline.
const DEEP_SORT_PIPELINE_ID = "people-detection-and-tracking";

const setup = (
  page: Page,
  pipelineId: string,
  trackData: Record<string, string>,
) =>
  mockApi(page, {
    videos: [buildVideo("people.mp4")],
    pipelines: [
      buildPipeline({
        id: pipelineId,
        name: "People detection and tracking",
        variants: [
          buildVariant({
            pipeline_graph: linearGraph("people.mp4", [
              { id: "", type: "gvatrack", data: trackData },
            ]),
          }),
        ],
      }),
    ],
  });

const openTrackingNode = async (page: Page, pipelineId: string) => {
  await page.clock.install();
  await page.goto(`/pipelines/vision/${pipelineId}/cpu`);
  await page.locator(".react-flow__node-gvatrack").click();
  // Edits made within the history debounce would merge into the loaded-graph baseline.
  await page.clock.runFor(1_000);
};

const savedTrackData = async (page: Page, pipelineId: string) => {
  const saveRequest = page.waitForRequest(
    (request) =>
      request.method() === "PATCH" &&
      request.url().endsWith(`/pipelines/${pipelineId}/variants/cpu`),
  );
  const saveButton = page.getByRole("button", { name: "Save", exact: true });
  await expect(saveButton).toBeEnabled();
  await saveButton.click();

  const body = (await saveRequest).postDataJSON();
  return body.pipeline_graph_simple.nodes.find(
    (node: { type: string }) => node.type === "gvatrack",
  ).data as Record<string, string>;
};

test.describe("Tracking node - Deep SORT parameters", () => {
  test("composes deepsort-trck-cfg from the edited parameters", async ({
    page,
  }) => {
    await setup(page, DEEP_SORT_PIPELINE_ID, { "tracking-type": "deep-sort" });
    await openTrackingNode(page, DEEP_SORT_PIPELINE_ID);

    await expect(page.getByText("Deep SORT Parameters:")).toBeVisible();

    await page.getByPlaceholder("30", { exact: true }).fill("60");
    await page.getByPlaceholder("Enter Object class").fill("person");

    const data = await savedTrackData(page, DEEP_SORT_PIPELINE_ID);
    expect(data["tracking-type"]).toBe("deep-sort");
    expect(data["deepsort-trck-cfg"]).toBe('"max_age=60,object_class=person"');
  });

  test("keeps unknown keys and drops cleared values", async ({ page }) => {
    await setup(page, DEEP_SORT_PIPELINE_ID, {
      "tracking-type": "deep-sort",
      "deepsort-trck-cfg": '"max_age=45,n_init=2,custom_flag=1"',
    });
    await openTrackingNode(page, DEEP_SORT_PIPELINE_ID);

    const maxAge = page.getByPlaceholder("30", { exact: true });
    await expect(maxAge).toHaveValue("45");
    await expect(page.getByPlaceholder("3", { exact: true })).toHaveValue("2");

    await maxAge.fill("");
    await page.getByPlaceholder("0.2", { exact: true }).fill("0.3");

    const data = await savedTrackData(page, DEEP_SORT_PIPELINE_ID);
    expect(data["deepsort-trck-cfg"]).toBe(
      '"n_init=2,max_cosine_distance=0.3,custom_flag=1"',
    );
  });

  test("is not offered for other pipelines", async ({ page }) => {
    await setup(page, "custom-tracking", { "tracking-type": "deep-sort" });
    await openTrackingNode(page, "custom-tracking");

    await expect(
      page.locator(".react-flow__node-gvatrack").getByText("zero-term"),
    ).toBeVisible();
    await expect(page.getByText("Deep SORT Parameters:")).toHaveCount(0);
  });
});
