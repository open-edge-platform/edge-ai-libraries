// Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0
import type { ModelOptions } from "../../api/console/type";

export interface RerankerOverrides {
  model_id?: string;
  backend?: string;
}

export const findRerankerModel = (
  options: ModelOptions | undefined,
  model: RerankerOverrides,
) => options?.models.find((item) =>
  item.name === model.model_id,
);

export const isMediaReranker = (
  options: ModelOptions | undefined,
  model: RerankerOverrides,
  media: boolean,
) =>
  !!findRerankerModel(options, model)?.media ||
  (!!model.model_id && model.model_id === options?.media_model_id) ||
  (!model.model_id &&
    (media ||
      options?.model_id === options?.media_model_id ||
      !!findRerankerModel(options, { model_id: options?.model_id })?.media));

export const inferRerankerBackend = (
  options: ModelOptions | undefined,
  model: RerankerOverrides,
  media: boolean,
) =>
  model.backend ||
  (isMediaReranker(options, model, media)
    ? options?.media_backend
    : options?.backend);
