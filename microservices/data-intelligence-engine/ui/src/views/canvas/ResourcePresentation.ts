// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import type { Component } from "vue";
import {
  ApartmentOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  UploadOutlined,
} from "@ant-design/icons-vue";
import type { NodeKind } from "./Type";

interface ResourceCategory {
  kind: NodeKind;
  label: string;
  createLabel: string;
  icon: Component;
  createIcon: Component;
  color: string;
}

export const resourceCategories: Record<NodeKind, ResourceCategory> = {
  asset: {
    kind: "asset",
    label: "assets",
    createLabel: "upload",
    icon: FileTextOutlined,
    createIcon: UploadOutlined,
    color: "var(--color-primary-second)",
  },
  pool: {
    kind: "pool",
    label: "pools",
    createLabel: "createPool",
    icon: ApartmentOutlined,
    createIcon: ApartmentOutlined,
    color: "var(--color-success)",
  },
  source: {
    kind: "source",
    label: "sources",
    createLabel: "createSource",
    icon: DatabaseOutlined,
    createIcon: DatabaseOutlined,
    color: "var(--color-purple)",
  },
};

export const resourceCategoryList = Object.values(resourceCategories);
