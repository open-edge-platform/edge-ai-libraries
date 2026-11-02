// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import request from "../request";
import type {
  RouterPromptPayload,
  RouterPromptUpdatePayload,
} from "@/types/router";

export const getRouterPrompts = () => {
  return request({
    url: "/v1/prompts",
    method: "get",
  });
};

export const getRouterPromptDetail = (idx: number) => {
  return request({
    url: `/v1/prompts/${idx}`,
    method: "get",
  });
};

export const createRouterPrompt = (data: RouterPromptPayload) => {
  return request({
    url: "/v1/prompts",
    method: "post",
    data,
    showLoading: true,
  });
};

export const updateRouterPrompt = (data: RouterPromptUpdatePayload) => {
  return request({
    url: "/v1/prompts",
    method: "put",
    data,
    showLoading: true,
  });
};

export const deleteRouterPrompt = (idx: number) => {
  return request({
    url: `/v1/prompts/${idx}`,
    method: "delete",
    showLoading: true,
  });
};
