// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import type { TableColumnsType } from "ant-design-vue";
import type { Source } from "@/api/console/type";

const getTableColumns = (
  t: (key: string) => string,
): TableColumnsType<Source> => [
  { title: t("console.name"), key: "name", dataIndex: "name", width: 240 },
  { title: t("console.type"), key: "type", dataIndex: "type", width: 100 },
  { title: t("console.database"), key: "database", width: 200 },
  { title: t("console.pools"), key: "pools", width: 220 },
  { title: t("console.status"), key: "status", width: 140 },
  { title: t("console.actions"), key: "actions", width: 190, fixed: "right" },
];
export default getTableColumns;
