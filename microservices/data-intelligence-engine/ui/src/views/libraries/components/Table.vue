<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <a-card :bordered="false" class="table-container">
    <div class="header-wrap">
      <div class="title-wrap">
        <span class="title">{{ $t("console.libraries") }}</span>
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
          {{ $t("console.createLibrary") }}
        </a-button>
      </a-space>
    </div>
    <ConsoleTable
      :columns="tableColumns"
      :data-source="tableList"
      row-key="id"
      :scroll="{ x: 1300 }"
      :row-class-name="rowClassName"
      :reset-key="searchName"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'name'">
          <div class="name-wrap">
            <div class="resource-icon"><DatabaseOutlined /></div>
            <div class="name-content">
              <a
                class="click-link"
                :title="record.name"
                @click="handleSelect(record.name)"
              >
                {{ record.name }}
              </a>
              <div class="description" :title="record.id">
                {{ record.id }}
              </div>
              <div
                v-if="record.description"
                class="description"
                :title="record.description"
              >
                {{ record.description }}
              </div>
            </div>
            <a-tooltip
              v-if="record.name === selectedLibrary"
              :title="$t('console.currentLibrary')"
            >
              <CheckCircleFilled class="selected-icon" />
            </a-tooltip>
          </div>
        </template>
        <template v-else-if="column.key === 'databases'">
          <a-tag
            v-if="record.content_database"
            class="database-tag"
            :bordered="false"
          >
            {{ record.content_database }}
          </a-tag>
          <span v-else>—</span>
        </template>
        <template v-else-if="column.key === 'pools'">
          {{ record.asset_pools.length }}
        </template>
        <template v-else-if="column.key === 'sources'">
          {{ record.sources.length }}
        </template>
        <template v-else-if="column.key === 'operation'">
          <a-space>
            <a-button
              size="small"
              :disabled="record.name === selectedLibrary"
              @click="handleSelectLibrary(record.name)"
            >
              {{ $t("console.select") }}
            </a-button>
            <a-button
              size="small"
              type="primary"
              ghost
              @click="handleSelect(record.name)"
            >
              {{ $t("console.upload") }}
            </a-button>
            <a-button danger size="small" @click="handleDelete(record.name)">
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
  CheckCircleFilled,
  DatabaseOutlined,
  PlusOutlined,
} from "@ant-design/icons-vue";
import { requestAssetLibraryDelete } from "@/api/console";
import type { Library } from "@/api/console/type";
import getTableColumns from "../ColumnsList";
import ConsoleTable from "../../../components/ConsoleTable.vue";
const props = defineProps<{ tableData: Library[]; selectedLibrary?: string }>();
const emit = defineEmits<{
  create: [];
  select: [name: string];
  "select-library": [name: string];
  search: [];
  deleted: [name: string];
}>();
const handleCreate = () => emit("create");
const handleSelect = (name: string) => emit("select", name);
const handleSelectLibrary = (name: string) => emit("select-library", name);
const { t } = useI18n();
const searchName = ref("");
const tableColumns = computed(() => getTableColumns(t));
const rowClassName = (record: Library) =>
  record.name === props.selectedLibrary ? "selected-row" : "";
const tableList = computed(() =>
  props.tableData.filter((item) =>
    `${item.name} ${item.id}`
      .toLowerCase()
      .includes(searchName.value.toLowerCase()),
  ),
);
const handleDelete = (name: string) => {
  Modal.confirm({
    title: t("common.delete"),
    content: t("console.deleteLibrary", { name }),
    okText: t("common.confirm"),
    cancelText: t("common.cancel"),
    okType: "danger",
    async onOk() {
      await requestAssetLibraryDelete(name);
      emit("deleted", name);
      emit("search");
    },
  });
};
</script>

<style scoped lang="less">
.table-container {
  border: 1px solid var(--border-main-color);
  border-radius: 8px;
  background: var(--bg-content-color);
  :deep(.intel-card-body) {
    padding: 0;
  }
  :deep(.intel-table-tbody > tr.selected-row > td) {
    background: color-mix(
      in srgb,
      var(--color-primary-second) 4%,
      var(--bg-content-color)
    );
  }
}
.header-wrap {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 20px 24px;
  flex-wrap: wrap;
}
.title-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  .title {
    color: var(--font-main-color);
    font-size: 16px;
    font-weight: 600;
  }
}
.search-input {
  width: 230px;
}
.name-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
}
.resource-icon {
  width: 30px;
  height: 32px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  background: var(--bg-card-color);
  color: var(--color-primary-second);
  font-size: 17px;
}
.name-content {
  min-width: 0;
  .click-link {
    display: block;
    max-width: 240px;
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
  .description {
    color: var(--font-info-color);
    font-size: 12px;
    margin-top: 1px;
    max-width: 280px;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }
}
.selected-icon {
  color: var(--color-primary-second);
}
.database-tag {
  max-width: 100%;
  margin: 0;
  white-space: normal;
  overflow-wrap: anywhere;
}
</style>
