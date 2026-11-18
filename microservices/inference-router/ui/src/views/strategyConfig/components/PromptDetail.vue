<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

<template>
  <section class="classifier-section">
    <div class="classifier-heading">
      <strong>{{ t("router.strategyClassifiers") }}</strong>
    </div>
    <p v-if="!options.length" class="classifier-empty">
      {{ t("router.strategyNoClassifiers") }}
    </p>
    <template v-else>
      <details
        v-for="(option, modelIndex) in options"
        :key="option.model"
        class="classifier-card"
        :open="initialOpenModels.has(option.model)"
      >
        <summary>
          <RightOutlined class="classifier-chevron" />
          <span class="classifier-model">{{ option.model }}</span>
          <span class="classifier-meta">
            {{ t("router.strategyClassifierVersionCount", { count: option.versions?.length || 0 }) }}
          </span>
        </summary>
        <div class="classifier-body">
          <p v-if="!option.versions?.length" class="classifier-empty">
            {{ t("router.strategyNoClassifierVersions") }}
          </p>
          <a-tabs
            v-else
            v-model:active-key="activeVersions[option.model]"
            size="small"
            :animated="false"
            destroy-inactive-tab-pane
          >
            <a-tab-pane
              v-for="(version, versionIndex) in option.versions"
              :key="version.version"
            >
              <template #tab>
                <span class="classifier-version-label">
                  {{ version.version }}
                  <a-tooltip
                    v-if="isEffective(option.model, version.version)"
                    :title="t('router.strategyClassifierEffective')"
                  >
                    <CheckCircleFilled
                      class="classifier-effective-icon"
                      :aria-label="t('router.strategyClassifierEffective')"
                    />
                  </a-tooltip>
                  <span
                    v-else-if="isConfigured(option.model, version.version)"
                    class="classifier-badge"
                  >{{ t("router.strategyClassifierConfigured") }}</span>
                </span>
              </template>
              <div class="prompt-heading">
                <strong>Prompt</strong>
                <span
                  v-if="version.kind"
                  class="prompt-kind"
                  :class="{
                    'prompt-kind-hard': version.kind === 'hard',
                    'prompt-kind-soft': version.kind === 'soft',
                  }"
                >
                  <span class="prompt-kind-dot" aria-hidden="true"></span>
                  {{ version.kind }}
                </span>
                <a-button
                  v-if="hasText(version.text)"
                  type="text"
                  size="small"
                  class="prompt-copy"
                  @click="copyText(version.text)"
                >
                  <template #icon><CopyOutlined /></template>
                  {{ t("common.copy") }}
                </a-button>
              </div>
              <template v-if="hasText(version.text)">
                <pre
                  :ref="(element) => observePrompt(element, `${modelIndex}:${versionIndex}`)"
                  class="prompt-text"
                  :class="{ 'is-expanded': expanded[`${modelIndex}:${versionIndex}`] }"
                  tabindex="0"
                  aria-label="Prompt"
                >{{ version.text }}</pre>
                <a-button
                  v-if="overflowing[`${modelIndex}:${versionIndex}`]"
                  type="text"
                  size="small"
                  class="prompt-expand"
                  :aria-expanded="!!expanded[`${modelIndex}:${versionIndex}`]"
                  @click="expanded[`${modelIndex}:${versionIndex}`] = !expanded[`${modelIndex}:${versionIndex}`]"
                >
                  <span>
                    {{ t(expanded[`${modelIndex}:${versionIndex}`]
                      ? "router.strategyPromptCollapse"
                      : "router.strategyPromptExpand") }}
                  </span>
                  <UpOutlined v-if="expanded[`${modelIndex}:${versionIndex}`]" />
                  <DownOutlined v-else />
                </a-button>
              </template>
              <p v-else class="classifier-empty prompt-empty">
                {{ t("router.strategyNoPromptText") }}
              </p>
            </a-tab-pane>
          </a-tabs>
        </div>
      </details>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue";
