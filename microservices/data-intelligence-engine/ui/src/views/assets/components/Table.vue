<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <a-card :bordered="false" class="table-container">
    <div class="header-wrap">
      <a-tabs v-model:activeKey="assetType" class="type-tabs">
        <a-tab-pane key="all" :tab="$t('common.all')" />
        <a-tab-pane
          v-for="type in ['document', 'image', 'video', 'audio']"
          :key="type"
          :tab="$t(`console.${type}`)"
        />
      </a-tabs>
      <a-button type="primary" @click="handleUpload">
        <template #icon><UploadOutlined /></template>
        {{ $t("console.upload") }}
      </a-button>
    </div>
    <div class="filter-wrap">
      <a-input-search
        v-model:value="searchName"
        allowClear
        :placeholder="$t('console.search')"
        class="search-input"
      />
      <div class="selection-wrap">
        <span>
          {{ $t("console.selectedCount", { count: selectedKeys.length }) }}
        </span>
        <a-button
          danger
          size="small"
          :disabled="!selectedKeys.length"
          @click="handleDelete(selectedKeys)"
        >
          <template #icon><DeleteOutlined /></template>
          {{ $t("common.delete") }}
        </a-button>
      </div>
    </div>
    <ConsoleTable
      :columns="tableColumns"
      :data-source="tableList"
      row-key="id"
      :scroll="{ x: 900 }"
      :row-selection="{
        selectedRowKeys: selectedKeys,
        preserveSelectedRowKeys: true,
        onChange: handleSelectionChange,
      }"
      :reset-key="`${assetType}:${searchName}`"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'name'">
          <div class="asset-name">
            <div class="file-icon" :class="getAssetKind(record)">
              <FileTextOutlined v-if="getAssetKind(record) === 'document'" />
              <PictureOutlined v-else-if="getAssetKind(record) === 'image'" />
              <PlaySquareOutlined
                v-else-if="getAssetKind(record) === 'video'"
              />
              <SoundOutlined v-else-if="getAssetKind(record) === 'audio'" />
              <FileOutlined v-else />
            </div>
            <div>
              <a
                :title="record.name || record.id"
                @click="handleView(record.id)"
              >
                {{ record.name || record.id }}
              </a>
              <div class="origin-wrap" :title="record.origin">
                {{ record.origin }}
              </div>
            </div>
          </div>
        </template>
        <template v-else-if="column.key === 'kind'">
          <StatusTag :value="getAssetKind(record)" />
          <div class="muted-wrap">{{ record.media_type }}</div>
        </template>
        <template v-else-if="column.key === 'pools'">
          <a-tag
            v-for="id in record.asset_pool_ids.slice(0, 1)"
            :key="id"
            :bordered="false"
            class="membership-tag"
            :title="poolNames([id])"
          >
            {{ poolData.find((pool) => pool.id === id)?.name || id }}
          </a-tag>
          <a-tooltip
            v-if="record.asset_pool_ids.length > 1"
            :title="poolNames(record.asset_pool_ids)"
          >
            <a-tag :bordered="false"
              >+{{ record.asset_pool_ids.length - 1 }}</a-tag
            >
          </a-tooltip>
          <span v-if="!record.asset_pool_ids.length" class="muted-wrap">—</span>
        </template>
        <template v-else-if="column.key === 'status'">
          <StatusTag :value="record.materialization || 'unknown'" />
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
            <a-button danger size="small" @click="handleDelete([record.id])">
              {{ $t("common.delete") }}
            </a-button>
          </a-space>
        </template>
      </template>
    </ConsoleTable>
  </a-card>
</template>
<script lang="ts" setup name="Table">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { Modal } from "ant-design-vue";
import type { Key } from "ant-design-vue/es/_util/type";
import {
  DeleteOutlined,
  FileOutlined,
  FileTextOutlined,
  PictureOutlined,
  PlaySquareOutlined,
  SoundOutlined,
  UploadOutlined,
} from "@ant-design/icons-vue";
import { requestAssetDelete } from "@/api/console";
import type { Asset, AssetPool } from "@/api/console/type";
import StatusTag from "../../../components/StatusTag.vue";
import getTableColumns from "../ColumnsList";
import ConsoleTable from "../../../components/ConsoleTable.vue";
import { getAssetKind } from "../AssetKind";
const props = defineProps<{
  tableData: Asset[];
  poolData: AssetPool[];
  libraryName: string;
}>();
const emit = defineEmits<{ upload: []; search: []; view: [id: string] }>();
const handleUpload = () => emit("upload");
const handleView = (id: string) => emit("view", id);
const { t } = useI18n();
const assetType = ref("all");
const searchName = ref("");
const selectedKeys = ref<string[]>([]);
const tableColumns = computed(() => getTableColumns(t));
const poolNames = (ids: string[]) =>
  ids
    .map((id) => props.poolData.find((pool) => pool.id === id)?.name || id)
    .join(", ");
const tableList = computed(() =>
  props.tableData.filter(
    (item) =>
      (assetType.value === "all" || getAssetKind(item) === assetType.value) &&
      `${item.name} ${item.id} ${item.origin}`
        .toLowerCase()
        .includes(searchName.value.toLowerCase()),
  ),
);
const handleSelectionChange = (keys: Key[]) => {
  selectedKeys.value = keys.map(String);
};
const handleDelete = (ids: string[]) => {
  Modal.confirm({
    title: t("common.delete"),
    content: t("console.deleteAssets", { count: ids.length }),
    okText: t("common.confirm"),
    cancelText: t("common.cancel"),
    okType: "danger",
    async onOk() {
      await requestAssetDelete(props.libraryName, { asset_ids: ids });
      selectedKeys.value = [];
      emit("search");
    },
  });
};
watch(
  () => props.tableData,
  (data) => {
    selectedKeys.value = selectedKeys.value.filter((id) =>
      data.some((item) => item.id === id),
    );
  },
);
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
  gap: 16px;
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
  }
  :deep(.intel-tabs-tab) {
    padding: 16px 0;
  }
}
.filter-wrap {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 24px;
  gap: 10px;
  flex-wrap: wrap;
}
.search-input {
  width: 280px;
  max-width: 100%;
}
.selection-wrap {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  color: var(--font-info-color);
}
.asset-name {
  display: flex;
  align-items: center;
  gap: 12px;
  a {
    display: block;
    max-width: 280px;
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
.file-icon {
  width: 28px;
  height: 32px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  background: var(--bg-card-color);
  border-radius: 6px;
  color: var(--color-primary-second);
  font-size: 17px;
  &.image {
    color: var(--color-purple);
  }
  &.audio {
    color: var(--color-success);
  }
  &.video {
    color: var(--color-warning);
  }
}
.origin-wrap {
  max-width: 280px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  font-size: 12px;
  color: var(--font-info-color);
  margin-top: 1px;
}
.muted-wrap {
  font-size: 12px;
  color: var(--font-info-color);
}
.membership-tag {
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
