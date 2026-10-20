// SPDX-FileCopyrightText: (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Selector logic for the OEP CLI Installer.
//
// Configuration (profiles, modules, outputs, links) lives in the sibling
// `config.json` file and is loaded at runtime. Keeping the data separate from
// this logic means profiles, modules, and links can be edited without touching
// the selector code.
let CONFIG = {};

// --- small helpers ---
const $ = (sel, root = document) => root.querySelector(sel);
const el = (tag, cls, txt) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (txt != null) n.textContent = txt;
  return n;
};

const parseQuery = (keys) => {
  const qs = new URLSearchParams(location.search);
  const out = {};
  for (const k of keys) {
    const v = qs.get(k);
    if (v) out[k] = v;
  }
  return out;
};

const writeQuery = (state, keys) => {
  const qs = new URLSearchParams();
  keys.forEach((k) => {
    const v = state[k];
    if (v != null && v !== "") qs.set(k, String(v));
  });
  const q = `?${qs.toString()}`;
  history.replaceState({}, "", q);
  return location.origin + location.pathname + q;
};

// {{KEY}} or {{KEY|dotver}}
const interpolate = (text, sel) =>
  text.replace(/\{\{\s*([A-Z0-9_]+)(?:\|([a-z]+))?\s*\}\}/g, (_, key, filter) => {
    let v = sel[key] ?? "";
    if (filter === "dotver") v = v.startsWith("v_") ? v.slice(2).replaceAll("_", ".") : v;
    return String(v);
  });

const firstMatch = (rules, sel) => {
  for (const r of rules || []) {
    const cond = r.when || {};
    const ok = Object.keys(cond).every((k) => String(sel[k] ?? "") === String(cond[k]));
    if (ok) return r;
  }
  return null;
};

// Look up the option object for a given category key and its currently selected
// value (e.g. the selected MODULE option). Returns null if not found.
function findSelectedOption(categoryKey, state) {
  const cat = (CONFIG.categories || []).find((c) => c.key === categoryKey);
  if (!cat) return null;
  return (cat.options || []).find(
    (o) => o.value === state[categoryKey] && isOptionAvailable(cat, o, state)
  ) || null;
}

// Return the `installAll` flag of the currently selected PROFILE option. When
// true, the selected profile installs every one of its modules at once, so the
// dependent Module category is shown read-only and the install command is keyed
// off the profile (see the profile-specific rules in the `install` output).
function isInstallAllProfile(state) {
  const profileOpt = findSelectedOption("PROFILE", state);
  return Boolean(profileOpt && profileOpt.installAll);
}

// --- UI rendering ---
let STATE = {};

function init() {
  $("#app-title").textContent = CONFIG.title || "Selector";

  // defaults: first option per category
  const defaults = {};
  (CONFIG.categories || []).forEach((cat) => {
    const first = cat.options?.[0]?.value;
    if (first != null) defaults[cat.key] = first;
  });
  // state from URL (shareable)
  STATE = { ...defaults, ...parseQuery(CONFIG.shareKeys || []) };
  repairState(STATE);

  renderCategories();
  updateOutputsAndUrl();
  hookCopyButtons();
}

