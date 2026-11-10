// Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0
import type { ModelOptions } from "../../api/console/type";

export interface RerankerOverrides {
  model_id?: string;
  model_path?: string;
  backend?: string;
}

export const findRerankerModel = (
  options: ModelOptions | undefined,
  model: RerankerOverrides,
) => options?.models.find((item) =>
  model.model_path
    ? item.path === model.model_path || item.name === model.model_path
    : item.name === model.model_id,
);

export const inferRerankerBackend = (
  options: ModelOptions | undefined,
  model: RerankerOverrides,
  media: boolean,
) =>
  model.backend ||
  findRerankerModel(options, model)?.backend ||
  ((model.model_id && model.model_id === options?.media_model_id) ||
  (!model.model_id && media)
    ? options?.media_backend || "openvino_vl"
    : options?.backend);
