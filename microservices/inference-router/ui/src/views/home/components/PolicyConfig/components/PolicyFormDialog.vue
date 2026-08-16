<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

<template>
  <a-modal
    :open="true"
    :title="dialogTitle"
    :confirm-loading="submitting"
    centered
    destroyOnClose
    :keyboard="false"
    :maskClosable="false"
    :ok-text="t('common.save')"
    :cancel-text="t('common.cancel')"
    width="640px"
    class="router-policy-form-dialog"
    @ok="handleSubmit"
    @cancel="emit('close')"
  >
    <div class="router-policy-form-scroll">
      <a-form
        ref="formRef"
        :model="formModel"
        :rules="rules"
        layout="vertical"
        class="router-policy-form"
      >
        <a-form-item :label="t('router.routerPolicyName')" name="name">
          <a-input
            v-model:value="formModel.name"
            :disabled="isEdit"
            :placeholder="t('router.routerPolicyNamePlaceholder')"
          />
        </a-form-item>
        <a-form-item
          :label="t('router.routerPolicyCriterion')"
          name="criterion"
        >
          <a-select
            v-model:value="formModel.criterion"
            :placeholder="t('router.routerPolicyCriterionPlaceholder')"
          >
            <a-select-option
              v-for="criterionOption in criterionOptions"
              :key="criterionOption"
              :value="criterionOption"
            >
              {{ criterionOption }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item name="strategies">
          <template #label>
            <span>{{ t("router.routerPolicyStrategies") }}</span>
            <span v-if="showStrategiesEmptyHint" class="strategies-empty-hint">
              <ExclamationCircleFilled class="router-tip-icon" />
              {{ t("router.routerPolicyStrategiesEmptyHint") }}
            </span>
          </template>
          <a-select
            v-model:value="formModel.strategies"
            mode="multiple"
            show-search
            :loading="isLoadingStrategies"
            @dropdownVisibleChange="handleStrategiesVisible"
            :placeholder="t('router.routerPolicyStrategiesPlaceholder')"
          >
            <a-select-option
              v-for="strategy in strategyOptions"
              :key="strategy.name"
              :value="strategy.name"
            >
              {{ strategy.name }}
            </a-select-option>
          </a-select>
        </a-form-item>
      </a-form>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ExclamationCircleFilled } from "@ant-design/icons-vue";
import { getRouterStrategies, updateRouterPolicy } from "@/api/router";
import type {
  PolicyConfigDialogType,
  PolicyConfigPayload,
  PolicyConfigRow,
} from "@/views/home/type";

interface PolicyConfigFormModel {
  name: string;
  criterion?: string;
  strategies: string[];
}

const props = withDefaults(
  defineProps<{
    dialogData?: PolicyConfigRow;
    dialogType: PolicyConfigDialogType;
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
const validPattern = /^[a-zA-Z0-9._-]+$/;
const criterionOptions = ["FirstMatch", "AllMatch"];
const formRef = ref<{ validate: () => Promise<void> }>();
const submitting = ref(false);
const isLoadingStrategies = ref(false);
const hasLoadedStrategies = ref(false);
const strategyOptions = ref<string[]>([]);
const formModel = reactive<PolicyConfigFormModel>({
  name: "",
  criterion: "FirstMatch",
  strategies: [],
});

const isEdit = computed(() => props.dialogType === "edit");
const dialogTitle = computed(() =>
  isEdit.value
    ? t("router.routerPolicyEditTitle")
    : t("router.routerPolicyCreateTitle"),
);
const showStrategiesEmptyHint = computed(
  () =>
    hasLoadedStrategies.value &&
    !isLoadingStrategies.value &&
    !strategyOptions.value.length,
);

const rules: FormRules = reactive({
  name: [
    {
      required: true,
      message: t("router.routerPolicyNameRequired"),
      trigger: "blur",
    },
    {
      pattern: validPattern,
      message: t("router.routerPolicyNamePattern"),
      trigger: "blur",
    },
  ],
  criterion: [
    {
      required: true,
      message: t("router.routerPolicyCriterionRequired"),
      trigger: "change",
    },
  ],
  strategies: [
    {
      required: true,
      type: "array",
      message: t("router.routerPolicyStrategiesRequired"),
      trigger: "change",
    },
  ],
});

const ensureSelectedStrategies = () => {
  const missingStrategies = formModel.strategies.filter(
    (strategy) => !strategyOptions.value.includes(strategy),
  );
  if (missingStrategies.length) {
    strategyOptions.value = [...missingStrategies, ...strategyOptions.value];
  }
};
const handleStrategiesVisible = async (visible: boolean) => {
  if (visible) {
    try {
      await loadStrategies();
    } catch (err) {
      console.error(err);
    }
  }
};
const loadStrategies = async () => {
  isLoadingStrategies.value = true;
  try {
    const response = await getRouterStrategies();
    strategyOptions.value = response || [];
    hasLoadedStrategies.value = true;
    ensureSelectedStrategies();
  } finally {
    isLoadingStrategies.value = false;
  }
};

const syncFormModel = () => {
  const policy = props.dialogData || {};
  formModel.name = typeof policy.name === "string" ? policy.name : "";
  formModel.criterion =
    typeof policy.criterion === "string" ? policy.criterion : "FirstMatch";
  formModel.strategies = Array.isArray(policy.strategies)
    ? policy.strategies.filter(
        (strategy): strategy is string => typeof strategy === "string",
      )
    : [];
  ensureSelectedStrategies();
};

const formatFormParam = (): PolicyConfigPayload => {
  return {
    criterion: formModel.criterion || "",
    strategies: [...formModel.strategies],
  };
};

const handleSubmit = async () => {
  try {
    await formRef.value?.validate();
    const { name } = formModel;

    submitting.value = true;
    updateRouterPolicy(name, formatFormParam())
      .then(() => {
        emit("saved");
      })
      .catch((error) => {
        console.log(error);
      })
      .finally(() => {
        submitting.value = false;
      });
  } catch (error) {
    if (!(error as { errorFields?: unknown[] })?.errorFields) {
      console.log(error);
    }
  }
};

watch(() => props.dialogData, syncFormModel, { immediate: true, deep: true });

onMounted(() => {
  loadStrategies();
});
</script>

<style scoped lang="less">
.router-policy-form-scroll {
  padding-right: 6px;
  overflow-y: auto;
}
.strategies-empty-hint {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: 8px;
  color: var(--font-tip-color);
  font-size: var(--font-size-11);
  font-weight: 400;
}
.router-tip-icon {
  color: var(--color-warning-strong);
  font-size: var(--font-size-12);
}
</style>
