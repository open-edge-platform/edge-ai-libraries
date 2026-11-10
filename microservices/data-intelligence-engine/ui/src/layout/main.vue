<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <a-layout class="console-container">
    <a-layout-header class="header-container">
      <Header />
    </a-layout-header>
    <a-layout class="body-container">
      <Sidebar :online="online" />
      <a-layout-content class="main-container">
        <div class="toolbar-wrap">
          <a-breadcrumb>
            <a-breadcrumb-item>{{ $t("console.title") }}</a-breadcrumb-item>
            <a-breadcrumb-item>
              {{ $t(`console.${currentPage}`) }}
            </a-breadcrumb-item>
          </a-breadcrumb>
          <div class="scope-wrap">
            <span class="scope-label">{{ $t("console.library") }}</span>
            <a-select
              :value="libraryName || undefined"
              :placeholder="$t('console.pleaseSelect')"
              :aria-label="$t('console.library')"
              :options="
                libraryList.map((item) => ({
                  value: item.name,
                  label: item.name,
                }))
              "
              :disabled="loading"
              showSearch
              class="library-select"
              @change="handleLibraryChange"
            />
            <a-tooltip :title="$t('console.refresh')">
              <a-button
                :loading="loading"
                :aria-label="$t('console.refresh')"
                @click="handleRefresh"
              >
                <template #icon><ReloadOutlined /></template>
              </a-button>
            </a-tooltip>
          </div>
        </div>
        <div
          class="page-container"
          :class="{
            'workspace-page': isWorkspacePage,
            'table-page': isTablePage,
            'chat-page': currentPage === 'chat',
          }"
        >
          <a-alert
            v-if="loadError"
            type="error"
            showIcon
            :message="$t('console.loadingError')"
            :description="loadError"
            class="error-wrap"
          />
          <div class="page-content" :aria-busy="loading">
            <a-empty
              v-if="initialized && !libraryData && isLibraryPage"
              :description="$t('console.noLibrary')"
              class="empty-wrap"
            >
              <a-button type="primary" @click="handleCreateLibrary">
                {{ $t("console.createLibrary") }}
              </a-button>
            </a-empty>
            <router-view v-else-if="initialized" v-slot="{ Component }">
              <component
                :is="Component"
                :key="`${currentPage}:${isLibraryPage ? libraryName : ''}:${refreshKey}`"
                class="console-page"
                :library-list="libraryList"
                :library-data="libraryData"
                @refresh="handleSearch"
                @select-library="handleLibraryChange"
                @library-deleted="handleLibraryDeleted"
              />
            </router-view>
          </div>
        </div>
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>

<script lang="ts" setup name="Console">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { ReloadOutlined } from "@ant-design/icons-vue";
import Header from "@/layout/Header.vue";
import Sidebar from "@/layout/Sidebar.vue";
import { useLibraryStore } from "@/store/library";
import { getAssetLibraryList, getHealth } from "@/api/console";
import type { Library } from "@/api/console/type";

const route = useRoute();
const router = useRouter();
const { t, locale } = useI18n();
const handleCreateLibrary = () => router.push("/libraries");
const handleSearch = () => queryLibraryList(false);
const loading = ref(false);
const initialized = ref(false);
const online = ref(false);
const loadError = ref("");
const libraryList = ref<Library[]>([]);
const libraryStore = useLibraryStore();
const libraryName = ref(
  typeof route.query.library === "string"
    ? route.query.library
    : libraryStore.selectedName,
);
const refreshKey = ref(0);
const libraryData = computed(() =>
  libraryList.value.find((item) => item.name === libraryName.value),
);
const currentPage = computed(() => String(route.meta.consolePage));
const isLibraryPage = computed(
  () => !["libraries", "databases", "models"].includes(currentPage.value),
);
const isWorkspacePage = computed(() => currentPage.value !== "chat");
const isTablePage = computed(() =>
  ["libraries", "assets", "pools", "sources", "databases", "models"].includes(
    currentPage.value,
  ),
);
let statusTimer: ReturnType<typeof setTimeout>;
let disposed = false;
let healthCheckedAt = 0;
const previousTitle = document.title;

