<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <div class="library-container">
    <section class="setup-guide" :aria-label="$t('console.setupGuide')">
      <div class="guide-heading">
        <strong>{{ $t("console.setupGuide") }}</strong>
        <span>{{ $t("console.setupGuideHint") }}</span>
      </div>
      <ol class="guide-steps">
        <li v-for="(step, index) in guideSteps" :key="step.title">
          <button
            type="button"
            class="guide-step"
            :disabled="step.disabled"
            @click="handleGuideStep(index)"
          >
            <span class="step-number">{{ index + 1 }}</span>
            <span class="step-content">
              <strong>{{ $t(step.title) }}</strong>
            </span>
          </button>
          <ArrowRightOutlined
            v-if="index < guideSteps.length - 1"
            class="step-arrow"
            aria-hidden="true"
          />
        </li>
      </ol>
    </section>
    <div class="summary-strip">
      <div v-for="item in summaryList" :key="item.key" class="summary-item">
        <component :is="item.icon" class="summary-icon" :class="item.key" />
        <span>{{ $t(`console.${item.key}`) }}</span>
        <strong>{{ item.value }}</strong>
      </div>
    </div>
    <div
      ref="libraryTable"
      class="library-table"
      tabindex="-1"
      :aria-label="$t('console.selectLibrary')"
    >
      <Table
        :table-data="libraryList"
        :selected-library="libraryData?.name"
        @create="handleCreate"
        @select="handleSelect"
        @select-library="handleSelectLibrary"
        @search="handleSearch"
        @deleted="handleDeleted"
      />
    </div>
    <CreateDialog
      v-if="createDialog"
      @close="handleCreateClose"
      @search="handleSearch"
      @created="handleCreated"
    />
  </div>
</template>

<script lang="ts" setup name="ConsoleLibraries">
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import {
  AppstoreOutlined,
  FileTextOutlined,
  ApartmentOutlined,
  DeploymentUnitOutlined,
  ArrowRightOutlined,
} from "@ant-design/icons-vue";
import type { ConsolePageProps } from "../../types/console";
import Table from "./components/Table.vue";
import CreateDialog from "./components/CreateDialog.vue";

const props = defineProps<ConsolePageProps>();
const emit = defineEmits<{
  refresh: [];
  "select-library": [name: string];
  "library-deleted": [name: string];
}>();
const router = useRouter();
const createDialog = ref(false);
const libraryTable = ref<HTMLElement>();
const guideSteps = computed(() => [
  { title: "console.createLibrary", disabled: false },
  { title: "console.selectLibrary", disabled: !props.libraryList.length },
  { title: "console.createSource", disabled: !props.libraryData },
  { title: "console.createPool", disabled: !props.libraryData?.sources.length },
  { title: "console.upload", disabled: !props.libraryData?.asset_pools.length },
]);
const handleGuideStep = (index: number) => {
  if (index === 0) handleCreate();
  else if (index === 1) {
    libraryTable.value?.scrollIntoView({ behavior: "smooth", block: "start" });
    libraryTable.value?.focus({ preventScroll: true });
  } else {
    router.push(["/sources", "/pools", "/assets"][index - 2]);
  }
};
const handleCreate = () => {
  createDialog.value = true;
};
const handleCreateClose = () => {
  createDialog.value = false;
};
const handleSearch = () => emit("refresh");
const handleDeleted = (name: string) => emit("library-deleted", name);
const summaryList = computed(() => [
  { key: "libraries", icon: AppstoreOutlined, value: props.libraryList.length },
  {
    key: "assets",
    icon: FileTextOutlined,
    value: props.libraryList.reduce(
      (total, item) => total + item.asset_count,
      0,
    ),
  },
  {
    key: "pools",
    icon: ApartmentOutlined,
    value: props.libraryList.reduce(
      (total, item) => total + item.asset_pools.length,
      0,
    ),
  },
  {
    key: "sources",
    icon: DeploymentUnitOutlined,
    value: props.libraryList.reduce(
      (total, item) => total + item.sources.length,
      0,
    ),
  },
]);
const handleSelect = (name: string) => {
  emit("select-library", name);
  router.push("/assets");
};
const handleSelectLibrary = (name: string) => emit("select-library", name);
const handleCreated = (name: string) => {
  emit("select-library", name);
};
</script>

<style scoped lang="less">
.library-table {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}
.setup-guide {
  flex-shrink: 0;
  padding: 16px 18px;
  border: 1px solid
    color-mix(
      in srgb,
      var(--color-primary-second) 40%,
      var(--border-main-color)
    );
  border-radius: 8px;
  background: var(--bg-card-color);
  margin-bottom: 12px;
}
.guide-heading {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 8px 16px;
  margin-bottom: 12px;
  strong {
    color: var(--font-main-color);
    font-size: 15px;
  }
  > span {
    color: var(--font-info-color);
    font-size: 12px;
  }
}
.guide-steps {
  display: flex;
  gap: 10px;
  list-style: none;
  padding: 0;
  margin: 0;
  > li {
    display: flex;
    align-items: center;
    gap: 10px;
    flex: 1;
    min-width: 0;
  }
}
.step-arrow {
  flex-shrink: 0;
  color: var(--color-primary-second);
  font-size: 18px;
}
.guide-step {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  height: 100%;
  padding: 12px 10px;
  text-align: start;
  font: inherit;
  border: 1px solid
    color-mix(
      in srgb,
      var(--color-primary-second) 25%,
      var(--border-main-color)
    );
  border-radius: 6px;
  background: color-mix(
    in srgb,
    var(--color-primary-second) 6%,
    var(--bg-content-color)
  );
  cursor: pointer;
  &:hover:not(:disabled),
  &:focus-visible {
    border-color: var(--color-primary-second);
  }
  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
}
.step-number {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--color-primary-second);
  color: var(--color-white);
  font-size: 13px;
  font-weight: 600;
}
.step-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
  strong {
    color: var(--font-main-color);
    font-size: 14px;
    font-weight: 600;
  }
}
@media (max-width: 1100px) {
  .guide-steps {
    overflow-x: auto;
    > li {
      flex: 0 0 160px;
    }
  }
}
</style>
