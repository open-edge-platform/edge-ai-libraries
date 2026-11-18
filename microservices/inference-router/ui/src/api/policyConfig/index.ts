// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import request from "../request";

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

export const getRouterRouting = () => {
  return request({
    url: "/v1/routing",
    method: "get",
  });
};

export const updateRouterRouting = (data: object) => {
  return request({
    url: "/v1/routing",
    method: "post",
    data,
    showLoading: true,
  });
};
