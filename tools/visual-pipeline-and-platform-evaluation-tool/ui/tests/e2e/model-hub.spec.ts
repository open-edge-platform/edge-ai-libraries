// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { expect, test, type Page } from "@playwright/test";
import { mockApi } from "./fixtures/api";
import {
  buildModel,
  mockHubList,
  mockModelDownloads,
} from "./fixtures/model-hub";

// The Add Model dialog is 64rem tall; on shorter viewports its tabs end up off-screen.
test.use({ viewport: { width: 1600, height: 1100 } });

const openHubTab = async (page: Page, tab: string) => {
  await page.goto("/models");
  await page.getByRole("button", { name: "Add new model" }).click();
  const dialog = page.getByRole("dialog", { name: "Add New Model" });
  await dialog.getByRole("tab", { name: tab }).click();
  return dialog;
};

const hubRow = (page: Page, name: string) =>
  page.getByRole("row").filter({ hasText: name });

const HF_MODELS = [
  {
    name: "OpenVINO/yolo-det-ov",
    model_type: "object-detection",
    license: "apache-2.0",
    gated: false,
    metadata: { downloads: 12345 },
  },
  {
    name: "OpenVINO/gated-llm-ov",
    model_type: "text-generation",
    license: "llama3",
    gated: "manual",
    metadata: { downloads: 10 },
  },
  {
    name: "OpenVINO/fill-mask-ov",
    model_type: "fill-mask",
    license: "mit",
    gated: false,
  },
  {
    name: "OpenVINO/installed-ov",
    model_type: "object-detection",
    license: "mit",
    gated: false,
  },
];

test.describe("Add model - Hugging Face hub", () => {
  test.beforeEach(async ({ page }) => {
    const state = await mockApi(page, {
      models: [buildModel("OpenVINO/installed-ov")],
    });
    await mockModelDownloads(page, state);
  });

  test("lists OpenVINO models and marks installed ones", async ({ page }) => {
    const requests = await mockHubList(page, () => ({ items: HF_MODELS }));
    await openHubTab(page, "HuggingFace Model");

    const yolo = hubRow(page, "OpenVINO/yolo-det-ov");
    await expect(yolo.getByText("object-detection")).toBeVisible();
    await expect(yolo.getByText((12345).toLocaleString("en-US"))).toBeVisible();
    await expect(
      yolo.getByRole("link", {
        name: "Open OpenVINO/yolo-det-ov on Hugging Face",
      }),
    ).toHaveAttribute("href", "https://huggingface.co/OpenVINO/yolo-det-ov");
    await expect(
      hubRow(page, "OpenVINO/installed-ov").getByText("Installed", {
        exact: true,
      }),
    ).toBeVisible();

    expect(requests[0]).toMatchObject({
      hub: "huggingface",
      filters: { author: "OpenVINO" },
      offset: 0,
    });
  });

  test("searches and pages through the hub", async ({ page }) => {
    const requests = await mockHubList(page, (request) =>
      request.filters?.search === "missing"
        ? { items: [] }
        : request.offset === 0
          ? { items: HF_MODELS.slice(0, 1), has_more: true, next_offset: 13 }
          : { items: HF_MODELS.slice(1, 2), has_more: false },
    );
    await page.clock.install();
    const dialog = await openHubTab(page, "HuggingFace Model");

    await expect(hubRow(page, "OpenVINO/yolo-det-ov")).toBeVisible();
    // The initial search debounce resets paging, so let it fire first.
    await page.clock.runFor(500);
    await dialog.getByLabel("Go to next page").click();
    await expect(hubRow(page, "OpenVINO/gated-llm-ov")).toBeVisible();
    expect(requests.at(-1)?.offset).toBe(13);

    await dialog.getByLabel("Go to previous page").click();
    await expect(hubRow(page, "OpenVINO/yolo-det-ov")).toBeVisible();

    await dialog
      .getByPlaceholder("Search HuggingFace models...")
      .fill("missing");
    await expect(dialog.getByText("No models found")).toBeVisible();
    await expect(
      dialog.getByText("Try adjusting your search terms"),
    ).toBeVisible();
    expect(requests.at(-1)).toMatchObject({
      filters: { author: "OpenVINO", search: "missing" },
      offset: 0,
    });
  });

  test("installs a model with the category derived from its task", async ({
    page,
  }) => {
    await mockHubList(page, () => ({ items: HF_MODELS }));
    const dialog = await openHubTab(page, "HuggingFace Model");

    const downloadRequest = page.waitForRequest("**/api/v1/models/download");
    await hubRow(page, "OpenVINO/yolo-det-ov")
      .getByRole("button", { name: "Install" })
      .click();

    expect((await downloadRequest).postDataJSON()).toEqual({
      names: ["OpenVINO/yolo-det-ov"],
      hub: "huggingface",
      category: "object_detection",
      gated: "false",
    });
    await expect(
      page.getByText('Model "OpenVINO/yolo-det-ov" installed successfully.'),
    ).toBeVisible();
    await expect(dialog).toBeHidden();
  });

  test("requires license acknowledgement for gated models", async ({
    page,
  }) => {
    await mockHubList(page, () => ({ items: HF_MODELS }));
    await openHubTab(page, "HuggingFace Model");

    await hubRow(page, "OpenVINO/gated-llm-ov")
      .getByRole("button", { name: "Install" })
      .click();

    const license = page.getByRole("dialog", {
      name: "Additional action required",
    });
    await expect(
      license.getByRole("link", { name: "OpenVINO/gated-llm-ov" }),
    ).toHaveAttribute("href", "https://huggingface.co/OpenVINO/gated-llm-ov");

    const downloadRequest = page.waitForRequest("**/api/v1/models/download");
    await license.getByRole("button", { name: "Proceed with install" }).click();

    expect((await downloadRequest).postDataJSON()).toMatchObject({
      names: ["OpenVINO/gated-llm-ov"],
      category: "large_language_models",
      gated: "manual",
    });
  });

  test("refuses models with an unsupported task", async ({ page }) => {
    let downloads = 0;
    page.on("request", (request) => {
      if (request.url().endsWith("/api/v1/models/download")) downloads += 1;
    });
    await mockHubList(page, () => ({ items: HF_MODELS }));
    await openHubTab(page, "HuggingFace Model");

    await hubRow(page, "OpenVINO/fill-mask-ov")
      .getByRole("button", { name: "Install" })
      .click();

    await expect(page.getByText("Cannot install model")).toBeVisible();
    await expect(
      page.getByText(
        'Unsupported task "fill-mask" for "OpenVINO/fill-mask-ov".',
      ),
    ).toBeVisible();
    expect(downloads).toBe(0);
  });
});

