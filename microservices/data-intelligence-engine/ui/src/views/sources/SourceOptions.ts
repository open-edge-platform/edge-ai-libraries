// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import type { JsonObject, ModelOptions } from "../../api/console/type";
import { REMOTE_BACKEND, effectiveBackend, embeddingChoice } from "./embeddingModels";

export const instructionKeys = [
  "TYPE_HINTS",
  "DOMAIN",
  "GRANULARITY",
  "TITLE_RULES",
  "MERGE_STANCE",
  "RELATION_RULES",
  "ESCALATION_RULES",
] as const;
export const vectorDefaults = () => ({
  backend: "",
  model: "",
  device: "",
  apiBase: "",
  chunkSize: undefined as number | undefined,
  chunkOverlap: undefined as number | undefined,
  figureContext: undefined as number | undefined,
  maxImageTokens: undefined as number | undefined,
  framesPerClip: undefined as number | undefined,
});
export const sourceOptionsDefaults = () => ({
  vectorTypes: ["document"],
  vectors: {
    document: vectorDefaults(),
    image: vectorDefaults(),
    video: vectorDefaults(),
    audio: vectorDefaults(),
  },
  graphTypes: ["okf"],
  extractorUrl: "http://okf-extractor:8080",
  apiKey: "",
  timeout: 3600,
  trigger: "auto",
  debounce: 15,
  cron: "",
  timezone: "UTC",
  language: "",
  goal: "",
  instructions: Object.fromEntries(
    instructionKeys.map((key) => [key, ""]),
  ) as Record<(typeof instructionKeys)[number], string>,
});
export type SourceOptionsForm = ReturnType<typeof sourceOptionsDefaults>;
export const vectorMode = (
  types: string[],
): keyof SourceOptionsForm["vectors"] =>
  types.includes("document")
    ? "document"
    : types.includes("image")
      ? "image"
      : types.includes("video")
        ? "video"
        : "audio";
