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
