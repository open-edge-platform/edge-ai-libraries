<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

<template>
  <div class="header-wrap">
    <div class="header-shell">
      <div class="brand-wrap">
        <img :src="headerLog" alt="Intel" class="brand-logo" />
        <div class="brand-divider"></div>
        <div class="product-name">{{ $t("headerTitle") }}</div>
      </div>

      <div class="setting-wrap">
        <a-dropdown>
          <div @click.prevent>
            <div class="lang-icon utility-button">
              <SvgIcon
                class="iconfont"
                :name="
                  currentLanguage === 'en_US' ? 'icon-lang-en' : 'icon-lang-zh'
                "
                :size="20"
              />
            </div>
          </div>
          <template #overlay>
            <a-menu @click="handleLanguageChange">
              <a-menu-item key="zh_CN" :disabled="currentLanguage === 'zh_CN'"
                >简体中文</a-menu-item
              >
              <a-menu-item key="en_US" :disabled="currentLanguage === 'en_US'"
                >English</a-menu-item
              >
            </a-menu>
          </template>
        </a-dropdown>
        <div class="theme-switch" @click="handleThemeChange">
          <div class="icon-wrap" :class="{ 'slider-on': isDark }">
            <img v-if="!isDark" :src="LightIcon" alt="Sun" class="icon" />
            <img v-else :src="DarkIcon" alt="Moon" class="icon" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup name="Header">
import DarkIcon from "@/assets/svgs/dark-icon.svg";
import headerLog from "@/assets/svgs/header-log.svg";
import LightIcon from "@/assets/svgs/light-icon.svg";
import SvgIcon from "@/components/SvgIcon.vue";
import { themeAppStore } from "@/store/theme";
import { useI18n } from "vue-i18n";

const { locale } = useI18n();
const themeStore = themeAppStore();
const isDark = ref<boolean>(false);

const currentLanguage = computed(() => locale.value);
const handleLanguageChange = ({ key }: { key: string | number }) => {
  const languageKey = String(key);
  locale.value = languageKey;
  themeStore.toggleLanguage(languageKey);
};
const handleThemeChange = () => {
  isDark.value = !isDark.value;
  const theme = isDark.value ? "dark" : "light";
  const body = document.documentElement as HTMLElement;
  body.setAttribute("data-theme", theme);
  themeStore.toggleTheme(theme);
};
onMounted(() => {
  isDark.value = themeStore.theme === "dark";
});
</script>

<style scoped lang="less">
@keyframes logoAnimation {
  0% {
    transform: scale(0);
  }
  80% {
    transform: scale(1.2);
  }
  100% {
    transform: scale(1);
  }
}
.header-wrap {
  width: 100%;
}

.header-shell {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  height: 64px;
  padding: 0 4px;
  color: var(--font-main-color);
}

.brand-wrap {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 14px;
}

.brand-logo {
  width: auto;
  height: 32px;
  flex: none;
}

.brand-divider {
  width: 1px;
  height: 24px;
  flex: none;
  background: var(--border-main-color);
}

.product-name {
  color: var(--font-main-color);
  font-family: var(--header-font-family);
  font-size: 20px;
  font-weight: 600;
  white-space: nowrap;
}

.theme-switch {
  position: relative;
  flex: none;
  width: 50px;
  height: 24px;
  background-color: var(--bg-switch);
  border-radius: 15px;
  cursor: pointer;
  overflow: hidden;
}

.icon-wrap {
  position: absolute;
  top: 0;
  left: 0;
  width: 30px;
  height: 24px;
  border-radius: 50%;
  transition: transform 0.3s ease;
}

.slider-on {
  transform: translateX(20px);
}

.icon {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 20px;
  height: 20px;
  transition: opacity 0.3s ease;
}
.setting-wrap {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  min-width: 0;
  line-height: 1;
}

.utility-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.lang-icon {
  cursor: pointer;
  color: var(--font-tip-color);

  &:hover i {
    display: inline-block;
    animation: logoAnimation 0.3s ease-in-out;
  }
}

@media (max-width: 760px) {
  .header-shell {
    gap: 10px;
    padding: 0;
  }

  .brand-wrap {
    gap: 10px;
  }

  .brand-logo {
    height: 28px;
  }

  .product-name {
    overflow: hidden;
    font-size: 16px;
    text-overflow: ellipsis;
  }

  .setting-wrap {
    gap: 8px;
  }
}
</style>
