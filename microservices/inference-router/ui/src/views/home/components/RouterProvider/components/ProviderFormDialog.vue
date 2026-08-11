<template>
  <a-modal
    :open="true"
    :title="dialogTitle"
    :confirm-loading="submitting"
    :ok-text="t('common.save')"
    :cancel-text="t('common.cancel')"
    width="640px"
    class="router-provider-form-dialog"
    @ok="handleSubmit"
    @cancel="emit('close')"
  >
    <div class="router-provider-form-scroll">
      <a-form
        ref="formRef"
        :model="formModel"
        :rules="rules"
        layout="vertical"
        class="router-provider-form"
      >
        <a-form-item :label="t('router.routerProviderName')" name="name">
          <a-input
            v-model:value="formModel.name"
            :disabled="isEdit"
            :placeholder="t('router.routerProviderNamePlaceholder')"
          />
        </a-form-item>
        <a-form-item :label="t('router.routerProviderType')" name="type">
          <a-select
            v-model:value="formModel.type"
            :placeholder="t('router.routerProviderTypePlaceholder')"
          >
            <a-select-option
              v-for="typeOption in typeOptions"
              :key="typeOption"
              :value="typeOption"
            >
              {{ typeOption }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item :label="t('router.routerProviderModel')" name="model">
          <a-select
            v-model:value="formModel.model"
            show-search
            :loading="isLoadingModels"
            :placeholder="t('router.routerProviderModelPlaceholder')"
          >
            <a-select-option
              v-for="modelOption in modelOptions"
              :key="modelOption"
              :value="modelOption"
            >
              {{ modelOption }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item :label="t('router.routerProviderEnabled')" name="enabled">
          <a-radio-group v-model:value="formModel.enabled" button-style="solid">
            <a-radio :value="true">{{ t("common.yes") }}</a-radio>
            <a-radio :value="false">{{ t("common.no") }}</a-radio>
          </a-radio-group>
        </a-form-item>
        <a-form-item
          :label="t('router.routerProviderMetadata')"
          name="metadataText"
        >
          <a-textarea
            v-model:value="formModel.metadataText"
            :rows="4"
            :placeholder="t('router.routerProviderJsonPlaceholder')"
          />
        </a-form-item>
        <a-form-item
          :label="t('router.routerProviderSettings')"
          name="settingsText"
        >
          <a-textarea
            v-model:value="formModel.settingsText"
            :rows="4"
            :placeholder="t('router.routerProviderJsonPlaceholder')"
          />
        </a-form-item>
      </a-form>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { getRouterModels, updateRouterProvider } from "@/api/router";
import type {
  ConfigProviderRow,
  RouterProviderDialogType,
  RouterProviderPayload,
} from "@/views/home/type";

interface RouterProviderFormModel {
  name: string;
  type: string | undefined;
  model: string | undefined;
  enabled: boolean;
  metadataText: string;
  settingsText: string;
}

interface RouterProviderModelRow {
  id?: unknown;
}

const props = withDefaults(
  defineProps<{
    dialogData?: ConfigProviderRow;
    dialogType: RouterProviderDialogType;
  }>(),
  {
    dialogData: () => ({}),
  },
);

const emit = defineEmits<{
  close: [];
  saved: [];
}>();

const { t } = useI18n();
const validPattern = /^[a-zA-Z0-9_]+$/;
const typeOptions = ["hosted_vllm", "openai"];
const formRef = ref<{ validate: () => Promise<void> }>();
const submitting = ref(false);
const isLoadingModels = ref(false);
const modelOptions = ref<string[]>([]);
const formModel = reactive<RouterProviderFormModel>({
  name: "",
  type: undefined,
  model: undefined,
  enabled: false,
  metadataText: "",
  settingsText: "",
});

const isEdit = computed(() => props.dialogType === "edit");
const dialogTitle = computed(() =>
  isEdit.value
    ? t("router.routerProviderEditTitle")
    : t("router.routerProviderCreateTitle"),
);

const formatJsonText = (value: unknown) => {
  if (value === null || value === undefined || value === "") return "";
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
};

const parseJsonText = (value: string) => {
  const trimmedValue = value.trim();
  return trimmedValue ? JSON.parse(trimmedValue) : {};
};

const validateJson = (_rule: unknown, value: string) => {
  try {
    parseJsonText(value || "");
    return Promise.resolve();
  } catch {
    return Promise.reject(t("router.routerProviderJsonRule"));
  }
};

const rules: FormRules = reactive({
  name: [
    {
      required: true,
      message: t("router.routerProviderNameRequired"),
      trigger: "blur",
    },
    {
      pattern: validPattern,
      message: t("router.routerProviderNamePattern"),
      trigger: "blur",
    },
  ],
  type: [
    {
      required: true,
      message: t("router.routerProviderTypeRequired"),
      trigger: "change",
    },
  ],
  model: [
    {
      required: true,
      message: t("router.routerProviderModelRequired"),
      trigger: "change",
    },
  ],
  enabled: [
    {
      required: true,
      trigger: "change",
    },
  ],
  metadataText: [{ validator: validateJson, trigger: "blur" }],
  settingsText: [{ validator: validateJson, trigger: "blur" }],
});

const normalizeModelOptions = (response: unknown) => {
  const responseRecord = response as Record<string, unknown>;
  const rows = Array.isArray(responseRecord?.data)
    ? responseRecord.data
    : Array.isArray(response)
      ? response
      : [];

  return rows
    .map((row) => {
      if (typeof row === "string") return row;
      const modelRow = row as RouterProviderModelRow;
      return typeof modelRow.id === "string" ? modelRow.id : "";
    })
    .filter(Boolean);
};

const loadModels = async () => {
  isLoadingModels.value = true;
  try {
    const response = await getRouterModels();
    modelOptions.value = normalizeModelOptions(response);
    if (formModel.model && !modelOptions.value.includes(formModel.model)) {
      modelOptions.value = [formModel.model, ...modelOptions.value];
    }
  } finally {
    isLoadingModels.value = false;
  }
};

const syncFormModel = () => {
  const provider = props.dialogData || {};
  formModel.name = typeof provider.name === "string" ? provider.name : "";
  formModel.type =
    typeof provider.type === "string" ? provider.type : undefined;
  formModel.model =
    typeof provider.model === "string" ? provider.model : undefined;
  formModel.enabled = Boolean(provider.enabled);
  formModel.metadataText = formatJsonText(provider.metadata);
  formModel.settingsText = formatJsonText(provider.settings);
  if (formModel.model && !modelOptions.value.includes(formModel.model)) {
    modelOptions.value = [formModel.model, ...modelOptions.value];
  }
};

const handleSubmit = async () => {
  submitting.value = true;
  try {
    await formRef.value?.validate();
    const payload: RouterProviderPayload = {
      type: formModel.type || "",
      model: formModel.model || "",
      enabled: formModel.enabled,
      metadata: parseJsonText(formModel.metadataText),
      settings: parseJsonText(formModel.settingsText),
    };
    await updateRouterProvider(formModel.name, payload);
    emit("saved");
  } catch (error) {
    if (!(error as { errorFields?: unknown[] })?.errorFields)
      console.log(error);
  } finally {
    submitting.value = false;
  }
};

watch(() => props.dialogData, syncFormModel, { immediate: true, deep: true });

onMounted(() => {
  loadModels();
});
</script>

<style scoped lang="less">
.router-provider-form-scroll {
  max-height: min(72vh, 680px);
  padding-right: 6px;
  overflow-y: auto;
}
</style>
