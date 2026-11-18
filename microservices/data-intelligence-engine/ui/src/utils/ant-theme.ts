// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { theme } from "ant-design-vue";

const themeColor = (name: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim();

export const antTheme = {
  black: {
    get token() {
      return { colorPrimary: themeColor("--color-big-icon") };
    },
  },
  subTheme: {
    get token() {
      return { colorPrimary: themeColor("--color-primary-hover") };
    },
  },
  success: {
    get token() {
      return { colorPrimary: themeColor("--color-success") };
    },
  },
  danger: {
    get token() {
      return { colorPrimary: themeColor("--color-error") };
    },
  },
  light: {
    algorithm: theme.defaultAlgorithm,
    inherit: false,
    get token() {
      return {
        colorPrimary: themeColor("--color-primary"),
        colorPrimaryBg: themeColor("--color-primaryBg"),
        colorError: themeColor("--color-error"),
        colorInfo: themeColor("--color-info"),
        colorSuccess: themeColor("--color-success"),
        colorWarning: themeColor("--color-warning"),
        colorTextBase: themeColor("--font-main-color"),
        colorSuccessBg: themeColor("--color-successBg"),
        colorWarningBg: themeColor("--color-warningBg"),
        colorErrorBg: themeColor("--color-errorBg"),
        colorInfoBg: themeColor("--bg-main-color"),
      };
    },
    cssVar: true,
  },
  dark: {
    algorithm: theme.darkAlgorithm,
    inherit: false,
    cssVar: true,
  },
};
