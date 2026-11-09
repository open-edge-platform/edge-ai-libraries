// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import type {
  ChatMessage,
  CompletionMessage,
  CompletionResponse,
} from "./Type";
import type { Chunk } from "../../api/console/type";

export const stripThinking = (text: string) =>
  text.replace(/<think>[\s\S]*?(<\/think>|$)/g, "").trimStart();
export const sourceLabel = (chunk: Chunk) =>
  [
    chunk.metadata.file_name || chunk.metadata.library || chunk.id,
    chunk.metadata.page != null ? `p.${chunk.metadata.page}` : "",
  ]
    .filter(Boolean)
    .join(", ");

export const buildMessages = (
  question: string,
  chunks: Chunk[],
  history: ChatMessage[],
): CompletionMessage[] => {
  const completed: CompletionMessage[] = [];
  for (let index = 0; index + 1 < history.length; index += 2) {
    const user = history[index];
    const answer = history[index + 1];
    if (
      user.role === "user" &&
      answer.role === "assistant" &&
      !answer.error &&
      stripThinking(answer.content).trim()
    )
      completed.push(
        { role: "user", content: user.content },
        { role: "assistant", content: stripThinking(answer.content) },
      );
  }
  const context = chunks
    .map(
      (chunk, index) =>
        `[${index + 1}] (${sourceLabel(chunk)})\n${chunk.text.trim().slice(0, 2000)}`,
    )
    .join("\n\n");
  return [
    {
      role: "system",
      content:
        "Answer the user's question using the retrieval results provided with it. If they do not contain the answer, say so. Cite the results you use by number, like [1].",
    },
    ...completed.slice(-6),
    {
      role: "user",
      content: `Retrieval results:\n${context || "(No retrieval results.)"}\n\nQuestion: ${question}`,
    },
  ];
};

export const readCompletion = async (
  response: Response,
  onContent: (content: string) => void,
  onThinking: () => void,
) => {
  if (!response.ok)
    throw new Error(
      `${response.status} ${response.statusText}: ${(await response.text()).slice(0, 500)}`,
    );
  if (!response.headers.get("content-type")?.includes("text/event-stream")) {
    const data: CompletionResponse = await response.json();
    if (data.error) throw new Error(data.error.message);
    onContent(data.choices?.[0]?.message?.content || "");
    return;
  }
  if (!response.body)
    throw new Error("Chat endpoint returned no response body.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let eventData: string[] = [];
  let finished = false;
  const dispatch = () => {
    if (!eventData.length) return;
    const text = eventData.join("\n");
    eventData = [];
    if (text === "[DONE]") {
      finished = true;
      return;
    }
    const data: CompletionResponse = JSON.parse(text);
    if (data.error) throw new Error(data.error.message);
    const delta = data.choices?.[0]?.delta;
    if (delta?.content) onContent(delta.content);
    else if (delta?.reasoning || delta?.reasoning_content) onThinking();
  };
  const consume = (line: string) => {
    line = line.replace(/\r$/, "");
    if (line === "") dispatch();
    else if (line.startsWith("data:"))
      eventData.push(line.slice(5).replace(/^ /, ""));
  };
  try {
    while (!finished) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      let newline: number;
      while ((newline = buffer.indexOf("\n")) >= 0) {
        consume(buffer.slice(0, newline));
        buffer = buffer.slice(newline + 1);
        if (finished) break;
      }
      if (done) {
        if (buffer) consume(buffer);
        dispatch();
        break;
      }
    }
  } finally {
    await reader.cancel();
    reader.releaseLock();
  }
};
