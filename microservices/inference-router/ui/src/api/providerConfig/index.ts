// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import request from "../request";

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
