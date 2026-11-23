<!-- Copyright (C) 2025 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <a-config-provider
    :locale="getGlobalI18n"
    :theme="currentTheme"
    prefixCls="intel"
    autoInsertSpaceInButton
  >
    <router-view />
  </a-config-provider>
</template>
<script setup lang="ts">
import { themeAppStore } from "@/store/theme";
import { antTheme } from "@/utils/ant-theme";
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import enLocale from "ant-design-vue/es/locale/en_US";
import zhLocale from "ant-design-vue/es/locale/zh_CN";

const themeStore = themeAppStore();

const currentTheme = computed(() => {
  return antTheme[themeStore.theme as keyof typeof antTheme];
});

const { locale } = useI18n();
const getGlobalI18n = computed(() => {
  return locale.value === "zh_CN" ? zhLocale : enLocale;
});
</script>
<style scoped lang="less"></style>
