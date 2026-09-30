// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { inject } from "vue";
import { customNotification } from "./notification";
import { sessionAppStore } from "@/store/session";

// Access the globally provided notification instance.
export const useNotification = () => {
  const customNotificationInjected =
    inject<typeof customNotification>("customNotification");

  if (!customNotificationInjected) {
    throw new Error("Notification service not provided");
  }
  return {
    antNotification: customNotificationInjected,
  };
};

// Round a number to a fixed count of decimal places.
export const formatDecimals = (num: number, decimalPlaces: number = 2) => {
  const factor = Math.pow(10, decimalPlaces);
  return Math.round(num * factor) / factor;
};

// Capitalize a substring at the given start and length.
export const formatCapitalize = (
  string: string,
  start: number = 0,
  length: number = 1,
) => {
  const end = start + length;
  const part1 = string.slice(0, start);
  const part2 = string.slice(start, end).toUpperCase();
  const part3 = string.slice(end);
  return part1 + part2 + part3;
};

// Get or create a persistent chat session id.
export const getChatSessionId = (): string => {
  const sessionStore = sessionAppStore();

  const storedSessionId = sessionStore.currentSession;
  if (storedSessionId) {
    return storedSessionId;
  }
  const newSessionId = self.crypto?.randomUUID?.() || generateFallbackId();

  sessionStore.setSessionId(newSessionId);
  return newSessionId;
};

const generateFallbackId = (): string => {
  if (
    typeof self !== "undefined" &&
    self.crypto &&
    self.crypto.getRandomValues
  ) {
    const array = new Uint32Array(2);
    self.crypto.getRandomValues(array);
    const randomPart = Array.from(array)
      .map((num) => num.toString(36))
      .join("");
    return `${Date.now()}_${randomPart}`;
  } else {
    throw new Error(
      "No secure random number generator available for session ID generation.",
    );
  }
};

// Trigger browser download for JSON data.
export const downloadJson = (
  data: object | string,
  filename: string = "pipeline.json",
) => {
  const jsonStr: string =
    typeof data === "string" ? data : JSON.stringify(data, null, 2);

  const blob: Blob = new Blob([jsonStr], { type: "application/json" });

  const url: string = URL.createObjectURL(blob);

  const a: HTMLAnchorElement = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();

  document.body.removeChild(a);
  URL.revokeObjectURL(url);
};

// Normalize text with optional spacing and case controls.
export const formatTextStrict = (
  str: string,
  options?: {
    preserveSpaces?: boolean;
    keepOriginalCase?: boolean;
  },
): string => {
  const { preserveSpaces = true, keepOriginalCase = false } = options || {};

  // replace _ and -
  let processed = str.replace(/[_-]/g, " ");

  if (!preserveSpaces) {
    processed = processed.replace(/\s+/g, " ");
  }
  return processed
    .split(preserveSpaces ? /(\s+)/ : /\s+/)
    .map((segment) => {
      if (segment.trim() === "") {
        return segment;
      }
      const firstChar = segment.charAt(0).toUpperCase();
      const restChars = keepOriginalCase
        ? segment.slice(1)
        : segment.slice(1).toLowerCase();
      return firstChar + restChars;
    })
    .join("");
};

// Find an enum-like item by key and return a target field.
export const getEnumField = <T extends readonly Record<string, any>[]>(
  list: T,
  inputValue: any,
  matchKey: string = "value",
  outputKey: string = "name",
): any => {
  const item = list.find((item) => item[matchKey] === inputValue);
  return item?.[outputKey];
};

// Convert unknown input to finite number with fallback.
export const normalizeNumber = (value: unknown, fallback: number = 0) => {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : fallback;
};

// Convert unknown input to finite number or null.
export const normalizeNullableNumber = (value: unknown) => {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : null;
};

// Format values for UI display with empty placeholder support.
export const formatDisplayValue = (
  value: unknown,
  emptyText: string = "--",
) => {
  if (value === null || value === undefined || value === "") return emptyText;
  if (typeof value === "object") {
    if (Array.isArray(value) && !value.length) return emptyText;
    if (!Array.isArray(value) && !Object.keys(value as object).length)
      return emptyText;
    return JSON.stringify(value);
  }
  return String(value);
};

// Map truthy/falsy values to localized text.
export const formatBooleanText = (
  value: unknown,
  yesText: string,
  noText: string,
) => {
  return value ? yesText : noText;
};

// Convert JSON-like data to pretty text with fallback options.
export const formatJsonText = (
  value: unknown,
  options?: {
    fallback?: string;
    emptyCollectionsAsFallback?: boolean;
    emptyJsonStringsAsFallback?: boolean;
  },
) => {
  const {
    fallback = "",
    emptyCollectionsAsFallback = true,
    emptyJsonStringsAsFallback = true,
  } = options || {};

  if (value === null || value === undefined || value === "") return fallback;

  if (Array.isArray(value)) {
    if (emptyCollectionsAsFallback && value.length === 0) return fallback;
    return JSON.stringify(value, null, 2);
  }

  if (typeof value === "object") {
    if (
      emptyCollectionsAsFallback &&
      Object.keys(value as object).length === 0
    ) {
      return fallback;
    }
    return JSON.stringify(value, null, 2);
  }

  if (typeof value === "string") {
    const trimmedValue = value.trim();
    if (!trimmedValue) return fallback;
    if (
      emptyJsonStringsAsFallback &&
      (trimmedValue === "[]" || trimmedValue === "{}")
    ) {
      return fallback;
    }
    return value;
  }

  return String(value);
};

// Parse JSON text or return fallback when empty.
export const parseJsonText = <T>(value: string, fallback: T): T => {
  const trimmedValue = value.trim();
  return trimmedValue ? (JSON.parse(trimmedValue) as T) : fallback;
};