function renderCategories() {
  const host = $("#categories");
  host.innerHTML = "";

  (CONFIG.categories || []).forEach((cat) => {
    const sec = el("section", "st-section st-section-accent");
    const title = el("div", "st-section-title", cat.label);
    const content = el("div", "st-section-content");
    const row = el("div", "st-section-content-row");

    // Categories whose options depend on the profile (e.g. MODULE) are shown as
    // a non-selectable, read-only list when the selected profile installs all of
    // its modules at once — there is nothing to pick, so we display the modules
    // for reference only.
    const dependsOnProfile = (cat.options || []).some(
      (o) => o.supports && Object.prototype.hasOwnProperty.call(o.supports, "PROFILE")
    );
    const readOnly = dependsOnProfile && isInstallAllProfile(STATE);

    const group = el("div", "spark-button-group option-button-group");
    (cat.options || []).forEach((opt) => {
      // Hide options that are not available for the current selection (e.g.
      // modules that don't belong to the selected profile) so each category
      // only shows relevant choices.
      const available = isOptionAvailable(cat, opt, STATE);
      if (!available) return;

      const btn = el("button", "spark-button spark-button-size-l spark-button-ghost");
      const inner = el("span", "spark-button-content");
      inner.append(el("span", "", opt.label));
      if (opt.subtitle) inner.append(el("span", "subtitle", opt.subtitle));
      btn.append(inner);

      if (readOnly) {
        // Non-selectable list: render every module in the blue "selected" style
        // so it's clear all of them will be installed, but disable interaction
        // and keep them non-focusable. The install command comes from the
        // profile instead of an individual module.
        btn.classList.add("option-button-readonly", "spark-toggle-button-clicked-ghost", "pill-active");
        btn.setAttribute("aria-disabled", "true");
        btn.setAttribute("tabindex", "-1");
        group.append(btn);
        return;
      }

      const isActive = STATE[cat.key] === opt.value;
      if (isActive) btn.classList.add("spark-toggle-button-clicked-ghost", "pill-active");

      btn.addEventListener("click", () => {
        STATE[cat.key] = opt.value;
        // Clear selections in categories that depend on this one (e.g. MODULE
        // depends on PROFILE) so a stale dependent value doesn't invalidate the
        // option the user just picked. repairState then fills them with the
        // first option available for the new selection.
        clearDependents(cat.key, STATE);
        repairState(STATE);
        // Re-render everything
        renderCategories();
        updateOutputsAndUrl();
      });

      group.append(btn);
    });

    row.append(group);
    content.append(row);
    sec.append(title, content);
    host.append(sec);
  });

  renderOptions();
}

// Each options entry is one complete choice, e.g. "--gpu --docker".
// Shared URLs keep comma-separated flag names, but must match a whole configured
// combination. "none" is accepted only for an explicitly configured empty entry.
const optionsKey = () => CONFIG.options?.key || "OPTIONS";

function moduleOptions() {
  if (isInstallAllProfile(STATE)) return [];
  return findSelectedOption("MODULE", STATE)?.options || [];
}

function selectedFlags() {
  const allowed = moduleOptions();
  if (!allowed.length) return [];
  const raw = String(STATE[optionsKey()] ?? "");
  const chosen = raw === "none" ? [] : raw.split(",").map((v) => `--${v}`);
  const combinations = allowed.map((value) => value ? value.split(/\s+/) : []);
  return combinations.find((flags) =>
    flags.length === chosen.length && new Set(chosen).size === chosen.length &&
    flags.every((flag) => chosen.includes(flag))
  ) || combinations[0];
}

function setSelectedFlags(flags) {
  STATE[optionsKey()] = flags.length ? flags.map((f) => f.replace(/^--/, "")).join(",") : "none";
}

// Keep STATE (and so the share URL) in sync with what the command uses.
function syncOptionsState() {
  if (moduleOptions().length) setSelectedFlags(selectedFlags());
  else delete STATE[optionsKey()];
}

function optionLabel(value) {
  if (!value) return "Default";
  return value.split(/\s+/).map((flag) =>
    flag.slice(2).split(/[-_]/).map((word) =>
      /^[cgn]pu$/.test(word) ? word.toUpperCase() : word.charAt(0).toUpperCase() + word.slice(1)
    ).join(" ")
  ).join(" & ");
}

