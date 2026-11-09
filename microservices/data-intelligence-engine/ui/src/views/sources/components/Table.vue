<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <a-card :bordered="false" class="table-container">
    <div class="header-wrap">
      <a-tabs v-model:activeKey="sourceType" class="type-tabs">
        <a-tab-pane key="all">
          <template #tab>
            <span class="tab-title">
              <AppstoreOutlined />
              {{ $t("common.all") }}
              <a-tag :bordered="false">{{ tableData.length }}</a-tag>
            </span>
          </template>
        </a-tab-pane>
        <a-tab-pane v-for="item in sourceTabs" :key="item.type">
          <template #tab>
            <span class="tab-title">
              <component :is="item.icon" />
              {{ $t(`console.${item.type}Source`) }}
              <a-tag :bordered="false">
                {{
                  tableData.filter((source) => source.type === item.type).length
                }}
              </a-tag>
            </span>
          </template>
        </a-tab-pane>
      </a-tabs>
      <a-button type="primary" @click="handleCreate">
        <template #icon><PlusOutlined /></template>
        {{ $t("console.createSource") }}
      </a-button>
    </div>
    <div class="filter-wrap">
      <span>{{ $t("common.total") }}: {{ tableData.length }}</span>
      <a-input-search
        v-model:value="searchName"
        allowClear
        :placeholder="$t('console.search')"
        class="search-input"
      />
    </div>
    <ConsoleTable
      :columns="tableColumns"
      :data-source="tableList"
      row-key="id"
      :scroll="{ x: 1100 }"
      :reset-key="`${sourceType}:${searchName}`"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'name'">
          <div class="name-wrap">
            <div class="source-icon" :class="record.type">
              <DeploymentUnitOutlined />
            </div>
            <div>
              <div class="name-line">
                <a :title="record.name" @click="handleView(record.id)">{{
                  record.name
                }}</a>
                <a-tag
                  v-if="record.id === libraryData.default_content_source_id"
                  class="theme-tag-primary"
                  :bordered="false"
                >
                  {{ $t("console.defaultContent") }}
                </a-tag>
              </div>
              <div class="id-wrap" :title="record.id">{{ record.id }}</div>
            </div>
          </div>
        </template>
        <template v-else-if="column.key === 'type'">
          <a-tag
            v-if="record.type === 'vector'"
            class="theme-tag-primary"
            :bordered="false"
          >
            {{ $t("console.vectorSource") }}
          </a-tag>
          <a-tag
            v-else-if="record.type === 'graph'"
            class="theme-tag-purple"
            :bordered="false"
          >
            {{ $t("console.graphSource") }}
          </a-tag>
          <a-tag v-else :bordered="false">
            {{ $t(`console.${record.type}Source`) }}
          </a-tag>
        </template>
        <template v-else-if="column.key === 'database'">
          <span>{{ record.database_id }}</span>
          <div class="id-wrap">{{ record.collection_name }}</div>
        </template>
        <template v-else-if="column.key === 'pools'">
          <div class="binding-list">
            <div
              v-for="{ pool, binding } in getSourceBindings(record.id)"
              :key="pool.id"
              class="pool-binding"
              :title="`${pool.name || pool.id} · ${binding.serving_state}`"
            >
              <span class="pool-name">{{ pool.name || pool.id }}</span>
              <span class="pool-state" :class="binding.serving_state">
                {{ binding.serving_state }}
              </span>
            </div>
            <span v-if="record.type === 'object'" class="muted-wrap">
              {{ $t("console.libraryWide") }}
            </span>
            <span
              v-else-if="!getSourceBindings(record.id).length"
              class="muted-wrap"
              >—</span
            >
          </div>
        </template>
        <template v-else-if="column.key === 'status'">
          <a-tooltip :title="record.reconciliation_error">
            <a-badge
              v-if="record.reconciled"
              status="success"
              :text="$t('console.reconciled')"
            />
            <a-badge v-else status="error" :text="$t('console.unreconciled')" />
          </a-tooltip>
        </template>
        <template v-else-if="column.key === 'actions'">
          <a-space>
            <a-button
              size="small"
              type="primary"
              ghost
              @click="handleView(record.id)"
            >
              {{ $t("common.details") }}
            </a-button>
            <a-button
              danger
              size="small"
              @click="handleDelete(record.id, record.name)"
            >
              {{ $t("common.delete") }}
            </a-button>
          </a-space>
        </template>
      </template>
    </ConsoleTable>
  </a-card>
