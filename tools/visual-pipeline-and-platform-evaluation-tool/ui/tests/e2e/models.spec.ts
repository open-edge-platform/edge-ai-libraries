// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { expect, test, type Page } from "@playwright/test";
import { mockApi } from "./fixtures/api";
import {
  buildModel,
  mockModelDownloads,
  type MockModel,
} from "./fixtures/model-hub";

const GATED_LINK = "https://huggingface.co/OpenVINO/gated-vlm";

const MODELS: MockModel[] = [
  buildModel("yolo11s", {
    display_name: "YOLO11s",
    source: "ultralytics",
    link: "https://docs.ultralytics.com/models/yolo11/",
    variants: [
      { name: "yolo11s-fp16", display_name: "YOLO11s", precision: "FP16" },
      { name: "yolo11s-int8", display_name: "YOLO11s", precision: "INT8" },
    ],
    used_by_pipelines: ["smart-nvr"],
  }),
  buildModel("person-detection", {
    display_name: "Person Detection",
    install_status: "not_installed",
    used_by_pipelines: ["smart-nvr"],
  }),
  buildModel("gated-vlm", {
    display_name: "Gated VLM",
    category: "vision_language_models",
    source: "huggingface",
    install_status: "not_installed",
    gated: "manual",
    link: GATED_LINK,
    used_by_pipelines: ["vlm-captioning"],
  }),
  buildModel("resnet-50", {
    display_name: "ResNet-50",
    category: "image_classification",
    install_status: "failed",
  }),
  buildModel("my-model", {
    display_name: "My Model",
    category: null,
    source: "custom",
  }),
];

const modelRow = (page: Page, displayName: string) =>
  page.getByRole("row").filter({ hasText: displayName });

const openInstallAction = async (page: Page, displayName: string) => {
  await page
    .getByRole("button", { name: `Actions for ${displayName}` })
    .click();
  return page.getByRole("menuitem", { name: "Install", exact: true });
};

test.describe("Models page", () => {
  test("groups models by category and shows their details", async ({
    page,
  }) => {
    await mockApi(page, { models: MODELS });
    await page.goto("/models");

    for (const heading of [
      "Object Detection",
      "Image Classification",
      "Vision Language Models (VLMs)",
      "Uncategorized",
    ]) {
      await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    }
    await expect(
      page.getByRole("heading", { name: "Pose Estimation" }),
    ).toHaveCount(0);

    const yolo = modelRow(page, "YOLO11s");
    await expect(
      yolo.getByRole("link", { name: "ultralytics" }),
    ).toHaveAttribute("href", "https://docs.ultralytics.com/models/yolo11/");
    await expect(yolo.getByText("FP16, INT8")).toBeVisible();
    await expect(yolo.getByText("Installed", { exact: true })).toBeVisible();

    await expect(
      modelRow(page, "Person Detection").getByText("Not Installed"),
    ).toBeVisible();
    await expect(modelRow(page, "ResNet-50").getByText("Failed")).toBeVisible();
  });

  test("allows installing only models that are not installed", async ({
    page,
  }) => {
    await mockApi(page, { models: MODELS });
    await page.goto("/models");

    await expect(await openInstallAction(page, "YOLO11s")).toBeDisabled();
    await page.keyboard.press("Escape");

    await expect(await openInstallAction(page, "ResNet-50")).toBeEnabled();
  });

  test("installs a single model from the actions menu", async ({ page }) => {
    const state = await mockApi(page, { models: MODELS });
    const downloads = await mockModelDownloads(page, state);
    await page.goto("/models");

    await (await openInstallAction(page, "Person Detection")).click();

    await expect(page.getByText("Model installed successfully.")).toBeVisible();
    expect(downloads).toEqual([{ names: ["person-detection"] }]);
    await expect(
      modelRow(page, "Person Detection").getByText("Installed", {
        exact: true,
      }),
    ).toBeVisible();
  });

  test("asks to acknowledge the license before installing a gated model", async ({
    page,
  }) => {
    const state = await mockApi(page, { models: MODELS });
    const downloads = await mockModelDownloads(page, state);
    await page.goto("/models");

    await (await openInstallAction(page, "Gated VLM")).click();

    const dialog = page.getByRole("dialog", {
      name: "Additional action required",
    });
    await expect(dialog).toBeVisible();
    await expect(
      dialog.getByRole("link", { name: "gated-vlm" }),
    ).toHaveAttribute("href", GATED_LINK);

    await dialog.getByRole("button", { name: "Cancel" }).click();
    await expect(dialog).toBeHidden();
    expect(downloads).toHaveLength(0);

    await (await openInstallAction(page, "Gated VLM")).click();
    await dialog.getByRole("button", { name: "Proceed with install" }).click();

    await expect(page.getByText("Model installed successfully.")).toBeVisible();
    expect(downloads).toEqual([{ names: ["gated-vlm"] }]);
  });

  test("installs all required models after acknowledging gated licenses", async ({
    page,
  }) => {
    const state = await mockApi(page, { models: MODELS });
    const downloads = await mockModelDownloads(page, state);
    await page.goto("/models");

    // Only models used by pipelines count; the failed ResNet-50 is not required.
    const installRequired = page.getByRole("button", {
      name: "Install required models (2)",
    });
    await installRequired.click();

    const dialog = page.getByRole("dialog", {
      name: "Additional action required",
    });
    await expect(dialog.getByRole("link", { name: "Gated VLM" })).toBeVisible();
    await dialog.getByRole("button", { name: "Proceed with install" }).click();

    await expect(
      page.getByText("2 models installed successfully."),
    ).toBeVisible();
    expect(downloads).toEqual([{ names: ["person-detection", "gated-vlm"] }]);
    await expect(
      page.getByRole("button", { name: "Install required models" }),
    ).toBeDisabled();
  });

  test("reports models rejected in a partially accepted install", async ({
    page,
  }) => {
    const state = await mockApi(page, { models: MODELS });
    const downloads = await mockModelDownloads(page, state, {
      "person-detection": "Model is already being downloaded",
    });
    await page.goto("/models");

    await page
      .getByRole("button", { name: "Install required models (2)" })
      .click();
    await page
      .getByRole("dialog", { name: "Additional action required" })
      .getByRole("button", { name: "Proceed with install" })
      .click();

    await expect(page.getByText("Model installed successfully.")).toBeVisible();
    await expect(
      page.getByText("person-detection: Model is already being downloaded"),
    ).toBeVisible();
    expect(downloads).toHaveLength(1);
    await expect(
      modelRow(page, "Gated VLM").getByText("Installed", { exact: true }),
    ).toBeVisible();
    await expect(
      modelRow(page, "Person Detection").getByText("Not Installed"),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Install required models (1)" }),
    ).toBeEnabled();
  });
});
