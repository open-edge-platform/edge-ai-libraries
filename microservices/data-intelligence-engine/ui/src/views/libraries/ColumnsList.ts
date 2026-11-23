// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import type { TableColumnsType } from "ant-design-vue";
import type { Library } from "@/api/console/type";

const getTableColumns = (
  t: (key: string) => string,
): TableColumnsType<Library> => [
  { title: t("console.name"), key: "name", dataIndex: "name", width: 260 },
  { title: t("console.databases"), key: "databases", width: 220 },
  { title: t("console.pools"), key: "pools", width: 100 },
  { title: t("console.sources"), key: "sources", width: 100 },
  {
    title: t("console.assets"),
    key: "asset_count",
    dataIndex: "asset_count",
    width: 100,
  },
  {
    title: t("console.documents"),
    key: "document_count",
    dataIndex: "document_count",
    width: 100,
  },
  {
    title: t("console.chunks"),
    key: "chunk_count",
    dataIndex: "chunk_count",
    width: 100,
  },

  { title: t("console.actions"), key: "operation", width: 280, fixed: "right" },
];
export default getTableColumns;
