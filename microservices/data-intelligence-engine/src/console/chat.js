// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
// Retrieval-augmented chat, entirely in the browser. Each question is retrieved
// and reranked with the Retrieval & reranking form (runRetrieval, console.js);
// the results go as numbered context to an OpenAI-compatible chat completion
// endpoint, called straight from here. The engine has no chat logic.
const Chat = (() => {
const SYSTEM_PROMPT =
  "Answer the user's question using the retrieval results provided with it. " +
  "If they do not contain the answer, say so. Cite the results you use by number, like [1].";
const MAX_CHUNK_CHARS = 2000;   // per result, so a long chunk cannot crowd out the rest
const HISTORY_TURNS = 3;        // earlier question/answer pairs sent for follow-ups
const THINKING = () => t("Thinking…");
const STORE = { endpoint: "die.chat.endpoint", model: "die.chat.model", key: "die.chat.key" };

// [{role: "user"|"assistant", content, sources?, scope?, error?, pending?}]
let MESSAGES = [];
let controller = null;          // AbortController of the answer being streamed

const endpointUrl = (path) => {
  const base = $("chat-endpoint").value.trim().replace(/\/+$/, "").replace(/\/chat\/completions$/, "");
  if (!/^https?:\/\//.test(base)) throw new Error(t("Enter the chat endpoint, e.g. http://localhost:8000/v1"));
  return base + path;
};
const headers = () => {
  const h = { "Content-Type": "application/json" };
  const key = $("chat-key").value.trim();
  if (key) h.Authorization = `Bearer ${key}`;
  return h;
};
// A browser reports an unreachable or CORS-refusing endpoint as a bare TypeError.
// A browser reports an unreachable endpoint and one refusing this page's origin
// (CORS) the same way; the second is the usual cause with a running server.
const networkError = (err) => err && err.name === "TypeError"
  ? new Error(t("Could not reach the chat endpoint. If it is running, it must allow this console's origin {origin} -- for vLLM, start it with --allowed-origins '[\"{origin}\"]'.", { origin: location.origin }))
  : err;
async function failure(res) {
  const text = await res.text().catch(() => "");
  let detail = text;
  try { const data = JSON.parse(text); detail = (data.error && (data.error.message || data.error)) || data.detail || data.message || text; } catch { /* plain text */ }
  return new Error(`${t("Chat endpoint")}: ${res.status} ${res.statusText}${detail ? " · " + String(detail).slice(0, 300) : ""}`);
}

// ---- settings ---------------------------------------------------------------------
for (const [id, key, storage] of [["chat-endpoint", STORE.endpoint, localStorage], ["chat-model", STORE.model, localStorage], ["chat-key", STORE.key, sessionStorage]]) {
  $(id).value = storage.getItem(key) || "";
  $(id).addEventListener("change", () => storage.setItem(key, $(id).value.trim()));
}
$("chat-models-load").addEventListener("click", (e) => busy(e.target, "…", async () => {
  let res;
  try { res = await fetch(endpointUrl("/models"), { headers: headers() }); } catch (err) { throw networkError(err); }
  if (!res.ok) throw await failure(res);
  const ids = ((await res.json()).data || []).map(m => m.id).filter(Boolean);
  $("chat-models").innerHTML = ids.map(id => `<option value="${esc(id)}"></option>`).join("");
  if (ids.length && !$("chat-model").value) { $("chat-model").value = ids[0]; $("chat-model").dispatchEvent(new Event("change")); }
  toast(ids.length ? t("{n} model(s): {ids}", { n: ids.length, ids: ids.slice(0, 3).join(", ") }) : t("The endpoint lists no models"));
}));

// ---- the prompt -------------------------------------------------------------------
function sourceLabel(chunk) {
  const m = chunk.metadata || {};
  return [m.file_name || m.library || chunk.id, m.page != null ? `p.${m.page}` : ""].filter(Boolean).join(", ");
}
function contextBlock(chunks) {
  if (!chunks.length) return t("(No retrieval results.)");
  return chunks.map((c, i) => {
    const text = (c.text || "").trim();
    return `[${i + 1}] (${sourceLabel(c)})\n${text.length > MAX_CHUNK_CHARS ? text.slice(0, MAX_CHUNK_CHARS) + "…" : text}`;
  }).join("\n\n");
}
// Earlier turns go as plain question/answer pairs (answered ones only, so roles
// keep alternating); only this question carries retrieval context.
function chatMessages(question, chunks) {
  const done = MESSAGES.slice(0, -2);               // all but this question and its answer
  const earlier = [];
  for (let i = 0; i + 1 < done.length; i++) {
    const [q, a] = [done[i], done[i + 1]];
    if (q.role === "user" && a.role === "assistant" && !a.error && stripThinking(a.content).trim())
      earlier.push({ role: "user", content: q.content }, { role: "assistant", content: stripThinking(a.content) });
  }
  return [
    { role: "system", content: SYSTEM_PROMPT },
    ...earlier.slice(-HISTORY_TURNS * 2),
    { role: "user", content: `Retrieval results:\n${contextBlock(chunks)}\n\nQuestion: ${question}` },
  ];
}
// Reasoning models may put their thinking inline; it is not part of the answer.
const stripThinking = (text) => String(text || "").replace(/<think>[\s\S]*?(<\/think>|$)/g, "").trimStart();

// ---- asking -----------------------------------------------------------------------
async function streamAnswer(messages, answer) {
  let res;
  try {
    res = await fetch(endpointUrl("/chat/completions"), {
      method: "POST", headers: headers(), signal: controller.signal,
      body: JSON.stringify({ model: $("chat-model").value.trim(), messages, stream: true }),
    });
  } catch (err) { throw err.name === "AbortError" ? err : networkError(err); }
  if (!res.ok) throw await failure(res);
  // A server that ignores `stream` answers with one JSON body.
  if (!(res.headers.get("content-type") || "").includes("text/event-stream")) {
    const data = await res.json();
    answer.content = (data.choices && data.choices[0] && data.choices[0].message && data.choices[0].message.content) || "";
    render();
    return;
  }
  const reader = res.body.getReader(), decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n"); buffer = lines.pop();
    for (const line of lines) {
      const data = line.trim().replace(/^data:\s*/, "");
      if (!line.trim().startsWith("data:") || data === "[DONE]") continue;
      let delta;
      try { delta = JSON.parse(data).choices?.[0]?.delta || {}; } catch { continue; }   // keep-alive or partial line
      if (delta.content) {
        answer.content += delta.content; answer.pending = null; render();
      } else if ((delta.reasoning || delta.reasoning_content) && !answer.content && answer.pending !== THINKING()) {
        // A reasoning model thinks first (not shown); say so instead of looking stuck.
        answer.pending = THINKING(); render();
      }
    }
  }
}
async function send() {
  if (controller) { controller.abort(); return; }   // the button is "Stop" while answering
  const question = $("chat-input").value.trim();
  if (!question) return toast(t("Enter a question"), true);
  try { endpointUrl(""); } catch (err) { return toast(err.message, true); }
  if (!$("chat-model").value.trim()) return toast(t("Enter the chat model ID"), true);
  $("chat-input").value = "";
  $("q-text").value = question;                     // the results panel shows this question's retrieval
  MESSAGES.push({ role: "user", content: question });
  const answer = { role: "assistant", content: "", pending: t("Retrieving…") };
  MESSAGES.push(answer);
  controller = new AbortController();
  render();
  try {
    const { r, scope } = await runRetrieval(question);
    answer.sources = r.chunks.map(c => ({ label: sourceLabel(c), text: (c.text || "").slice(0, 300) }));
    answer.scope = scope;
    answer.pending = t("Answering…");
    render();
    await streamAnswer(chatMessages(question, r.chunks), answer);
    if (!stripThinking(answer.content).trim()) answer.error = t("The chat model returned an empty answer.");
  } catch (err) {
    answer.error = err.name === "AbortError" ? t("Stopped.") : err.message;
  } finally {
    answer.pending = null; controller = null;
    render();
  }
}

// ---- view -------------------------------------------------------------------------
// Escaped text, with [n] turned into citation chips that show their source.
function answerHtml(message, latest) {
  return esc(stripThinking(message.content)).replace(/\[(\d+)\]/g, (whole, n) => {
    const source = (message.sources || [])[n - 1];
    if (!source) return whole;
    return `<span class="chip cite" ${latest ? `data-cite="${n}"` : ""} title="${esc(source.label + "\n" + source.text)}">${n}</span>`;
  });
}
function render() {
  const log = $("chat-log");
  const latestAnswer = MESSAGES.map(m => m.role).lastIndexOf("assistant");
  log.innerHTML = MESSAGES.length ? MESSAGES.map((m, i) => {
    if (m.role === "user") return `<div class="msg user">${esc(m.content)}</div>`;
    const sources = m.sources ? `<div class="hint">${esc(t("Context: {n} result(s) · {scope}", { n: m.sources.length, scope: m.scope || "" }))}</div>` : "";
    const body = m.content ? `<div class="txt">${answerHtml(m, i === latestAnswer)}</div>` : "";
    const state = m.pending ? `<div class="hint">${esc(m.pending)}</div>` : "";
    const error = m.error ? `<div class="err">${esc(m.error)}</div>` : "";
    return `<div class="msg assistant">${body}${state}${error}${sources}</div>`;
  }).join("") : "";
  log.scrollTop = log.scrollHeight;
  const btn = $("chat-send");
  btn.textContent = t(controller ? "Stop" : "Send");
  btn.classList.toggle("danger", !!controller);
}
// A citation in the latest answer points at that result in the Results panel.
$("chat-log").addEventListener("click", e => {
  const cite = e.target.closest("[data-cite]"); if (!cite) return;
  const result = $("q-results").querySelectorAll(".result")[+cite.dataset.cite - 1];
  if (!result) return;
  result.scrollIntoView({ behavior: "smooth", block: "nearest" });
  result.classList.add("flash"); setTimeout(() => result.classList.remove("flash"), 1200);
});
$("chat-send").addEventListener("click", send);
$("chat-input").addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); }
});
$("chat-clear").addEventListener("click", () => { if (controller) controller.abort(); MESSAGES = []; render(); });
render();

return { render };
})();
