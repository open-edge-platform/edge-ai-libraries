// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import request from "../request";
import type {
  CompressorTrafficMetrics,
  RouterTrafficMetrics,
} from "@/views/trafficOverview/type";

export const getRouterTraffic = () =>
  request<RouterTrafficMetrics, RouterTrafficMetrics>({
    url: "/v1/metrics",
    method: "get",
  });

export const getCompressorTraffic = () =>
  request<CompressorTrafficMetrics, CompressorTrafficMetrics>({
    url: "/v1/plugins/compressor",
    method: "get",
  });
