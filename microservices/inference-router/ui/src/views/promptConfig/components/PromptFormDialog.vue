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
    width="640px"
    class="router-prompt-form-dialog"
    @cancel="emit('close')"
  >
    <a-form
      ref="formRef"
      :model="formModel"
      :rules="rules"
      layout="vertical"
      class="router-prompt-form"
    >
      <a-form-item :label="t('router.routerPromptModel')" name="model">
        <a-input
          v-model:value="formModel.model"
          :placeholder="t('router.routerPromptModelPlaceholder')"
        />
      </a-form-item>
      <a-form-item :label="t('router.routerPromptContent')" name="content">
        <a-textarea
          v-model:value="formModel.content"
          :rows="8"
          :placeholder="t('router.routerPromptContentPlaceholder')"
        />
      </a-form-item>
    </a-form>
    <template #footer>
      <div class="footer-wrap">
        <a-button type="primary" ghost @click="handleCancel">
          {{ t("common.cancel") }}
        </a-button>
        <a-button type="primary" :loading="submitting" @click="handleSubmit">
          {{ t("common.update") }}
        </a-button>
      </div>
    </template>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { createRouterPrompt, updateRouterPrompt } from "@/api/promptConfig";
import type {
  ConfigPromptRow,
  RouterPromptDialogType,
  RouterPromptPayload,
  RouterPromptUpdatePayload,
} from "@/types/router";

interface RouterPromptFormModel extends RouterPromptPayload {
  idx?: number;
  active: boolean;
}

const props = withDefaults(
  defineProps<{
    dialogData?: ConfigPromptRow;
    dialogType: RouterPromptDialogType;
  }>(),
  {
    dialogData: () => ({}),
  },
);

const emit = defineEmits<{
  close: [];
  saved: [];
}>();

const handleCancel = () => emit("close");

const { t } = useI18n();
const formRef = ref<{ validate: () => Promise<void> }>();
const submitting = ref(false);
const formModel = reactive<RouterPromptFormModel>({
  model: "",
  content: "",
  active: false,
});

const isEdit = computed(() => props.dialogType === "edit");
const dialogTitle = computed(() =>
  isEdit.value
    ? t("router.routerPromptEditTitle")
    : t("router.routerPromptCreateTitle"),
);

const rules: FormRules = reactive({
  model: [
    {
      required: true,
      message: t("router.routerPromptModelRequired"),
      trigger: "change",
    },
  ],
  content: [
    {
      required: true,
      message: t("router.routerPromptContentRequired"),
      trigger: "change",
    },
  ],
});

const syncFormModel = () => {
  const { idx, model = "", content = "", active = false } = props.dialogData;
  formModel.idx = idx;
  formModel.model = model;
  formModel.content = content;
  formModel.active = active;
};

const handleSubmit = async () => {
  try {
    await formRef.value?.validate();
    const payload: RouterPromptPayload = {
      model: formModel.model,
      content: formModel.content,
    };

    submitting.value = true;
    if (isEdit.value) {
      if (typeof formModel.idx !== "number") {
        throw new Error("Prompt detail is missing idx");
      }
      const updatePayload: RouterPromptUpdatePayload = {
        idx: formModel.idx,
        active: formModel.active,
        ...payload,
      };
      await updateRouterPrompt(updatePayload);
    } else {
      await createRouterPrompt(payload);
    }
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
</script>

<style scoped lang="less">
.footer-wrap {
  display: flex;
  justify-content: space-between;
}
</style>
