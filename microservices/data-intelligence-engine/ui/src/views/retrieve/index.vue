<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <div v-if="libraryData" class="retrieval-container">
    <a-card :bordered="false" class="configuration-card">
      <template #title>
        <div class="card-title">
          <SlidersOutlined />
          {{ $t("console.retrievalSettings") }}
        </div>
      </template>
      <RetrievalForm ref="formRef" :library-data="libraryData" />
    </a-card>
    <div
      ref="workspaceRef"
      class="workspace-wrap"
      :class="{ 'graph-workspace': activeKey === 'graph' }"
    >
      <a-card :bordered="false" class="query-card">
        <div class="query-input">
          <a-textarea
            v-model:value="query"
            :auto-size="{ minRows: 1, maxRows: 4 }"
            :placeholder="$t('console.queryPlaceholder')"
            @keydown.ctrl.enter.prevent="handleRetrieve"
          />
          <div class="query-footer">
            <span>Ctrl + Enter</span>
            <a-button
              type="primary"
              :loading="loading"
              :disabled="!query.trim()"
              @click="handleRetrieve"
            >
              <template #icon><SearchOutlined /></template>
              {{ $t("console.retrieveNow") }}
            </a-button>
          </div>
        </div>
        <a-alert
          v-if="errorMessage"
          type="error"
          showIcon
          :message="errorMessage"
          class="error-wrap"
        />
      </a-card>
      <div ref="resultsRef" class="results-region">
        <a-card :bordered="false" class="results-card">
          <a-tabs v-model:activeKey="activeKey" @tab-click="handleTabClick">
            <a-tab-pane key="results">
              <template #tab>
                <FileSearchOutlined />
                {{ $t("console.results") }}
                <a-badge
                  v-if="result"
                  :count="result.chunks.length"
                  :showZero="true"
                  color="var(--color-primary-second)"
                  class="result-count"
                />
              </template>
              <Results
                :result="result"
                :loading="loading"
                :excluded-ids="formRef?.excludedIds"
                @exclude="handleExclude"
                @focus="handleFocus"
              />
            </a-tab-pane>
            <a-tab-pane key="graph" force-render>
              <template #tab>
                <NodeIndexOutlined />
                {{ $t("console.graph") }}
              </template>
              <ConceptGraph
                :library-data="libraryData"
                :result="result"
                :focus="focus"
                :retrieving="loading"
              />
            </a-tab-pane>
          </a-tabs>
        </a-card>
      </div>
    </div>
  </div>
