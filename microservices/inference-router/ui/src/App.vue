<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

<template>
  <a-config-provider
    :locale="antLocale"
    :theme="currentTheme"
    prefixCls="intel"
    autoInsertSpaceInButton
  >
    <router-view />
  </a-config-provider>
</template>
<script setup lang="ts">
import { themeAppStore } from "@/store/theme";
import { antTheme } from "@/utils/antTheme";
import enLocale from "ant-design-vue/es/locale/en_US";
import zhLocale from "ant-design-vue/es/locale/zh_CN";
import { computed } from "vue";
import { useI18n } from "vue-i18n";

const themeStore = themeAppStore();

const currentTheme = computed(() => {
  return antTheme[themeStore.theme as keyof typeof antTheme];
});

const { locale } = useI18n();
const antLocale = computed(() =>
  locale.value === "zh_CN" ? zhLocale : enLocale,
);
</script>
<style scoped lang="less"></style>
