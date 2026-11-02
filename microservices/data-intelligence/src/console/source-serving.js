// Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0
// A serving state belongs to one pool binding, never to the source globally.
const SourceServing = (() => {
  const state = binding => binding.serving_state || "SERVING";
  const effective = (source, binding) => source.enabled === false ? "DISABLED" : binding.effective_state || state(binding);
  const bindings = (lib, sourceId) => lib.asset_pools.flatMap(pool =>
    pool.source_statuses.filter(binding => binding.source_id === sourceId).map(binding => ({pool, binding})));
  const pending = (pool, sourceId) => pool.source_statuses.some(binding =>
    state(binding) === "PREPARING" && binding.replaces && (binding.source_id === sourceId || binding.replaces === sourceId));
  const polling = binding => !["DEPRECATED", "DISABLED"].includes(binding.effective_state || state(binding));
  const color = value => value === "SERVING" ? "ok" : value === "PREPARING" ? "warn" : "";

  function chip(binding) {
    const value = state(binding);
    return `<span class="chip serving-state ${color(value)}">${esc(value)}</span>`;
  }

  function control(lib, pool, sourceId) {
    const source = lib.sources.find(item => item.id === sourceId);
    const binding = pool.source_statuses.find(item => item.source_id === sourceId);
    if (!source || !binding || source.type === "object" || sourceId === lib.default_content_source_id) return "";
    const value = state(binding), locked = pending(pool, sourceId);
    const disabled = source.enabled === false || locked;
    const title = locked ? t("Finish or cancel the pending replacement in the CLI first")
      : source.enabled === false ? t("Source is disabled")
      : t("DEPRECATED stops this binding; SERVING resumes it. Data is kept.");
    const choices = ["SERVING", "DEPRECATED"];
    if (!choices.includes(value)) choices.unshift(value);
    return `<select class="serving-state-select ${color(value)}" data-serving-library="${esc(lib.name)}"
      data-serving-pool="${esc(pool.id)}" data-serving-source="${esc(sourceId)}" data-serving-state="${esc(value)}"
      aria-label="${esc(t("Serving state of {source} in {pool}", {source: source.name || sourceId, pool: pool.name || pool.id}))}"
      title="${esc(title)}" ${disabled ? "disabled" : ""}>
      ${choices.map(item => `<option value="${esc(item)}" ${item === value ? "selected" : ""}
        ${!["SERVING", "DEPRECATED"].includes(item) ? "disabled" : ""}>${esc(item)}</option>`).join("")}</select>
      ${effective(source, binding) !== value ? `<span class="chip">${esc(effective(source, binding))}</span>` : ""}`;
  }

  function sourceBindings(lib, sourceId) {
    return bindings(lib, sourceId).map(({pool, binding}) => `<div class="source-binding">
      <span class="binding-pool">${esc(pool.name || pool.id)}</span>${control(lib, pool, sourceId)}
      ${typeof sourceStatusChip === "function" ? sourceStatusChip(binding) : ""}</div>`).join("")
      || '<span class="hint">—</span>';
  }

  return {state, effective, bindings, pending, polling, chip, control, sourceBindings};
})();