import type { ComponentPublicInstance } from "vue";
import {
  CheckCircleFilled,
  CopyOutlined,
  DownOutlined,
  RightOutlined,
  UpOutlined,
} from "@ant-design/icons-vue";
import { useI18n } from "vue-i18n";
import { copyText } from "@/utils/clipboard";
import type { StrategyClassifierOption } from "@/types/router";

const props = defineProps<{
  options: StrategyClassifierOption[];
  rules?: unknown;
}>();
const { t } = useI18n();
const activeVersions = ref<Record<string, string>>({});
const initialOpenModels = ref(new Set<string>());
const expanded = reactive<Record<string, boolean>>({});
const overflowing = reactive<Record<string, boolean>>({});
const isRecord = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);
const modelRules = computed(() => {
  if (!Array.isArray(props.rules)) return [];
  return props.rules.flatMap((rule: unknown) => {
    if (!isRecord(rule) || rule.type !== "ModelBasedRule" || !isRecord(rule.param))
      return [];
    if (typeof rule.param.model !== "string") return [];
    return [{
      model: rule.param.model,
      configured: rule.param.version,
      effective: isRecord(rule.prompt_info) && rule.prompt_info.status === "ok"
        ? rule.prompt_info.effective
        : undefined,
    }];
  });
});
const isEffective = (model: string, version: string) =>
  modelRules.value.some((rule) => rule.model === model && rule.effective === version);
const isConfigured = (model: string, version: string) =>
  modelRules.value.some((rule) => rule.model === model && rule.configured === version);
const hasText = (text: string | null | undefined): text is string =>
  typeof text === "string" && text.trim().length > 0;

watch([() => props.options, modelRules], () => {
  activeVersions.value = Object.fromEntries(props.options.map((option) => {
    const versions = option.versions || [];
    const selected = versions.find((version) => isEffective(option.model, version.version))
      || versions.find((version) => isConfigured(option.model, version.version))
      || versions[0];
    return [option.model, selected?.version || ""];
  }));
  const usedModels = props.options.filter((option) =>
    modelRules.value.some((rule) => rule.model === option.model),
  );
  initialOpenModels.value = new Set(
    (usedModels.length ? usedModels : props.options.slice(0, 1)).map((option) => option.model),
  );
  for (const key of Object.keys(expanded)) delete expanded[key];
}, { immediate: true });

const promptElements = new Map<string, HTMLElement>();
let resizeObserver: ResizeObserver | undefined;
const measurePrompt = (element: HTMLElement, key: string) => {
  if (!element.clientWidth) return;
  const style = getComputedStyle(element);
  const collapsedHeight = parseFloat(style.lineHeight) * 8
    + parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);
  overflowing[key] = element.scrollHeight > collapsedHeight + 1;
};
const observePrompt = (
  element: Element | ComponentPublicInstance | null,
  key: string,
) => {
  const previous = promptElements.get(key);
  if (previous === element) return;
  if (previous) resizeObserver?.unobserve(previous);
  promptElements.delete(key);
  if (!(element instanceof HTMLElement)) return;
  if (!resizeObserver) {
    resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        for (const [promptKey, promptElement] of promptElements) {
          if (promptElement === entry.target) measurePrompt(promptElement, promptKey);
        }
      }
    });
  }
  promptElements.set(key, element);
  resizeObserver.observe(element);
  measurePrompt(element, key);
};
onBeforeUnmount(() => resizeObserver?.disconnect());
</script>

