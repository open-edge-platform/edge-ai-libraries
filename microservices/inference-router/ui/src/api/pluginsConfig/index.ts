// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import request from "../request";

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
