// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import request from "../request";
import type { AxiosProgressEvent } from "axios";
import type { Asset, IngestResult } from "./type";

export const getHealth = () => {
  return request({
    url: "/health",
    method: "get",
  });
};

export const getAssetLibraryList = (showLoading = true) => {
  return request({
    url: "/v1/libraries",
    method: "get",
    showLoading,
  });
};

export const requestAssetLibraryCreate = (data: Object) => {
  return request({
    url: "/v1/libraries",
    method: "post",
    data,
    showSuccessMsg: true,
    successMsg: "console.saved",
  });
};

export const requestAssetLibraryDelete = (name: string) => {
  return request({
    url: `/v1/libraries/${name}`,
    method: "delete",
    showSuccessMsg: true,
    successMsg: "console.saved",
  });
};

export const getAssetList = (
  name: string,
  params: Object,
  showLoading = false,
) => {
  return request({
    url: `/v1/libraries/${name}/assets`,
    method: "get",
    params,
    showLoading,
  });
};

export const requestAssetDelete = (name: string, data: Object) => {
  return request({
    url: `/v1/libraries/${name}/assets`,
    method: "delete",
    data,
    showSuccessMsg: true,
    successMsg: "console.saved",
  });
};

export const requestAssetUpload = (
  name: string,
  path: string,
  data: File,
  onUploadProgress: (event: AxiosProgressEvent) => void,
) => {
  return request({
    url: `/v1/libraries/${name}/uploads/${path}`,
    method: "put",
    data,
    headers: { "Content-Type": "application/octet-stream" },
    onUploadProgress,
  });
};

export const requestAssetCreate = (
  name: string,
  data: Object,
): Promise<IngestResult> => {
  return request({
    url: `/v1/libraries/${name}/assets`,
    method: "post",
    data,
  });
};

export const getAssetMaterialization = (
  name: string,
  ids: string[],
): Promise<Record<string, Asset["materialization"]>> => {
  return request({
    url: `/v1/libraries/${name}/assets/materialization`,
    method: "get",
    params: { asset_ids: ids },
    paramsSerializer: { indexes: null },
  });
};

export const requestAssetPoolCreate = (name: string, data: Object) => {
  return request({
    url: `/v1/libraries/${name}/asset_pools`,
    method: "post",
    data,
    showSuccessMsg: true,
    successMsg: "console.saved",
  });
};

export const requestAssetPoolDelete = (name: string, id: string) => {
  return request({
    url: `/v1/libraries/${name}/asset_pools/${id}`,
    method: "delete",
    showSuccessMsg: true,
    successMsg: "console.saved",
  });
};

export const requestAssetPoolSourcesUpdate = (
  name: string,
  id: string,
  data: Object,
) => {
  return request({
    url: `/v1/libraries/${name}/asset_pools/${id}/sources`,
    method: "put",
    data,
    showSuccessMsg: true,
    successMsg: "console.saved",
  });
};

export const requestAssetPoolAssetsCreate = (
  name: string,
  id: string,
  data: Object,
) => {
  return request({
    url: `/v1/libraries/${name}/asset_pools/${id}/assets`,
    method: "post",
    data,
    showSuccessMsg: true,
    successMsg: "console.saved",
  });
};

export const requestSourceServingUpdate = (
  name: string,
  poolId: string,
  sourceId: string,
  data: Object,
) => {
  return request({
    url: `/v1/libraries/${name}/asset_pools/${poolId}/sources/${sourceId}`,
    method: "patch",
    data,
    showSuccessMsg: true,
    successMsg: "console.saved",
  });
};

export const requestExtractionCreate = (
  name: string,
  poolId: string,
  data: Object,
) => {
  return request({
    url: `/v1/libraries/${name}/asset_pools/${poolId}/extractions`,
    method: "post",
    data,
    showSuccessMsg: true,
    successMsg: "console.saved",
  });
};

export const getAssetPoolGraph = (name: string, id: string) => {
  return request({
    url: `/v1/libraries/${name}/asset_pools/${id}/graph`,
    method: "get",
    showLoading: true,
  });
};

export const requestSourceCreate = (name: string, data: Object) => {
  return request({
    url: `/v1/libraries/${name}/sources`,
    method: "post",
    data,
    showSuccessMsg: true,
    successMsg: "console.saved",
  });
};

export const requestSourceDelete = (name: string, id: string) => {
  return request({
    url: `/v1/libraries/${name}/sources/${id}`,
    method: "delete",
    showSuccessMsg: true,
    successMsg: "console.saved",
  });
};

export const getDatabaseList = () => {
  return request({
    url: "/v1/databases",
    method: "get",
    showLoading: true,
  });
};

export const getDatabaseBackendList = () => {
  return request({
    url: "/v1/databases/backends",
    method: "get",
    showLoading: true,
  });
};

export const requestDatabaseCreate = (data: Object) => {
  return request({
    url: "/v1/databases",
    method: "post",
    data,
    showSuccessMsg: true,
    successMsg: "console.saved",
  });
};

export const requestDatabaseUpdate = (id: string, data: Object) => {
  return request({
    url: `/v1/databases/${id}`,
    method: "patch",
    data,
    showSuccessMsg: true,
    successMsg: "console.saved",
  });
};

export const requestDatabaseDelete = (id: string) => {
  return request({
    url: `/v1/databases/${id}`,
    method: "delete",
    showSuccessMsg: true,
    successMsg: "console.saved",
  });
};

export const requestDatabaseCheck = (id: string) => {
  return request({
    url: `/v1/databases/${id}/check`,
    method: "post",
  });
};

export const getModelDevices = (): Promise<string[]> => {
  return request({
    url: "/v1/models/devices",
    method: "get",
  });
};

export const getModelList = () => {
  return request({
    url: "/v1/models",
    method: "get",
    showLoading: true,
  });
};

export const requestRetrieval = (data: Object, signal?: AbortSignal) => {
  return request({
    url: "/v1/retrieve",
    method: "post",
    data,
    signal,
  });
};

export const blobUrl = "/v1/blob";
