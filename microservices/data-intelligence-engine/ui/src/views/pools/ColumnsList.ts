// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import type { TableColumnsType } from "ant-design-vue";
import type { AssetPool } from "@/api/console/type";

const getTableColumns = (
  t: (key: string) => string,
): TableColumnsType<AssetPool> => [
  { title: t("console.name"), key: "name", dataIndex: "name", width: 180 },
  { title: t("console.assets"), key: "assets", width: 90 },
  { title: t("console.sources"), key: "sources", width: 240 },
  { title: t("console.status"), key: "status", width: 140 },
  {
    title: t("console.revision"),
    key: "revision",
    dataIndex: "revision",
    width: 90,
  },
  { title: t("console.actions"), key: "operation", width: 190, fixed: "right" },
];
export default getTableColumns;
