// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { theme } from "ant-design-vue";

const getThemeColor = (name: string) => {
  const color = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  if (!color) {
    throw new Error(`Missing theme color variable: ${name}`);
  }
  return color;
};

const createTheme = (algorithm: typeof theme.defaultAlgorithm) => ({
  algorithm,
  inherit: false,
  token: {
    colorPrimary: getThemeColor("--color-primary"),
    colorPrimaryBg: getThemeColor("--color-primaryBg"),
    colorError: getThemeColor("--color-error"),
    colorInfo: getThemeColor("--color-info"),
    colorSuccess: getThemeColor("--color-success"),
    colorWarning: getThemeColor("--color-warning"),
    colorTextBase: getThemeColor("--font-main-color"),
    colorSuccessBg: getThemeColor("--color-successBg"),
    colorWarningBg: getThemeColor("--color-warningBg"),
    colorErrorBg: getThemeColor("--color-errorBg"),
    colorInfoBg: getThemeColor("--color-infoBg"),
  },
  cssVar: true,
});

// Resolve after data-theme is applied; Ant Design needs colors, not var() expressions.
export const antTheme = {
  get black() {
    return { token: { colorPrimary: getThemeColor("--bg-black-color") } };
  },
  get subTheme() {
    return { token: { colorPrimary: getThemeColor("--color-primary-second") } };
  },
  get success() {
    return { token: { colorPrimary: getThemeColor("--color-success") } };
  },
  get danger() {
    return { token: { colorPrimary: getThemeColor("--color-error") } };
  },
  get light() {
    return createTheme(theme.defaultAlgorithm);
  },
  get dark() {
    return createTheme(theme.darkAlgorithm);
  },
};