const queryLibraryList = async (showLoading = true) => {
  libraryList.value = await getAssetLibraryList(showLoading);
  if (!libraryList.value.some((item) => item.name === libraryName.value)) {
    if (libraryStore.selectedName === libraryName.value)
      libraryStore.selectedName = "";
    libraryName.value = libraryList.value[0]?.name || "";
  }
};
const queryEngineHealth = async () => {
  healthCheckedAt = Date.now();
  try {
    await getHealth();
    online.value = true;
  } catch (error) {
    online.value = false;
    console.error(error);
  }
};
const handleRefresh = async () => {
  loading.value = true;
  loadError.value = "";
  try {
    await Promise.all([queryLibraryList(), queryEngineHealth()]);
    refreshKey.value++;
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  } finally {
    initialized.value = true;
    loading.value = false;
  }
};
const handleLibraryChange = (value: unknown) => {
  libraryName.value = String(value);
  libraryStore.selectedName = libraryName.value;
};
const handleLibraryDeleted = (name: string) => {
  if (name !== libraryName.value) return;
  libraryName.value = "";
  libraryStore.selectedName = "";
};
const querySourceStatus = async () => {
  // if (Date.now() - healthCheckedAt >= 15000) await queryEngineHealth();
  const syncing = libraryData.value?.asset_pools.some((pool) =>
    pool.source_statuses.some(
      (status) =>
        !["DEGRADE", "DISABLED"].includes(status.effective_state) &&
        (["pending", "indexing"].includes(status.status) ||
          ["running", "queued"].includes(status.extraction?.state || "")),
    ),
  );
  if (syncing && !loading.value) {
    try {
      await queryLibraryList(false);
      loadError.value = "";
    } catch (error) {
      loadError.value = error instanceof Error ? error.message : String(error);
    }
  }
  if (!disposed) statusTimer = setTimeout(querySourceStatus, 3000);
};
watch(
  [currentPage, locale],
  () => {
    document.title = `${t(`console.${currentPage.value}`)} · ${t("console.title")}`;
  },
  { immediate: true },
);
watch(
  () => route.query.library,
  (name) => {
    if (typeof name === "string") handleLibraryChange(name);
  },
  { immediate: true },
);
onMounted(async () => {
  await handleRefresh();
  if (!disposed) statusTimer = setTimeout(querySourceStatus, 5000);
});
onUnmounted(() => {
  disposed = true;
  clearTimeout(statusTimer);
  document.title = previousTitle;
});
</script>

<style scoped lang="less">
.console-container {
  height: 100%;
  min-width: 0;
  background: var(--bg-main-color);
  .header-container {
    height: 64px;
    padding: 0 32px;
    background: var(--bg-content-color);
    border-bottom: 1px solid var(--border-main-color);
    :deep(.header-wrap) {
      max-width: none;
    }
  }
  .body-container {
    min-height: 0;
    background: transparent;
  }
  .main-container {
    min-width: 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
    background: var(--bg-main-color);
  }
  .toolbar-wrap {
    min-height: 56px;
    padding: 10px 20px;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 12px;
    background: var(--bg-content-color);
    border-bottom: 1px solid var(--border-main-color);
  }
  .scope-wrap {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .scope-label {
    color: var(--font-info-color);
    font-size: 12px;
  }
  .library-select {
    width: 200px;
  }
  .page-help {
    margin-left: 6px;
    color: var(--font-info-color);
  }
  .page-container {
    flex: 1;
    min-height: 0;
    overflow: auto;
    padding: 12px 14px;
  }
  .workspace-page {
    display: flex;
    flex-direction: column;
    overflow: auto;
    .page-content {
      display: flex;
      flex-direction: column;
      flex: 1;
      min-height: 0;
    }
    :deep(.console-page),
    :deep(.table-container),
    :deep(.table-container > .intel-card-body) {
      display: flex;
      flex-direction: column;
      flex: 1;
      min-width: 0;
      min-height: 0;
    }
    :deep(.table-container .header-wrap),
    :deep(.table-container .filter-wrap) {
      flex-shrink: 0;
    }
    :deep(.table-container .header-wrap) {
      padding: 12px 16px;
      gap: 10px;
    }
    :deep(.table-container .filter-wrap) {
      padding: 10px 16px;
    }
    :deep(.table-container .type-tabs .intel-tabs-tab) {
      padding: 8px 0;
    }
  }
  .table-page {
    overflow: hidden;
    .page-content {
      min-height: 0;
    }
  }
  .chat-page {
    display: flex;
    flex-direction: column;
    .page-content {
      display: flex;
      flex: 1;
      min-height: 0;
    }
  }
  :deep(.summary-strip) {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    flex-shrink: 0;
    gap: 10px 28px;
    padding: 10px 16px;
    margin-bottom: 12px;
    border: 1px solid var(--border-main-color);
    border-radius: 6px;
    background: var(--bg-content-color);
  }
  :deep(.summary-item) {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    color: var(--font-info-color);
    font-size: 12px;
    strong {
      color: var(--font-main-color);
      font-size: 18px;
      font-weight: 600;
      line-height: 24px;
    }
    .summary-icon {
      color: var(--color-primary-second);
      font-size: 16px;
      &.assets,
      &.success {
        color: var(--color-success);
      }
      &.pools,
      &.purple {
        color: var(--color-purple);
      }
      &.sources {
        color: var(--color-warning);
      }
    }
  }
  .empty-wrap {
    padding: 70px 20px;
    background: var(--bg-content-color);
    border-radius: 8px;
  }
  .error-wrap {
    margin-bottom: 12px;
    flex-shrink: 0;
  }
  @media (max-width: 900px) {
    .page-container {
      padding: 12px;
    }
    .toolbar-wrap {
      padding: 14px 20px;
    }
    .header-container {
      padding: 0 20px;
    }
  }
  @media (max-width: 600px) {
    .scope-label,
    .toolbar-wrap > .intel-breadcrumb {
      display: none;
    }
    .toolbar-wrap {
      min-height: 60px;
      padding: 12px;
    }
    .library-select {
      width: 150px;
    }
    .page-container {
      padding: 16px 12px;
    }
  }
}
</style>
