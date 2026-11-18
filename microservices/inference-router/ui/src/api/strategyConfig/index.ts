// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import request from "../request";

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