<style scoped lang="less">
.classifier-section {
  display: grid;
  gap: 10px;
  min-width: 0;
  color: var(--font-main-color);
  font-size: var(--font-size-12);
}
.classifier-heading,
.prompt-heading,
.classifier-version-label {
  display: flex;
  align-items: center;
  gap: 8px;
}
.classifier-heading {
  justify-content: space-between;
  flex-wrap: wrap;
  strong { font-size: var(--font-size-13); }
}
.classifier-meta,
.classifier-empty {
  color: var(--font-tip-color);
}
.classifier-meta { flex-shrink: 0; }
.classifier-card {
  min-width: 0;
  border: 1px solid color-mix(in srgb, var(--border-main-color) 72%, transparent);
  border-radius: 8px;
  background: var(--surface-panel-bg-strong);
  summary {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 14px 12px;
    cursor: pointer;
    list-style: none;
    &::-webkit-details-marker { display: none; }
    &:focus-visible { outline: 2px solid var(--color-primary); outline-offset: -2px; }
  }
}
.classifier-chevron { font-size: 8px; transition: transform 0.15s; }
.classifier-card[open] > summary .classifier-chevron { transform: rotate(90deg); }
.classifier-model {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
  font-weight: 600;
  font-size: var(--font-size-15);
}
.classifier-body {
  padding: 0 12px 12px;
  border-top: 1px solid color-mix(in srgb, var(--border-main-color) 50%, transparent);
  :deep(.ant-tabs-nav) { margin-bottom: 12px; }
  :deep(.ant-tabs-tab) { font-size: var(--font-size-12); }
  :deep(.ant-tabs-tab + .ant-tabs-tab) { margin-left: 18px; }
}
.classifier-badge {
  padding: 1px 5px;
  border-radius: 4px;
  color: var(--font-tip-color);
  background: color-mix(in srgb, var(--font-tip-color) 10%, transparent);
  font-size: 10px;
  font-weight: 400;
  text-shadow: none;
}
.classifier-effective-icon {
  color: var(--color-success);
  font-size: 12px;
  flex-shrink: 0;
}
.prompt-heading { margin-bottom: 8px; min-height: 24px; }
.prompt-heading > strong {
  font-size: var(--font-size-12);
  font-weight: 500;
}
.prompt-kind {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 8px;
  border-radius: 999px;
  color: var(--font-tip-color);
  background: color-mix(in srgb, var(--font-tip-color) 8%, transparent);
  font-size: 10px;
  font-weight: 500;
  line-height: 1.6;
  text-transform: capitalize;
}
.prompt-kind-hard {
  color: var(--color-primary);
  background: color-mix(in srgb, var(--color-primary) 7%, transparent);
}
.prompt-kind-dot {
  width: 5px;
  height: 5px;
  flex-shrink: 0;
  border-radius: 50%;
  background: currentColor;
}
.prompt-kind-soft {
  color: var(--color-warning-strong);
  background: color-mix(in srgb, var(--color-warning-strong) 8%, transparent);
}
.prompt-copy { margin-left: auto; font-size: var(--font-size-12); }
.prompt-text {
  box-sizing: border-box;
  max-height: calc(8 * 1.6em + 26px);
  overflow: hidden;
  margin: 0;
  padding: 12px;
  border: 1px solid color-mix(in srgb, var(--border-main-color) 60%, transparent);
  border-radius: 6px;
  background: color-mix(in srgb, var(--font-tip-color) 5%, transparent);
  color: var(--font-main-color);
  font-family: Consolas, "Liberation Mono", monospace;
  font-size: var(--font-size-12);
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  &.is-expanded { max-height: none; }
}
.prompt-expand {
  display: flex;
  align-items: center;
  width: fit-content;
  height: 28px;
  margin: 6px 0 0 auto;
  padding: 0 6px;
  border-color: transparent;
  border-radius: 4px;
  background: transparent;
  box-shadow: none;
  color: var(--color-primary);
  font-size: var(--font-size-12);
  font-weight: 500;
  cursor: pointer;
  :deep(.anticon) { font-size: 10px; }
  &:hover {
    border-color: transparent;
    color: var(--color-primary);
    background: color-mix(in srgb, var(--font-tip-color) 6%, transparent);
  }
  &:focus-visible {
    outline: 2px solid var(--color-primary);
    outline-offset: 2px;
  }
}
.classifier-empty { margin: 0; padding: 16px 0; line-height: 1.6; }
.prompt-empty {
  padding: 18px 12px;
  border: 1px dashed var(--border-main-color);
  border-radius: 6px;
  text-align: center;
}
</style>
