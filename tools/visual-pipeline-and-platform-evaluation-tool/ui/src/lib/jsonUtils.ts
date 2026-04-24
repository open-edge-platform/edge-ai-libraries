import hljs from "highlight.js/lib/core";
import json from "highlight.js/lib/languages/json";

hljs.registerLanguage("json", json);

export const prettifyJson = (raw: string): string => {
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
};

export const highlightJson = (raw: string): string => {
  const formatted = prettifyJson(raw);
  return hljs.highlight(formatted, { language: "json" }).value;
};