export const httpUrl = (value: string, message: string) => {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new Error(message);
  }
  if (!["http:", "https:"].includes(url.protocol)) throw new Error(message);
  return value.trim();
};
export const serializeSourceOptions = (
  type: string,
  form: SourceOptionsForm,
  t: (key: string) => string,
  modelData: Record<string, ModelOptions> = {},
): JsonObject => {
  const numberOption = (
    value: number,
    min: number,
    max = Infinity,
    integer = false,
  ) => {
    if (
      typeof value !== "number" ||
      !Number.isFinite(value) ||
      value < min ||
      value > max ||
      (integer && !Number.isSafeInteger(value))
    )
      throw new Error(t("console.invalidSourceNumber"));
    return value;
  };
  if (type === "object" || type === "sql") return {};
  if (type === "graph") {
    if (!form.graphTypes.includes("okf"))
      throw new Error(t("console.graphHint"));
    if (!form.graphTypes.includes("document"))
      return { asset_types: form.graphTypes };
    if (!["auto", "manual", "schedule"].includes(form.trigger))
      throw new Error(t("console.invalidSourceOptions"));
    let timezone = form.timezone.trim();
    if (form.trigger === "schedule") {
      const fields = form.cron.trim().split(/\s+/);
      const bounds = [
        [0, 59],
        [0, 23],
        [1, 31],
        [1, 12],
        [0, 7],
      ];
      if (fields.length !== 5) throw new Error(t("console.invalidSchedule"));
      fields.forEach((field, index) => {
        const [low, high] = bounds[index];
        for (const part of field.split(",")) {
          const match = /^(\*|\d+(?:-\d+)?)(?:\/(\d+))?$/.exec(part);
          if (!match) throw new Error(t("console.invalidSchedule"));
          const step = match[2] === undefined ? 1 : Number(match[2]);
          const range =
            match[1] === "*" ? [low, high] : match[1].split("-").map(Number);
          const start = range[0];
          const end = range[1] ?? (match[2] === undefined ? start : high);
          if (
            !Number.isSafeInteger(step) ||
            step <= 0 ||
            start < low ||
            start > end ||
            end > high
          )
            throw new Error(t("console.invalidSchedule"));
        }
      });
      try {
        if (!timezone) throw new Error();
        timezone = new Intl.DateTimeFormat("en", {
          timeZone: timezone,
        }).resolvedOptions().timeZone;
      } catch {
        throw new Error(t("console.invalidSchedule"));
      }
    }
    const extractor: JsonObject = {
      url: httpUrl(form.extractorUrl, t("console.invalidUrl")),
      timeout: numberOption(form.timeout, Number.MIN_VALUE),
      trigger:
        form.trigger === "auto"
          ? {
              mode: "auto",
              debounce_seconds: numberOption(form.debounce, 0, 86400),
            }
          : form.trigger === "schedule"
            ? {
                mode: "schedule",
                cron: form.cron.trim(),
                timezone,
              }
            : "manual",
    };
    if (form.apiKey.trim()) extractor.api_key = form.apiKey.trim();
    const options: JsonObject = {};
    if (form.language.trim()) options.language = form.language.trim();
    if (form.goal.trim()) options.goal = form.goal.trim();
    const instructions = Object.fromEntries(
      Object.entries(form.instructions)
        .filter(([, value]) => value.trim())
        .map(([key, value]) => [key, value.trim()]),
    );
    if (Object.keys(instructions).length) options.instructions = instructions;
    if (Object.keys(options).length) extractor.options = options;
    return { asset_types: form.graphTypes, external_extractor: extractor };
  }
  if (type !== "vector") throw new Error(t("console.invalidSourceOptions"));
  const types = form.vectorTypes;
  if (
    !types.length ||
    (types.length > 1 && (types.includes("video") || types.includes("document")))
  )
    throw new Error(t("console.incompatibleContent"));
  const mode = vectorMode(types);
  const vector = form.vectors[mode];
  const result: JsonObject = { asset_types: types };
  const embedding = modelData.embedding;
  const model = vector.model.trim();
  const backend = effectiveBackend(embedding, types, vector.backend);
  if (backend === REMOTE_BACKEND) {
    if (vector.backend) {
      if (!model) throw new Error(t("console.modelRequiredWithBackend"));
      result.embedding_backend = vector.backend;
      result.embedding_model = model;
    }
  } else {
    const choice = embeddingChoice(embedding, types);
    if (choice.status === "none") throw new Error(t("console.noCommonModel"));
    if (model) {
      if (!choice.candidates.includes(model))
        throw new Error(t("console.noCommonModel"));
      result.embedding_backend = backend;
      result.embedding_model = model;
    } else if (choice.status === "differ") {
      throw new Error(t("console.defaultModelsDiffer"));
    } else if (vector.backend) {
      result.embedding_backend = vector.backend;
    }
  }
  if (backend === REMOTE_BACKEND) {
    if (vector.apiBase.trim())
      result.embedding_api_base = httpUrl(
        vector.apiBase,
        t("console.invalidUrl"),
      );
  } else {
    if (vector.device) result.embedding_device = vector.device;
    if (mode !== "video" && vector.maxImageTokens != null)
      result.max_image_tokens = numberOption(
        vector.maxImageTokens,
        1,
        Infinity,
        true,
      );
  }
  if (mode === "document") {
    if (
      vector.chunkSize != null &&
      vector.chunkOverlap != null &&
      vector.chunkOverlap >= vector.chunkSize
    )
      throw new Error(t("console.invalidOverlap"));
    if (vector.chunkSize != null)
      result.chunk_size = numberOption(vector.chunkSize, 1, Infinity, true);
    if (vector.chunkOverlap != null)
      result.chunk_overlap = numberOption(
        vector.chunkOverlap,
        0,
        Infinity,
        true,
      );
    if (vector.figureContext != null)
      result.figure_context_chars = numberOption(
        vector.figureContext,
        0,
        Infinity,
        true,
      );
  }
  if (mode === "video" && vector.framesPerClip != null)
    result.frames_per_clip = numberOption(
      vector.framesPerClip,
      1,
      Infinity,
      true,
    );
  return result;
};