const GETI_MODELS = [
  {
    name: "yolox-tiny",
    owner: "Warehouse detection",
    model_type: "detection",
    metadata: {
      variants: [
        { model_format: "openvino", precision: ["FP16", "FP32"] },
        { model_format: "onnx", precision: "FP32" },
      ],
    },
  },
  {
    name: "efficientnet-b0",
    owner: "Defect classification",
    model_type: "classification",
    metadata: { variants: [{ model_format: "openvino", precision: "INT8" }] },
  },
  {
    name: "onnx-only",
    owner: "Experiments",
    model_type: "detection",
    metadata: { variants: [{ model_format: "onnx", precision: "FP32" }] },
  },
];

test.describe("Add model - Geti", () => {
  test.beforeEach(async ({ page }) => {
    const state = await mockApi(page);
    await mockModelDownloads(page, state);
  });

  test("lists only successfully trained models with OpenVINO precisions", async ({
    page,
  }) => {
    const requests = await mockHubList(page, () => ({
      items: GETI_MODELS,
      total: GETI_MODELS.length,
    }));
    await openHubTab(page, "Geti Model");

    const yolox = hubRow(page, "yolox-tiny");
    await expect(yolox.getByText("Warehouse detection")).toBeVisible();
    await expect(yolox.getByText("FP16, FP32")).toBeVisible();
    await expect(yolox.getByRole("button", { name: "Install" })).toBeVisible();

    const onnxOnly = hubRow(page, "onnx-only");
    await expect(onnxOnly.getByText("no precisions available")).toBeVisible();
    await expect(onnxOnly.getByRole("button", { name: "Install" })).toHaveCount(
      0,
    );

    expect(requests[0]).toMatchObject({
      hub: "geti",
      filters: { training_status: "successful" },
    });
  });

  test("filters by model name on the server and by category locally", async ({
    page,
  }) => {
    const requests = await mockHubList(page, (request) => ({
      items: GETI_MODELS.filter((model) =>
        model.name.includes(request.filters?.model_name ?? ""),
      ),
      total: null,
    }));
    const dialog = await openHubTab(page, "Geti Model");

    await dialog.getByRole("combobox").click();
    await page.getByRole("option", { name: "classification" }).click();
    await expect(hubRow(page, "efficientnet-b0")).toBeVisible();
    await expect(hubRow(page, "yolox-tiny")).toHaveCount(0);

    await dialog.getByPlaceholder("yolox-tiny").fill("yolox");
    await expect(dialog.getByText("No models found")).toBeVisible();
    expect(requests.at(-1)?.filters).toEqual({
      model_name: "yolox",
      training_status: "successful",
    });
  });

  test("installs a model with the category mapped from the Geti task", async ({
    page,
  }) => {
    await mockHubList(page, () => ({ items: GETI_MODELS, total: 3 }));
    const dialog = await openHubTab(page, "Geti Model");

    const downloadRequest = page.waitForRequest("**/api/v1/models/download");
    await hubRow(page, "yolox-tiny")
      .getByRole("button", { name: "Install" })
      .click();

    expect((await downloadRequest).postDataJSON()).toEqual({
      names: ["yolox-tiny"],
      hub: "geti",
      category: "object_detection",
    });
    await expect(
      page.getByText('Model "yolox-tiny" installed successfully.'),
    ).toBeVisible();
    await expect(dialog).toBeHidden();
  });

  test("explains when the Geti server cannot be reached", async ({ page }) => {
    await page.route("**/api/v1/models/list", (route) =>
      route.fulfill({
        status: 502,
        contentType: "application/json",
        body: JSON.stringify({ message: "Geti is not configured" }),
      }),
    );
    const dialog = await openHubTab(page, "Geti Model");

    await expect(
      dialog.getByText(/Check that the Geti server is configured/),
    ).toBeVisible();
  });
});
