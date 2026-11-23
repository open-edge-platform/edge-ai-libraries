<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <a-modal
    v-model:open="modelVisible"
    :title="$t('console.createLibrary')"
    width="560px"
    centered
    :maskClosable="false"
    :confirmLoading="submitLoading"
    @ok="handleSubmit"
    @cancel="handleClose"
  >
    <div class="dialog-body">
      <div class="intro-wrap">
        <DatabaseOutlined />
        <span>{{ $t("console.librariesHint") }}</span>
      </div>
      <a-form
        ref="formRef"
        :model="form"
        :rules="rules"
        layout="vertical"
        autocomplete="off"
        @finish="handleSubmit"
      >
        <a-form-item :label="$t('console.name')" name="name">
          <a-input
            v-model:value="form.name"
            :placeholder="$t('console.libraryNameExample')"
            :maxlength="100"
          />
        </a-form-item>
        <a-form-item :label="$t('console.description')" name="description">
          <a-textarea
            v-model:value="form.description"
            :placeholder="$t('console.libraryDescriptionExample')"
            :rows="4"
          />
        </a-form-item>
      </a-form>
    </div>
    <template #footer>
      <a-button @click="handleClose">{{ $t("common.cancel") }}</a-button>
      <a-button type="primary" :loading="submitLoading" @click="handleSubmit">
        {{ $t("console.createLibrary") }}
      </a-button>
    </template>
  </a-modal>
</template>
<script lang="ts" setup name="CreateDialog">
import { computed, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import type { FormInstance } from "ant-design-vue";
import { DatabaseOutlined } from "@ant-design/icons-vue";
import { requestAssetLibraryCreate } from "@/api/console";
const emit = defineEmits<{ close: []; search: []; created: [name: string] }>();
const handleClose = () => emit("close");
const { t } = useI18n();
const modelVisible = ref(true);
const submitLoading = ref(false);
const formRef = ref<FormInstance>();
const form = reactive({ name: "", description: "" });
const rules = computed(() => ({
  name: [{ required: true, whitespace: true, message: t("console.required") }],
}));
const handleSubmit = async () => {
  try {
    await formRef.value!.validate();
  } catch {
    return;
  }
  submitLoading.value = true;
  try {
    const data = await requestAssetLibraryCreate({
      name: form.name.trim(),
      description: form.description.trim(),
    });
    emit("created", data.name);
    emit("search");
    emit("close");
  } finally {
    submitLoading.value = false;
  }
};
</script>
<style scoped lang="less">
.dialog-body {
  padding: 16px 0 8px;
}
.intro-wrap {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 16px;
  margin-bottom: 24px;
  border-radius: 6px;
  background: var(--bg-card-color);
  color: var(--font-info-color);
  line-height: 1.7;
  .anticon {
    font-size: 24px;
    color: var(--color-primary-second);
  }
}
</style>