function renderOptions() {
  const section = $("#optionsSection");
  const host = $("#optionsHost");
  if (!section || !host) return;

  host.innerHTML = "";
  const allowed = moduleOptions();
  if (!allowed.length) {
    section.style.display = "none";
    return;
  }

  $("#optionsTitle").textContent = CONFIG.options?.label || "Options";
  const current = selectedFlags().join(" ");
  const choose = (value) => {
    setSelectedFlags(value ? value.split(/\s+/) : []);
    if (allowed.length <= 5) {
      renderOptions();
      host.querySelector('[aria-pressed="true"]')?.focus();
    }
    updateOutputsAndUrl();
  };

  if (allowed.length > 5) {
    const select = el("select");
    select.id = "optionsSelect";
    select.setAttribute("aria-labelledby", "optionsTitle");
    select.style.maxWidth = "100%";
    allowed.forEach((value) => {
      const option = el("option", "", optionLabel(value));
      option.value = value;
      option.selected = value === current;
      select.append(option);
    });
    select.addEventListener("change", () => choose(select.value));
    host.append(select);
    section.style.display = "";
    return;
  }

  allowed.forEach((value) => {
    const btn = el("button", "spark-button spark-button-size-l spark-button-ghost");
    const inner = el("span", "spark-button-content");
    inner.append(el("span", "", optionLabel(value)));
    btn.append(inner);
    btn.title = value || "No flags";

    const active = current === value;
    btn.setAttribute("aria-pressed", String(active));
    if (active) btn.classList.add("spark-toggle-button-clicked-ghost", "pill-active");

    btn.addEventListener("click", () => choose(value));

    host.append(btn);
  });

  section.style.display = "";
}

// Selected flags as a suffix for the install command (e.g. " --gpu").
function installFlags() {
  return selectedFlags().map((f) => ` ${f}`).join("");
}

// Return true if `opt` in category `cat` is compatible with the rest of `state`.
// Constraints are directional, except an install-all profile must be compatible
// with every module it installs. An individually selected module must not hide
// other profiles.
function isOptionAvailable(cat, opt, state) {
  if (cat.key === "PROFILE" && opt.installAll) {
    const modules = (CONFIG.categories || []).find((c) => c.key === "MODULE")?.options || [];
    const incompatible = modules.some((module) =>
      module.supports?.PROFILE?.includes(opt.value) &&
      module.supports?.OP_SYSTEM && state.OP_SYSTEM != null &&
      !module.supports.OP_SYSTEM.includes(state.OP_SYSTEM)
    );
    if (incompatible) return false;
  }
  // Check constraints declared by `opt` against currently selected values in other categories.
  if (opt.supports) {
    for (const otherKey of Object.keys(opt.supports)) {
      const allowed = opt.supports[otherKey];
      const selectedValue = state[otherKey];
      if (Array.isArray(allowed) && !allowed.includes(selectedValue)) {
        return false;
      }
    }
  }

  return true;
}

// Remove selections in categories that depend on `changedKey` (i.e. categories
// whose options declare `supports[changedKey]`). Used after an explicit user
// choice so a stale dependent value can't invalidate the new selection.
function clearDependents(changedKey, state) {
  (CONFIG.categories || []).forEach((cat) => {
    if (cat.key === changedKey) return;
    const dependsOnChanged = (cat.options || []).some(
      (o) => o.supports && Object.prototype.hasOwnProperty.call(o.supports, changedKey)
    );
    if (dependsOnChanged) {
      const stillAvailable = (cat.options || []).some(
        (o) => o.value === state[cat.key] && isOptionAvailable(cat, o, state)
      );
      if (!stillAvailable) delete state[cat.key];
    }
  });
}

// If the current selection in any category is no longer available given the
// rest of `state`, replace it with the first available option in that category.
function repairState(state) {
  (CONFIG.categories || []).forEach((cat) => {
    const currentValue = state[cat.key];
    const currentOpt = (cat.options || []).find(
      (o) => o.value === currentValue && isOptionAvailable(cat, o, state)
    );
    if (currentOpt) return;
    const firstAvailable = (cat.options || []).find((o) => isOptionAvailable(cat, o, state));
    if (firstAvailable) state[cat.key] = firstAvailable.value;
    else delete state[cat.key];
  });
}

