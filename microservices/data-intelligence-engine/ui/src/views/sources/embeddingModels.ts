// Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0
import type { ModelOptions } from "../../api/console/type";

export const LOCAL_BACKEND = "local_openvino";
export const REMOTE_BACKEND = "remote_openai_compatible";

export interface EmbeddingChoice {
  // Ready local models that embed every selected content type.
  candidates: string[];
  // The engine default when every selected type shares one usable default.
  defaultModel: string;
  // default: use the default; differ: the user must pick; none: nothing fits.
  status: "default" | "differ" | "none";
}

const isLocal = (path?: string) => !/^https?:/i.test(path || "");

export const embeddingChoice = (
  options: ModelOptions | undefined,
  types: string[],
): EmbeddingChoice => {
  const candidates = (options?.models || [])
    .filter(
      (model) =>
        model.ready &&
        isLocal(model.path) &&
        types.every((type) => model.supported_asset_types?.includes(type)),
    )
    .map((model) => model.name);
  if (!candidates.length) return { candidates, defaultModel: "", status: "none" };
  const defaults = [
    ...new Set(types.map((type) => options?.defaults?.[type]?.model_id || "")),
  ];
  const [only] = defaults;
  if (defaults.length === 1 && only && candidates.includes(only))
    return { candidates, defaultModel: only, status: "default" };
  return { candidates, defaultModel: "", status: "differ" };
};

// What an unset backend or device resolves to for the selected content types:
// the shared value, or every distinct value when the types disagree.
export const inheritedDefault = (
  options: ModelOptions | undefined,
  types: string[],
  field: "backend" | "device" | "model_id",
) =>
  [
    ...new Set(
      types
        .map((type) => options?.defaults?.[type]?.[field] || "")
        .filter(Boolean),
    ),
  ].join(" / ");

// An unset backend inherits the engine default, which only differs for documents.
export const effectiveBackend = (
  options: ModelOptions | undefined,
  types: string[],
  backend: string,
) =>
  backend ||
  (types.length === 1 && types[0] === "document"
    ? options?.defaults?.document?.backend
    : "") ||
  LOCAL_BACKEND;

// Remote embedding only serves documents; any media type needs a local model.
export const backendChoices = (types: string[]) =>
  types.length === 1 && types[0] === "document"
    ? [LOCAL_BACKEND, REMOTE_BACKEND]
    : [LOCAL_BACKEND];
