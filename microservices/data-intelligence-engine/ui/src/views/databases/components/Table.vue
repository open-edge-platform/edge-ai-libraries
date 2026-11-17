<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <a-card :bordered="false" class="table-container">
    <div class="header-wrap">
      <div class="title-wrap">
        {{ $t("console.databaseConnections") }}
        <a-tag>{{ tableData.length }}</a-tag>
      </div>
      <a-space wrap>
        <a-input-search
          v-model:value="searchName"
          allowClear
          :placeholder="$t('console.search')"
          class="search-input"
        />
        <a-button :loading="checkingIds.length > 0" @click="handleCheckAll">
          <template #icon><ApiOutlined /></template>
          {{ $t("console.checkAll") }}
        </a-button>
        <a-button type="primary" @click="handleCreate">
          <template #icon><PlusOutlined /></template>
          {{ $t("console.registerDatabase") }}
        </a-button>
      </a-space>
    </div>
    <ConsoleTable
      :columns="tableColumns"
      :data-source="tableList"
      row-key="id"
      :scroll="{ x: 1100 }"
      :reset-key="searchName"
      :row-expandable="(record: Database) => record.in_use_by.length > 0"
      :expanded-row-keys="expandedRowKeys"
      :show-expand-column="false"
    >
      <template #expandedRowRender="{ record }">
        <div class="membership-details">
          <div class="membership-list">
            <a-tag
              v-for="(name, index) in record.in_use_by"
              :key="`${name}-${index}`"
              :bordered="false"
              class="membership-tag"
            >
              {{ name }}
            </a-tag>
          </div>
        </div>
      </template>
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'name'">
          <div class="database-name">
            <div class="database-icon"><DatabaseOutlined /></div>
            <div>
              <strong :title="record.id">{{ record.id }}</strong>
              <p
                v-if="record.description"
                class="description"
                :title="record.description"
              >
                {{ record.description }}
              </p>
              <div class="database-meta">
                <a-tag :bordered="false">{{ record.type }}</a-tag>
                <span>{{ record.backend }}</span>
              </div>
            </div>
          </div>
        </template>
        <template v-else-if="column.key === 'options'">
          <JsonPretty
            :data="record.options"
            :theme="themeStore.theme === 'dark' ? 'dark' : 'light'"
          />
        </template>
        <template v-else-if="column.key === 'inUseBy'">
          <div v-if="record.in_use_by.length" class="membership-summary">
            <a-tag :bordered="false">{{ record.in_use_by.length }}</a-tag>
            <a-button
              type="link"
              size="small"
              class="membership-view"
              :aria-expanded="expandedRowKeys.includes(record.id)"
              @click="toggleMembership(record.id)"
            >
              <template #icon>
                <UpOutlined v-if="expandedRowKeys.includes(record.id)" />
                <EyeOutlined v-else />
              </template>
              {{
                $t(
                  expandedRowKeys.includes(record.id)
                    ? "common.collapse"
                    : "common.view",
                )
              }}
            </a-button>
          </div>
          <span v-if="!record.in_use_by.length" class="muted-wrap">—</span>
        </template>
        <template v-else-if="column.key === 'status'">
          <a-badge
            v-if="checkingIds.includes(record.id)"
            status="processing"
            :text="$t('console.checking')"
          />
          <a-badge
            v-else-if="!checkData[record.id]"
            status="default"
            :text="$t('console.unchecked')"
          />
          <a-badge
            v-else-if="checkData[record.id].reachable"
            status="success"
            :text="$t('console.reachable')"
          />
          <a-tooltip v-else :title="checkData[record.id].error">
            <a-badge status="error" :text="$t('console.unreachable')" />
          </a-tooltip>
        </template>
        <template v-else-if="column.key === 'actions'">
          <a-space :size="6">
            <a-button
              size="small"
              type="primary"
              ghost
              @click="handleUpdate(record.id)"
            >
              {{ $t("common.edit") }}
            </a-button>
            <a-tooltip
              :title="
                record.in_use_by.length ? $t('console.databaseInUse') : ''
              "
            >
              <a-button
                danger
                size="small"
                :disabled="record.in_use_by.length > 0"
                @click="handleDelete(record.id)"
              >
                {{ $t("common.delete") }}
              </a-button>
            </a-tooltip>
            <a-button
              size="small"
              :loading="checkingIds.includes(record.id)"
              @click="handleCheck(record.id)"
            >
              <template #icon><ApiOutlined /></template>
              {{ $t("console.check") }}
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
  ApiOutlined,
  DatabaseOutlined,
  EyeOutlined,
  PlusOutlined,
  UpOutlined,
} from "@ant-design/icons-vue";
import { requestDatabaseDelete } from "@/api/console";
import type { Database, DatabaseCheck } from "@/api/console/type";
import { themeAppStore } from "@/store/theme";
import JsonPretty from "vue-json-pretty";
import "vue-json-pretty/lib/styles.css";
import getTableColumns from "../ColumnsList";
import ConsoleTable from "../../../components/ConsoleTable.vue";
const props = defineProps<{
  tableData: Database[];
  checkData: Record<string, DatabaseCheck>;
  checkingIds: string[];
}>();
const emit = defineEmits<{
  create: [];
  update: [id: string];
  check: [id: string];
  "check-all": [];
  search: [];
}>();
const themeStore = themeAppStore();
const handleCreate = () => emit("create");
const handleUpdate = (id: string) => emit("update", id);
const handleCheck = (id: string) => emit("check", id);
const handleCheckAll = () => emit("check-all");
const { t } = useI18n();
const searchName = ref("");
const expandedRowKeys = ref<string[]>([]);
const toggleMembership = (id: string) => {
  expandedRowKeys.value = expandedRowKeys.value.includes(id)
    ? expandedRowKeys.value.filter((key) => key !== id)
    : [...expandedRowKeys.value, id];
};
const tableColumns = computed(() => getTableColumns(t));
const tableList = computed(() =>
  props.tableData.filter((item) =>
    `${item.id} ${item.type} ${item.backend}`
      .toLowerCase()
      .includes(searchName.value.toLowerCase()),
  ),
);
const handleDelete = (name: string) => {
  Modal.confirm({
    title: t("common.delete"),
    content: t("console.deleteDatabase", { name }),
    okText: t("common.confirm"),
    cancelText: t("common.cancel"),
    okType: "danger",
    async onOk() {
      await requestDatabaseDelete(name);
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
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  padding: 20px 24px;
}
.title-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--font-main-color);
  font-weight: 600;
  font-size: 16px;
}
.search-input {
  width: 220px;
}
.database-name {
  display: flex;
  align-items: center;
  gap: 12px;
  > div:last-child {
    flex: 1;
    min-width: 0;
  }
  strong {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--font-main-color);
    font-weight: 500;
  }
}
.database-icon {
  width: 30px;
  height: 32px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: var(--bg-card-color);
  color: var(--color-primary-second);
  font-size: 17px;
}
.database-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 1px;
  white-space: nowrap;
  min-width: 0;
  .intel-tag {
    flex-shrink: 0;
  }
  > span:last-child {
    color: var(--font-info-color);
    font-size: 12px;
  }
}
.description {
  font-size: 12px;
  color: var(--font-info-color);
  width: 100%;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 4px;
}
.membership-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.membership-summary {
  display: flex;
  align-items: center;
  gap: 6px;
  .intel-tag {
    flex-shrink: 0;
    margin: 0;
  }
  :deep(.membership-view) {
    color: var(--color-primary-second);
  }
}
.membership-details {
  max-height: 240px;
  overflow: auto;
}
.membership-tag {
  max-width: 100%;
  margin: 0;
  white-space: normal;
  overflow-wrap: anywhere;
}
.muted-wrap {
  color: var(--font-info-color);
}
</style>
