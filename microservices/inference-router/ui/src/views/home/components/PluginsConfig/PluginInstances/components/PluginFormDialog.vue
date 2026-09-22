<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

<template>
  <a-modal
    :open="true"
    :title="dialogTitle"
    centered
    destroyOnClose
    :keyboard="false"
    :maskClosable="false"
    :confirm-loading="submitting"
    :ok-text="t('common.save')"
    :cancel-text="t('common.cancel')"
    width="680px"
    @ok="handleSubmit"
    @cancel="emit('close')"
  >
    <div class="router-plugin-form-scroll">
      <a-form ref="formRef" :model="formModel" :rules="rules" layout="vertical">
        <a-form-item :label="t('router.routerPluginName')" name="name">
          <a-input
            v-model:value="formModel.name"
            :disabled="isEdit"
            :placeholder="t('router.routerPluginNamePlaceholder')"
          />
        </a-form-item>
        <a-form-item :label="t('router.routerPluginNode')" name="node">
          <a-select
            v-model:value="formModel.node"
            :disabled="isEdit"
            :loading="isLoadingNodes"
            :placeholder="t('router.routerPluginNodePlaceholder')"
            @dropdownVisibleChange="handleNodesVisible"
          >
            <a-select-option
              v-for="pluginNode in nodeOptions"
              :key="pluginNode.node"
              :value="pluginNode.node"
            >
              {{ pluginNode.node }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item :label="t('router.routerPluginTrigger')" name="trigger">
          <a-select v-model:value="formModel.trigger">
            <a-select-option
              v-for="triggerOption in triggerOptions"
              :key="triggerOption"
              :value="triggerOption"
            >
              {{ triggerOption }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item :label="t('router.routerPluginEnabled')" name="enabled">
          <a-radio-group v-model:value="formModel.enabled" button-style="solid">
            <a-radio :value="true">{{ t("common.yes") }}</a-radio>
            <a-radio :value="false">{{ t("common.no") }}</a-radio>
          </a-radio-group>
        </a-form-item>
        <a-form-item
          :label="t('router.routerPluginSettings')"
          name="settingsText"
          :required="requiredSettingKeys.length > 0"
        >
          <a-textarea
            v-model:value="formModel.settingsText"
            :rows="6"
            :placeholder="t('router.routerPluginSettingsPlaceholder')"
          />
        </a-form-item>
        <div v-if="selectedNode" class="plugin-schema-preview">
          <div class="plugin-schema-header">
            <div class="plugin-schema-heading">
              {{ t("router.routerPluginSettingsSchema") }}
            </div>
            <a-button
              type="text"
              shape="circle"
              size="small"
              :title="t('common.copy')"
              :aria-label="t('common.copy')"
              @click="handleCopySchema"
            >
              <template #icon>
                <CheckOutlined v-if="copied" />
                <CopyOutlined v-else />
              </template>
            </a-button>
          </div>
          <div v-if="requiredSettingKeys.length" class="plugin-schema-required">
            <span>{{ t("router.routerPluginRequiredSettings") }}</span>
            <a-tag
              v-for="settingKey in requiredSettingKeys"
              :key="settingKey"
              color="red"
            >
              {{ settingKey }}
            </a-tag>
          </div>
          <pre>{{ formatJsonBlock(selectedNode.settings_schema) }}</pre>
        </div>
      </a-form>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { CheckOutlined, CopyOutlined } from "@ant-design/icons-vue";
import { getRouterPluginNodes, updateRouterPlugin } from "@/api/router";
import { formatJsonText, parseJsonText } from "@/utils/common";
import { useClipboard } from "@/utils/clipboard";
import type {
  ConfigPluginRow,
  PluginNodeRow,
  RouterPluginDialogType,
  RouterPluginPayload,
} from "@/views/home/type";

interface RouterPluginFormModel {
  node: string | undefined;
  name: string;
  enabled: boolean;
  trigger: ConfigPluginRow["trigger"];
  settingsText: string;
}

const props = withDefaults(
  defineProps<{
    dialogData?: Partial<ConfigPluginRow>;
    dialogType: RouterPluginDialogType;
  }>(),
  {
    dialogData: () => ({}),
  },
);

const emit = defineEmits<{ close: []; saved: [] }>();
const { t } = useI18n();
const { copied, copy } = useClipboard();
const validPattern = /^[a-zA-Z0-9_.-]+$/;
const triggerOptions: ConfigPluginRow["trigger"][] = [
  "prerouting",
  "postrouting",
  "postresponse",
];
const formRef = ref<{
  validate: () => Promise<void>;
  clearValidate: (names?: string | string[]) => void;
}>();
const submitting = ref(false);
const isLoadingNodes = ref(false);
const nodeOptions = ref<PluginNodeRow[]>([]);
const formModel = reactive<RouterPluginFormModel>({
  node: undefined,
  name: "",
  enabled: true,
  trigger: "prerouting",
  settingsText: "",
});

const isEdit = computed(() => props.dialogType === "edit");
const dialogTitle = computed(() =>
  isEdit.value
    ? t("router.routerPluginEditTitle")
    : t("router.routerPluginCreateTitle"),
);
const selectedNode = computed(() =>
  nodeOptions.value.find((pluginNode) => pluginNode.node === formModel.node),
);
const requiredSettingKeys = computed(() => {
  const required = selectedNode.value?.settings_schema?.required;
  return Array.isArray(required)
    ? required.filter((key): key is string => typeof key === "string")
    : [];
});

const validateJsonObject = (_rule: unknown, value: string) => {
  try {
    const settings = parseJsonText(value || "", {});
    if (settings && typeof settings === "object" && !Array.isArray(settings)) {
      const missingKeys = requiredSettingKeys.value.filter(
        (key) => !Object.prototype.hasOwnProperty.call(settings, key),
      );
      if (missingKeys.length) {
        return Promise.reject(
          t("router.routerPluginRequiredSettingsRule", {
            fields: missingKeys.join(", "),
          }),
        );
      }
      return Promise.resolve();
    }
  } catch {
    // Validation message is returned below.
  }
  return Promise.reject(t("router.routerPluginSettingsRule"));
};

const rules: FormRules = reactive({
  node: [
    {
      required: true,
      message: t("router.routerPluginNodeRequired"),
      trigger: "change",
    },
  ],
  name: [
    {
      required: true,
      message: t("router.routerPluginNameRequired"),
      trigger: "blur",
    },
    {
      pattern: validPattern,
      message: t("router.routerPluginNamePattern"),
      trigger: "blur",
    },
  ],
  settingsText: [{ validator: validateJsonObject, trigger: "blur" }],
});

const normalizeNodeList = (response: unknown) => {
  if (Array.isArray(response)) return response as PluginNodeRow[];
  const { data } = (response || {}) as { data?: unknown };
  return Array.isArray(data) ? (data as PluginNodeRow[]) : [];
};

const loadNodes = async () => {
  isLoadingNodes.value = true;
  try {
    nodeOptions.value = normalizeNodeList(await getRouterPluginNodes());
  } finally {
    isLoadingNodes.value = false;
  }
};

const handleNodesVisible = async (visible: boolean) => {
  if (!visible) return;
  try {
    await loadNodes();
  } catch (error) {
    console.error(error);
  }
};

const syncFormModel = () => {
  const {
    node,
    name,
    enabled = true,
    trigger = "prerouting",
    settings,
  } = props.dialogData || {};

  formModel.node = typeof node === "string" ? node : undefined;
  formModel.name = typeof name === "string" ? name : "";
  formModel.enabled = Boolean(enabled);
  formModel.trigger =
    trigger === "postrouting" || trigger === "postresponse"
      ? trigger
      : "prerouting";
  formModel.settingsText = formatJsonText(settings, { fallback: "" });
};

const formatJsonBlock = (value: unknown) =>
  formatJsonText(value, {
    fallback: "{}",
    emptyCollectionsAsFallback: false,
    emptyJsonStringsAsFallback: false,
  });

const handleCopySchema = () => {
  if (!selectedNode.value) return;
  copy(formatJsonBlock(selectedNode.value.settings_schema));
};

const handleSubmit = async () => {
  try {
    await formRef.value?.validate();
    if (!formModel.node) return;
    const payload: RouterPluginPayload = {
      enabled: formModel.enabled,
      trigger: formModel.trigger,
      settings: parseJsonText(formModel.settingsText, {}) as Record<
        string,
        unknown
      >,
    };
    submitting.value = true;
    await updateRouterPlugin(formModel.node, formModel.name, payload);
    emit("saved");
  } catch (error) {
    if (!(error as { errorFields?: unknown[] })?.errorFields) {
      console.log(error);
    }
  } finally {
    submitting.value = false;
  }
};

watch(() => props.dialogData, syncFormModel, { immediate: true, deep: true });

onMounted(() => {
  loadNodes().catch((error) => console.error(error));
});
</script>

<style scoped lang="less">
.router-plugin-form-scroll {
  max-height: min(72vh, 720px);
  padding-right: 6px;
  overflow-y: auto;
}
.plugin-schema-preview {
  display: grid;
  gap: 8px;
  padding: 12px;
  border: 1px solid
    color-mix(in srgb, var(--border-main-color) 72%, transparent);
  border-radius: 8px;
  background: var(--surface-panel-bg-strong);
}
.plugin-schema-heading {
  color: var(--font-main-color);
  font-size: var(--font-size-13);
  font-weight: 600;
}
.plugin-schema-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.plugin-schema-required {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  color: var(--font-text-color);
  font-size: var(--font-size-12);
}
.plugin-schema-required .ant-tag {
  margin-inline-end: 0;
}
.plugin-schema-preview pre {
  max-height: 220px;
  margin: 0;
  overflow: auto;
  color: var(--font-main-color);
  font-family: Consolas, "Liberation Mono", monospace;
  font-size: var(--font-size-12);
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