// Build a runnable command in a code box with a Copy button, matching the
// Install section styling. `copyId` must be unique so flashCopied can target it.
function makeCommandBox(cmdText, copyId) {
  const box = document.createElement("div");
  box.className = "code-box st-code-snippet-multi-line";
  box.style.minWidth = "300px";
  box.style.width = "100%";

  const btn = document.createElement("button");
  btn.id = copyId;
  btn.className = "spark-button spark-button-size-s spark-button-primary code-copy";
  btn.textContent = "Copy";
  btn.addEventListener("click", async () => {
    try {
      btn.disabled = true;
      await copyToClipboard(cmdText);
      btn.disabled = false;
      flashCopied("#" + copyId);
    } catch (err) {
      console.error("Copy failed:", err);
      btn.disabled = false;
      alert("Copy failed. Please try manually selecting the text and pressing Ctrl+C (or Cmd+C on Mac).");
    }
  });

  const pre = document.createElement("pre");
  pre.className = "st-code-snippet-content";
  pre.style.fontFamily = "monospace, monospace";
  pre.style.fontSize = "0.875rem";
  pre.style.lineHeight = "1.4";
  pre.style.margin = "0";
  pre.style.padding = "0";
  pre.style.whiteSpace = "pre-line";
  pre.style.wordWrap = "break-word";
  pre.style.overflowWrap = "break-word";
  pre.style.maxWidth = "100%";
  pre.style.width = "100%";
  pre.textContent = cmdText;

  box.appendChild(btn);
  box.appendChild(pre);
  return box;
}

// A small heading shown above a lifecycle command.
function makeStepLabel(text) {
  const label = el("div", "st-next-step-label", text);
  label.style.fontWeight = "600";
  label.style.margin = "0.75rem 0 0.25rem";
  return label;
}

function updateOutputsAndUrl() {
  // keep URL in sync
  syncOptionsState();
  writeQuery(STATE, CONFIG.shareKeys || []);
  const profile = findSelectedOption("PROFILE", STATE);
  const module = findSelectedOption("MODULE", STATE);
  const installAll = isInstallAllProfile(STATE);
  const hasTarget = Boolean(profile && (installAll || module));

  // compute outputs
  (CONFIG.outputs || []).forEach((o) => {
    const matched = firstMatch(o.rules, STATE);

    if (o.id === "install") {
      $("#copyCmd").disabled = !hasTarget || !matched?.text;
      if (!hasTarget) {
        $("#installText").textContent = "No compatible modules available for this selection.";
        return;
      }
      const finalText = matched?.text ? interpolate(String(matched.text), STATE) : (o.fallback ?? "");
      const suffix = installFlags() + (!installAll && module?.startStop ? " start" : "");
      $("#installText").textContent = matched?.text ? finalText + suffix : finalText;
    }

    if (o.id === "nextsteps") {
      const section = $("#nextStepsSection");
      const container = $("#nextStepsText");
      container.innerHTML = "";

      const startStop = o.startStop;
      if (hasTarget && !installAll && module?.startStop && startStop) {
        if (startStop.start) {
          const startText = interpolate(String(startStop.start), STATE);
          container.appendChild(makeStepLabel("Start"));
          container.appendChild(makeCommandBox(startText, "copyNextStart"));
        }

        if (startStop.stop) {
          const stopText = interpolate(String(startStop.stop), STATE);
          container.appendChild(makeStepLabel("Stop"));
          container.appendChild(makeCommandBox(stopText, "copyNextStop"));
        }
      }
      const target = installAll ? profile : module;
      if (hasTarget && target?.remove && o.remove) {
        const removeText = interpolate(String(o.remove), { ...STATE, TARGET: target.value });
        container.appendChild(makeStepLabel("Remove"));
        container.appendChild(makeCommandBox(removeText, "copyNextRemove"));
      }
      if (section) section.style.display = container.childElementCount ? "" : "none";
    }

    if (o.id === "getstarted") {
      const container = $("#getStartedText");
      container.innerHTML = "";
      if (matched?.text && matched?.link) {
        const link = document.createElement("a");
        link.href = matched.link;
        link.target = "_blank";
        link.className = "spark-hyperlink spark-hyperlink-primary";
        link.textContent = matched.text;
        container.appendChild(link);
      } else {
        container.textContent = o.fallback ?? "";
      }
    }

    if (o.id === "resources") {
      const container = $("#resourcesText");
      if (matched?.links && Array.isArray(matched.links)) {
        container.innerHTML = "";
        matched.links.forEach((linkObj, index) => {
          const link = document.createElement("a");
          link.href = linkObj.url;
          link.target = "_blank";
          link.className = "spark-hyperlink spark-hyperlink-primary";
          link.textContent = linkObj.text;
          container.appendChild(link);
          if (index < matched.links.length - 1) {
            container.appendChild(document.createElement("br"));
          }
        });
      } else {
        container.textContent = o.fallback ?? "";
      }
    }
  });
}

