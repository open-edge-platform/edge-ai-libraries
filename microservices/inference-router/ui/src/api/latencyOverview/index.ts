// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import request from "../request";

export const getRouterMetrics = () => {
  return request({
    url: "/v1/metrics",
    method: "get",
  });
};