</template>
<script lang="ts" setup name="ConsoleRetrieval">
import { nextTick, onUnmounted, ref, watch } from "vue";
import { isAxiosError, isCancel } from "axios";
import {
  FileSearchOutlined,
  NodeIndexOutlined,
  SearchOutlined,
  SlidersOutlined,
} from "@ant-design/icons-vue";
import type { RetrieveResult } from "@/api/console/type";
import type { ConsolePageProps } from "../../types/console";
import type { ConceptFocus } from "./Type";
import RetrievalForm from "./components/RetrievalForm.vue";
import Results from "./components/Results.vue";
import ConceptGraph from "./components/ConceptGraph.vue";
defineProps<ConsolePageProps>();
const formRef = ref<InstanceType<typeof RetrievalForm>>();
const handleExclude = (id: string) => formRef.value?.excludeChunk(id);
const query = ref("");
const loading = ref(false);
const errorMessage = ref("");
const result = ref<RetrieveResult>();
const focus = ref<ConceptFocus>();
const activeKey = ref("results");
const workspaceRef = ref<HTMLElement>();
const resultsRef = ref<HTMLElement>();
const scrollToGraph = async () => {
  await nextTick();
  const workspace = workspaceRef.value;
  const results = resultsRef.value;
  if (!workspace || !results) return;
  workspace.scrollTo({
    top:
      workspace.scrollTop +
      results.getBoundingClientRect().top -
      workspace.getBoundingClientRect().top,
    behavior: "auto",
  });
};
const handleTabClick = (key: string | number) => {
  if (key === "graph" && activeKey.value === "graph") scrollToGraph();
};
watch(activeKey, (key) => {
  if (key === "graph") scrollToGraph();
});
let controller: AbortController | undefined;
const handleRetrieve = async () => {
  if (loading.value || !query.value.trim()) return;
  loading.value = true;
  errorMessage.value = "";
  result.value = undefined;
  controller = new AbortController();
  try {
    result.value = await formRef.value!.retrieve(
      query.value,
      controller.signal,
    );
    focus.value = undefined;
    activeKey.value = result.value?.graph_traces?.length ? "graph" : "results";
  } catch (error) {
    if (!isCancel(error))
      errorMessage.value = isAxiosError(error)
        ? String(error.response?.data?.detail || error.message)
        : error instanceof Error
          ? error.message
          : String(error);
  } finally {
    loading.value = false;
    controller = undefined;
  }
};
const handleFocus = (value: ConceptFocus) => {
  focus.value = value;
  activeKey.value = "graph";
};
onUnmounted(() => controller?.abort());
</script>
<style scoped lang="less">
.retrieval-container {
  display: flex;
  flex-direction: row !important;
  gap: 12px;
  overflow: hidden;
  min-height: 0;
}
.configuration-card,
.query-card,
.results-card {
  border: 1px solid var(--border-main-color);
  background: var(--bg-content-color);
  border-radius: 8px;
}
.configuration-card {
  width: 300px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
  :deep(.intel-card-head) {
    flex-shrink: 0;
    padding: 0 20px;
    min-height: 56px;
  }
  :deep(.intel-card-body) {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    overscroll-behavior-y: contain;
    padding: 22px 20px 10px;
  }
}
.card-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  .anticon {
    color: var(--color-primary-second);
  }
}
.workspace-wrap {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  overscroll-behavior-y: contain;
  gap: 20px;
  > .query-card {
    flex: 0 0 auto;
  }
}
.results-region {
  flex: 1 1 auto;
  min-height: 400px;
}
.query-card :deep(.intel-card-body) {
  padding: 14px 18px;
}
.query-input {
  border: 1px solid var(--border-main-color);
  border-radius: 8px;
  overflow: hidden;
  background: var(--bg-content-color);
  &:focus-within {
    border-color: var(--color-primary-second);
  }
  :deep(textarea) {
    border: 0;
    box-shadow: none;
    padding: 9px 12px;
    resize: none;
  }
}
.query-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px 12px;
  span {
    font-size: 11px;
    color: var(--font-tip-color);
  }
}
.error-wrap {
  margin-top: 16px;
}
.results-card {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  :deep(.intel-card-body) {
    display: flex;
    flex: 1;
    flex-direction: column;
    min-height: 0;
    padding: 0;
  }
  :deep(.intel-tabs) {
    display: flex;
    flex: 1;
    flex-direction: column;
    min-height: 0;
  }
  :deep(.intel-tabs-nav) {
    flex: 0 0 auto;
    padding: 0 24px;
    margin: 0;
  }
  :deep(.intel-tabs-content-holder) {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 24px;
  }
  :deep(.intel-tabs-content) {
    min-height: 100%;
  }
}
.result-count {
  margin-left: 8px;
}
.graph-workspace {
  overflow: hidden;
  .results-region {
    min-height: 0;
  }
  :deep(.intel-tabs-content-holder) {
    display: flex;
    flex-direction: column;
    overflow: hidden;
    padding: 12px;
  }
  :deep(.intel-tabs-content) {
    flex: 1;
    min-height: 0;
    height: 100%;
  }
  :deep(.intel-tabs-tabpane-active) {
    height: 100%;
    min-height: 0;
  }
}
@media (max-width: 1150px) {
  .configuration-card {
    width: 260px;
  }
}
</style>