</template>
<script lang="ts" setup name="Table">
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import { Modal } from "ant-design-vue";
import {
  AppstoreOutlined,
  DatabaseOutlined,
  DeploymentUnitOutlined,
  FileOutlined,
  PlusOutlined,
  ShareAltOutlined,
} from "@ant-design/icons-vue";
import { requestSourceDelete } from "@/api/console";
import type { Library, Source } from "@/api/console/type";
import getTableColumns from "../ColumnsList";
import ConsoleTable from "../../../components/ConsoleTable.vue";
const props = defineProps<{ tableData: Source[]; libraryData: Library }>();
const emit = defineEmits<{ create: []; search: []; view: [id: string] }>();
const handleCreate = () => emit("create");
const handleView = (id: string) => emit("view", id);
const { t } = useI18n();
const sourceType = ref("all");
const sourceTabs = [
  { type: "vector", icon: DeploymentUnitOutlined },
  { type: "graph", icon: ShareAltOutlined },
  { type: "object", icon: FileOutlined },
  { type: "sql", icon: DatabaseOutlined },
];
const searchName = ref("");
const tableColumns = computed(() => getTableColumns(t));
const getSourceBindings = (id: string) =>
  props.libraryData.asset_pools.flatMap((pool) =>
    pool.source_statuses
      .filter((binding) => binding.source_id === id)
      .map((binding) => ({ pool, binding })),
  );
const tableList = computed(() =>
  props.tableData.filter(
    (item) =>
      (sourceType.value === "all" || sourceType.value === item.type) &&
      `${item.name} ${item.id}`
        .toLowerCase()
        .includes(searchName.value.toLowerCase()),
  ),
);
const handleDelete = (id: string, name: string) => {
  Modal.confirm({
    title: t("common.delete"),
    content: t("console.deleteSource", { name }),
    okType: "danger",
    okText: t("common.confirm"),
    cancelText: t("common.cancel"),
    async onOk() {
      await requestSourceDelete(props.libraryData.name, id);
      emit("search");
    },
  });
};
</script>
<style scoped lang="less">
.table-container {
  background: var(--bg-content-color);
  border: 1px solid var(--border-main-color);
  border-radius: 8px;
  :deep(.intel-card-body) {
    padding: 0;
  }
}
.header-wrap {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
  padding: 6px 24px 0;
  border-bottom: 1px solid var(--border-main-color);
  flex-wrap: wrap;
}
.type-tabs {
  flex: 1;
  min-width: 0;
  :deep(.intel-tabs-nav) {
    margin: 0;
    &::before {
      border: 0;
    }
    .tab-title {
      display: inline-flex;
      align-items: center;
      gap: 8px;
    }
  }
  :deep(.intel-tabs-tab) {
    padding: 16px 0;
  }
}
.filter-wrap {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 18px 24px;
  > span {
    color: var(--font-info-color);
    font-size: 12px;
  }
}
.search-input {
  width: 260px;
}
.name-wrap {
  display: flex;
  align-items: center;
  gap: 12px;
  > div:last-child {
    min-width: 0;
  }
  a {
    font-weight: 500;
    color: var(--font-main-color);
    text-decoration: none;
    &:hover {
      color: var(--color-primary-second);
    }
    .name-line {
      display: flex;
      align-items: center;
      gap: 4px;
      a {
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .intel-tag {
        flex-shrink: 0;
        margin: 0;
        font-size: 10px;
      }
    }
  }
}
.source-icon {
  width: 30px;
  height: 32px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: var(--bg-card-color);
  font-size: 17px;
  color: var(--color-primary-second);
  &.graph {
    color: var(--color-purple);
  }
  &.object {
    color: var(--color-success);
  }
}
.id-wrap {
  font-size: 12px;
  color: var(--font-info-color);
  font-family: monospace;
  margin: 1px 0;
  max-width: 230px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.muted-wrap {
  color: var(--font-info-color);
  font-size: 12px;
}
.binding-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.pool-binding {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  max-width: 100%;
  padding: 1px 6px;
  border: 1px solid var(--border-main-color);
  border-radius: 4px;
  background: var(--bg-card-color);
  font-size: 11px;
  line-height: 18px;
}
.pool-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pool-state {
  flex-shrink: 0;
  padding-inline-start: 5px;
  border-inline-start: 1px solid var(--border-main-color);
  color: var(--font-info-color);
  font-size: 10px;
  &.SERVING {
    color: var(--color-success);
  }
  &.PREPARING {
    color: var(--color-primary-second);
  }
}
</style>
