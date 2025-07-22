// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import i18n, { InitOptions, Resource } from 'i18next';
import { initReactI18next } from 'react-i18next';
import { enTranslations } from './translations/en.ts';

interface Resources extends Resource {
  en: {
    translation: typeof enTranslations;
  };
}

const resources: Resources = {
  en: {
    translation: { ...enTranslations },
  },
};

const options: InitOptions = {
  resources,
  lng: 'en',
  interpolation: { escapeValue: false },
};

i18n.use(initReactI18next).init(options);

export default i18n;
