// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { NextLoading } from "@/utils/loading";
import serviceManager from "@/utils/service-manager";
import axios, { AxiosInstance } from "axios";
import qs from "qs";
import i18n from "@/i18n";

const service: AxiosInstance = axios.create({
  baseURL: "/",
  timeout: 600000,
  headers: { "Content-Type": "application/json" },
});

const request = (
  config: Parameters<AxiosInstance["request"]>[0],
): Promise<any> => service.request(config);

let loadingRequests = 0;
const finishLoading = (showLoading?: boolean) => {
  if (!showLoading || loadingRequests === 0) return;
  loadingRequests--;
  if (loadingRequests === 0) NextLoading.done();
};

// request interceptor
service.interceptors.request.use(
  (config) => {
    if (config.type === "formData") {
      config.data = qs.stringify(config.data);
    } else if (config.type === "files") {
      config.headers!["Content-Type"] = "multipart/form-data";
    }

    if (config.showLoading) {
      if (loadingRequests === 0) NextLoading.start();
      loadingRequests++;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  },
);

// response interceptor
service.interceptors.response.use(
  (response) => {
    const { config } = response;
    finishLoading(config.showLoading);
    const res = response.data;
    if (config.showSuccessMsg) {
      const antNotification = serviceManager.getService("antNotification");

      if (antNotification)
        antNotification("success", i18n.global.t("common.success"), i18n.global.t(config.successMsg));
    }
    return Promise.resolve(res);
  },
  (error) => {
    finishLoading(error.config?.showLoading);
    if (axios.isCancel(error)) return Promise.reject(error);
    let errorMessage = "";
    const { detail = "" } = error.response?.data || {};
    if (error.message.indexOf("timeout") != -1) {
      errorMessage = "Timeout";
    } else if (detail) {
      errorMessage = typeof detail === "string" ? detail : JSON.stringify(detail);
    } else {
      errorMessage = error.message;
    }
    const antNotification = serviceManager.getService("antNotification");
    if (antNotification) antNotification("error", i18n.global.t("common.error"), errorMessage);

    return Promise.reject(error);
  },
);

export default request;
