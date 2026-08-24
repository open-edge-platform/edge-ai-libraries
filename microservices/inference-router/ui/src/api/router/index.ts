// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import request from "../request";

export const getRouterHealth = () => {
  return request({
    url: "/health",
    method: "get",
  });
};

export const getRouterMetrics = () => {
  return request({
    url: "/v1/metrics",
    method: "get",
  });
};

export const resetRouterMetrics = () => {
  return request({
    url: "/v1/metrics/reset",
    method: "post",
    showLoading: true,
    showSuccessMsg: true,
    successMsg: "router.resetSuccess",
  });
};

export const reloadRouterConfig = () => {
  return request({
    url: "/v1/config/reload",
    method: "post",
    showLoading: true,
  });
};

export const getRouterProviders = () => {
  return request({
    url: "/v1/providers",
    method: "get",
  });
};

export const getRouterProvider = (name: string) => {
  return request({
    url: `/v1/providers/${name}`,
    method: "get",
  });
};

export const updateRouterProvider = (name: string, data: object) => {
  return request({
    url: `/v1/providers/${name}`,
    method: "post",
    data,
    showLoading: true,
  });
};

export const deleteRouterProvider = (name: string) => {
  return request({
    url: `/v1/providers/${name}`,
    method: "delete",
    showLoading: true,
  });
};

export const getRouterPolicies = () => {
  return request({
    url: "/v1/policies",
    method: "get",
  });
};

export const getRouterPolicy = (name: string) => {
  return request({
    url: `/v1/policies/${name}`,
    method: "get",
  });
};

export const updateRouterPolicy = (name: string, data: object) => {
  return request({
    url: `/v1/policies/${name}`,
    method: "post",
    data,
    showLoading: true,
  });
};

export const deleteRouterPolicy = (name: string) => {
  return request({
    url: `/v1/policies/${name}`,
    method: "delete",
    showLoading: true,
  });
};

export const getRouterStrategies = () => {
  return request({
    url: "/v1/strategies",
    method: "get",
  });
};

export const getRouterStrategy = (name: string) => {
  return request({
    url: `/v1/strategies/${name}`,
    method: "get",
  });
};

export const updateRouterStrategy = (name: string, data: object) => {
  return request({
    url: `/v1/strategies/${name}`,
    method: "post",
    data,
    showLoading: true,
  });
};

export const deleteRouterStrategy = (name: string) => {
  return request({
    url: `/v1/strategies/${name}`,
    method: "delete",
    showLoading: true,
  });
};

export const getRouterPlugins = () => {
  return request({
    url: "/v1/plugins",
    method: "get",
  });
};

export const getRouterPluginNodes = () => {
  return request({
    url: "/v1/plugins/nodes",
    method: "get",
  });
};

export const getRouterPluginNode = (node: string) => {
  return request({
    url: `/v1/plugins/${node}`,
    method: "get",
  });
};

export const resetRouterPluginNode = (node: string) => {
  return request({
    url: `/v1/plugins/${node}/reset`,
    method: "post",
    showLoading: true,
  });
};

export const getRouterPlugin = (node: string, name: string) => {
  return request({
    url: `/v1/plugins/${node}/${name}`,
    method: "get",
  });
};

export const updateRouterPlugin = (
  node: string,
  name: string,
  data: object,
) => {
  return request({
    url: `/v1/plugins/${node}/${name}`,
    method: "post",
    data,
    showLoading: true,
  });
};

export const deleteRouterPlugin = (node: string, name: string) => {
  return request({
    url: `/v1/plugins/${node}/${name}`,
    method: "delete",
    showLoading: true,
  });
};

export const resetRouterPlugin = (node: string, name: string) => {
  return request({
    url: `/v1/plugins/${node}/${name}/reset`,
    method: "post",
    showLoading: true,
  });
};
