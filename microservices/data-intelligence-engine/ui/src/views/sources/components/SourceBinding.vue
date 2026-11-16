<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <div class="binding-container">
    <div class="binding-header">
      <div class="binding-icon"><DeploymentUnitOutlined /></div>
      <div class="binding-name">
        <strong>{{ sourceData?.name || binding.source_id }}</strong>
        <div>
          <StatusTag :value="binding.display_status" />
          <StatusTag :value="binding.serving_state" raw />
          <StatusTag
            v-if="binding.effective_state !== binding.serving_state"
            :value="binding.effective_state"
            raw
          />
        </div>
      </div>
      <a-space align="center" wrap>
        <a-tooltip
          :title="
            locked
              ? $t('console.replacementLocked')
              : sourceData?.enabled === false
                ? $t('console.sourceDisabled')
                : $t('console.servingHint')
          "
        >
          <a-button
            v-if="sourceData?.type !== 'object'"
            size="small"
            :disabled="locked || sourceData?.enabled === false"
            :loading="submitLoading"
            type="primary"
            ghost
            @click="handleServingChange"
          >
            <template v-if="binding.serving_state === 'DEGRADE'">
              <PlayCircleOutlined />
              SERVING
            </template>
            <template v-else>
              <PauseCircleOutlined />
              DEGRADE
            </template>
          </a-button>
        </a-tooltip>
        <a-button
          v-if="binding.extraction"
          size="small"
          :loading="submitLoading"
          :disabled="
            locked ||
            sourceData?.enabled === false ||
            binding.effective_state === 'DEGRADE'
          "
          @click="handleExtraction"
        >
          <template #icon><ThunderboltOutlined /></template>
          {{ $t("console.extract") }}
        </a-button>
        <a-tooltip
          v-if="removable && sourceData?.type !== 'object'"
          :title="
            pool.source_statuses.length <= 1
              ? $t('console.sourceRequired')
              : $t('console.detachHint')
          "
        >
          <a-button
            danger
            size="small"
            :disabled="pool.source_statuses.length <= 1"
            @click="handleDetach"
          >
            <template #icon><DisconnectOutlined /></template>
            {{ $t("console.detach") }}
          </a-button>
        </a-tooltip>
      </a-space>
    </div>
    <div class="binding-meta">
      <span
        >{{ $t("console.indexedRevision") }}:
        {{ binding.indexed_revision }}</span
      >
      <span v-if="binding.updated_at"
        >{{ $t("console.updatedAt") }}:
        {{ new Date(binding.updated_at).toLocaleString() }}</span
      >
    </div>
    <div v-if="binding.extraction" class="extraction-wrap">
      <StatusTag :value="binding.extraction.state" />
      <span v-if="binding.extraction.outdated">{{
        $t("console.extractionOutdated")
      }}</span>
      <span>
        {{ $t("console.trigger") }}:
        {{ $t(`console.${binding.extraction.trigger}`) }}
      </span>
      <span v-if="binding.extraction.next_run">
        {{ $t("console.nextRun") }}:
        {{ new Date(binding.extraction.next_run).toLocaleString() }}
      </span>
      <span v-if="binding.extraction.trigger_options?.cron">
        {{ binding.extraction.trigger_options.cron }} ({{
          binding.extraction.trigger_options.timezone
        }})
      </span>
      <span v-if="binding.extraction.active?.not_before">
        {{ $t("console.notBefore") }}:
        {{ new Date(binding.extraction.active.not_before).toLocaleString() }}
      </span>
      <span v-if="binding.extraction.last">
        {{ $t("console.lastRun") }}:
        <StatusTag :value="binding.extraction.last.state" />
        {{
          binding.extraction.last.finished_at
            ? new Date(binding.extraction.last.finished_at).toLocaleString()
            : ""
        }}
      </span>
      <span v-if="binding.extraction.last?.result?.concepts != null">
        {{ binding.extraction.last.result.concepts }}
        {{ $t("console.concepts") }}
      </span>
    </div>
    <a-alert
      v-if="binding.error || binding.extraction?.last?.error"
      type="error"
      showIcon
      :message="binding.error || binding.extraction?.last?.error"
      :description="
        binding.error && binding.extraction?.last?.error !== binding.error
          ? binding.extraction?.last?.error
          : undefined
      "
      class="error-wrap"
    />
  </div>
</template>
<script lang="ts" setup name="SourceBinding">
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import { Modal } from "ant-design-vue";
import {
  DeploymentUnitOutlined,
  DisconnectOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons-vue";
import {
  requestExtractionCreate,
  requestSourceServingUpdate,
} from "@/api/console";
import type { AssetPool, Library, SourceStatus } from "@/api/console/type";
import StatusTag from "../../../components/StatusTag.vue";
const props = defineProps<{
  libraryData: Library;
  pool: AssetPool;
  binding: SourceStatus;
  removable?: boolean;
}>();
const emit = defineEmits<{ search: []; detach: [] }>();
const handleDetach = () => emit("detach");
const { t } = useI18n();
const submitLoading = ref(false);
const sourceData = computed(() =>
  props.libraryData.sources.find((item) => item.id === props.binding.source_id),
);
const locked = computed(() =>
  props.pool.source_statuses.some(
    (status) =>
      status.serving_state === "PREPARING" &&
      status.replaces &&
      [status.source_id, status.replaces].includes(props.binding.source_id),
  ),
);
const handleUpdateServing = async (state: "SERVING" | "DEGRADE") => {
  submitLoading.value = true;
  try {
    await requestSourceServingUpdate(
      props.libraryData.name,
      props.pool.id,
      props.binding.source_id,
      { serving_state: state },
    );
    emit("search");
  } finally {
    submitLoading.value = false;
  }
};
const handleServingChange = () => {
  if (props.binding.serving_state === "DEGRADE")
    return handleUpdateServing("SERVING");
  Modal.confirm({
    title: t("console.stop"),
    content: t("console.stopServing", { name: sourceData.value?.name }),
    okText: t("common.confirm"),
    cancelText: t("common.cancel"),
    onOk: () => handleUpdateServing("DEGRADE"),
  });
};
const handleExtraction = async () => {
  submitLoading.value = true;
  try {
    await requestExtractionCreate(props.libraryData.name, props.pool.id, {
      source_id: props.binding.source_id,
    });
    emit("search");
  } finally {
    submitLoading.value = false;
  }
};
</script>
<style scoped lang="less">
.binding-container {
  padding: 12px;
  border: 1px solid var(--border-main-color);
  border-radius: 8px;
  margin-bottom: 12px;
  background: var(--bg-content-color);
}
.binding-header {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.binding-icon {
  width: 36px;
  height: 40px;
  border-radius: 6px;
  display: grid;
  place-items: center;
  background: var(--bg-card-color);
  color: var(--color-primary-second);
  font-size: 19px;
}
.binding-name {
  flex: 1;
  min-width: 80px;
  strong {
    display: block;
    font-size: 13px;
    font-weight: 500;
    color: var(--font-main-color);
    margin-bottom: 7px;
  }
}
.extraction-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
  color: var(--font-info-color);
  font-size: 12px;
  padding-top: 10px;
  margin-top: 10px;
  border-top: 1px dashed var(--border-main-color);
}
.binding-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
  margin-top: 8px;
  font-size: 11px;
  color: var(--font-info-color);
}
.error-wrap {
  margin-top: 14px;
}
</style>
