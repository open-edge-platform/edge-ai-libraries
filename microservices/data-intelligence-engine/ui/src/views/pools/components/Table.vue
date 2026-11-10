<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <a-card :bordered="false" class="table-container">
    <div class="header-wrap">
      <div class="title-wrap">
        <span>{{ $t("console.pools") }}</span>
        <a-tag>{{ tableData.length }}</a-tag>
      </div>
      <a-space wrap>
        <a-input-search
          v-model:value="searchName"
          allowClear
          :placeholder="$t('console.search')"
          class="search-input"
        />
        <a-button type="primary" @click="handleCreate">
          <template #icon><PlusOutlined /></template>
          {{ $t("console.createPool") }}
        </a-button>
      </a-space>
    </div>
    <ConsoleTable
      :columns="tableColumns"
      :data-source="tableList"
      row-key="id"
      :scroll="{ x: 1050 }"
      :reset-key="searchName"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'name'">
          <div class="name-wrap">
            <div class="pool-icon"><ApartmentOutlined /></div>
            <div>
              <a :title="record.name" @click="handleView(record.id)">{{ record.name }}</a>
              <div class="id-wrap" :title="record.id">{{ record.id }}</div>
            </div>
          </div>
        </template>
        <template v-else-if="column.key === 'assets'">
          <span class="asset-number">{{ record.asset_ids.length }}</span>
        </template>
        <template v-else-if="column.key === 'sources'">
          <div class="source-list" :title="sourceSummary(record)">
            <div
              v-for="binding in record.source_statuses.slice(0, 1)"
              :key="binding.source_id"
              class="source-item"
            >
              <span>
                {{
                  libraryData.sources.find(
                    (source) => source.id === binding.source_id,
                  )?.name || binding.source_id
                }}
              </span>
              <StatusTag :value="binding.display_status" />
            </div>
            <a-tooltip v-if="record.source_statuses.length > 1" :title="sourceSummary(record)">
              <a-tag :bordered="false">+{{ record.source_statuses.length - 1 }}</a-tag>
            </a-tooltip>
          </div>
        </template>
        <template v-else-if="column.key === 'status'">
          <StatusTag :value="record.display_status" />
        </template>
        <template v-else-if="column.key === 'operation'">
          <a-space>
            <a-button
              type="primary"
              ghost
              size="small"
              @click="handleView(record.id)"
            >
              {{ $t("console.manage") }}
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
import { ApartmentOutlined, PlusOutlined } from "@ant-design/icons-vue";
import { requestAssetPoolDelete } from "@/api/console";
import type { AssetPool, Library } from "@/api/console/type";
import StatusTag from "../../../components/StatusTag.vue";
import getTableColumns from "../ColumnsList";
import ConsoleTable from "../../../components/ConsoleTable.vue";
const props = defineProps<{ tableData: AssetPool[]; libraryData: Library }>();
const emit = defineEmits<{ create: []; view: [id: string]; search: [] }>();
const handleCreate = () => emit("create");
const handleView = (id: string) => emit("view", id);
const { t } = useI18n();
const searchName = ref("");
const tableColumns = computed(() => getTableColumns(t));
const sourceSummary = (pool: AssetPool) => pool.source_statuses.map((binding) => {
  const name = props.libraryData.sources.find((source) => source.id === binding.source_id)?.name || binding.source_id;
  return `${name}: ${t(`console.${binding.display_status}`)}`;
}).join("; ");
const tableList = computed(() =>
  props.tableData.filter((item) =>
    `${item.name} ${item.id}`
      .toLowerCase()
      .includes(searchName.value.toLowerCase()),
  ),
);
const handleDelete = (id: string, name: string) => {
  Modal.confirm({
    title: t("common.delete"),
    content: t("console.deletePool", { name }),
    okType: "danger",
    okText: t("common.confirm"),
    cancelText: t("common.cancel"),
    async onOk() {
      await requestAssetPoolDelete(props.libraryData.name, id);
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
  padding: 20px 24px;
  gap: 16px;
  flex-wrap: wrap;
}
.title-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  > span:first-child {
    font-size: 16px;
    font-weight: 600;
    color: var(--font-main-color);
  }
}
.search-input {
  width: 240px;
}
.name-wrap {
  display: flex;
  align-items: center;
  gap: 12px;
  > div:last-child {
    min-width: 0;
  }
  a {
    display: block;
    max-width: 230px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-weight: 500;
    color: var(--font-main-color);
    text-decoration: none;
    &:hover {
      color: var(--color-primary-second);
    }
  }
}
.pool-icon {
  width: 30px;
  height: 32px;
  display: grid;
  place-items: center;
  font-size: 18px;
  background: color-mix(in srgb, var(--color-purple) 8%, transparent);
  color: var(--color-purple);
  border-radius: 8px;
}
.id-wrap {
  margin-top: 1px;
  font-size: 12px;
  color: var(--font-info-color);
  font-family: monospace;
  max-width: 230px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.source-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
}
.source-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  > span:first-child {
    max-width: 140px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
}
.asset-number {
  font-size: 16px;
  font-weight: 500;
}
</style>