function copyToClipboard(text) {
  // Try modern clipboard API first if available and in secure context
  if (navigator.clipboard && navigator.clipboard.writeText) {
    return navigator.clipboard.writeText(text).catch(err => {
      console.warn('Clipboard API failed, falling back to legacy method:', err);
      return copyToClipboardFallback(text);
    });
  }

  // Fallback for older browsers or non-secure contexts
  return copyToClipboardFallback(text);
}

function copyToClipboardFallback(text) {
  return new Promise((resolve, reject) => {
    const textArea = document.createElement('textarea');
    textArea.value = text;

    // Ensure the textarea is visible and properly positioned
    textArea.style.position = 'absolute';
    textArea.style.left = '0';
    textArea.style.top = '0';
    textArea.style.opacity = '0';
    textArea.style.pointerEvents = 'none';
    textArea.style.zIndex = '-1';

    // Make it readable
    textArea.setAttribute('readonly', '');
    textArea.style.border = 'none';
    textArea.style.outline = 'none';
    textArea.style.boxShadow = 'none';
    textArea.style.background = 'transparent';

    document.body.appendChild(textArea);

    try {
      // Focus and select
      textArea.focus();
      textArea.select();
      textArea.setSelectionRange(0, textArea.value.length);

      // Try execCommand
      const successful = document.execCommand('copy');
      document.body.removeChild(textArea);

      if (successful) {
        resolve();
      } else {
        reject(new Error('Copy failed'));
      }
    } catch (err) {
      document.body.removeChild(textArea);
      reject(err);
    }
  });
}



function hookCopyButtons() {
  const copyCmd = $("#copyCmd");
  if (copyCmd) {
    copyCmd.addEventListener("click", async () => {
    const text = $("#installText").textContent.trim();
    if (!text || text === "Select options to see a command…") {
      alert("No command to copy. Please select your options first.");
      return;
    }

    const btn = $("#copyCmd");

    try {
      btn.disabled = true;
      await copyToClipboard(text);
      btn.disabled = false;
      flashCopied("#copyCmd");
    } catch (err) {
      console.error('Copy failed:', err);
      btn.disabled = false;
      alert("Copy failed. Please try manually selecting the text and pressing Ctrl+C (or Cmd+C on Mac).");
    }
    });
  }
}

function flashCopied(sel) {
  const btn = document.querySelector(sel);
  if (!btn) return; // Guard against missing elements

  const old = btn.textContent;
  btn.textContent = "Copied!";
  setTimeout(() => {
    // Only reset if the button text hasn't changed (to avoid conflicts)
    if (btn.textContent === "Copied!") {
      btn.textContent = old;
    }
  }, 900);
}

// Load the configuration, then bootstrap the UI. The config path is resolved
// relative to this script so it works regardless of where the page is served.
//
// `document.currentScript` is only available while the script is executing, so
// capture the config URL now (before the async DOMContentLoaded callback runs).
const CONFIG_URL = new URL("config.json", document.currentScript.src);

async function bootstrapFromUrl() {
  try {
    const res = await fetch(CONFIG_URL);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    CONFIG = await res.json();
  } catch (err) {
    console.error("Failed to load config.json:", err);
    const title = $("#app-title");
    if (title) title.textContent = "Failed to load configuration";
    return;
  }
  init();
}

document.addEventListener("DOMContentLoaded", bootstrapFromUrl);
