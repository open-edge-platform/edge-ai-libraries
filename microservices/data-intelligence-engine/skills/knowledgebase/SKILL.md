---
name: knowledgebase
description: "Generic RAG query skill - Retrieve any information from the local knowledge base and generate structured reports, summaries, or Q&A responses. Use for: product comparisons, technical analysis, documentation generation, competitive analysis, benchmark reports, specification queries, or any knowledge base retrieval task. Also use for VISUAL questions about knowledge base photos, PDF figures, and video scenes: colors, clothing, actions, and what an image shows — add --include-media and Read the returned image files."
trigger: "When user needs to retrieve any information for any purpose."
user-invocable: true
allow-model-invocation: true
priority: high
---

# Knowledge Base - Generic Information Retrieval & Report Generation

Use this skill when the user wants to retrieve information from the local knowledge base and generate structured outputs (reports, summaries, comparisons, documentation).

The knowledge base is served by the Data Intelligence Engine. It returns the most relevant source text chunks for a question, **not a generated answer**. You must write the answer yourself from the returned chunks.

## 📋 QUICK START - Do This Immediately

When user asks a question, **execute the curl-based data_intelligence_engine wrapper via Bash**:

```javascript
Bash({
  command: '<SKILL_DIR>/data_intelligence_engine "user\'s question here"',
  description: "Query knowledge base"
})
```

Then answer the user based on the returned chunks. That's it!

**Example:** User asks "What is Intel Core Ultra 358H?"

**Your immediate action:**
```javascript
Bash({
  command: '<SKILL_DIR>/data_intelligence_engine "What is Intel Core Ultra 358H?"',
  description: "Query KB for Intel Core Ultra 358H"
})
// Wait for output, then answer the user from the returned chunks
```

## 🚨 CRITICAL EXECUTION REQUIREMENT 🚨

**YOU MUST EXECUTE COMMANDS USING THE BASH TOOL - DO NOT JUST DESCRIBE THEM!**

To query the knowledge base, you MUST:
1. Use the **Bash tool** to execute `<SKILL_DIR>/data_intelligence_engine "your question"`
2. Wait for the command to complete and get the output
3. Read the returned chunks and write the answer, report, or summary from them

Example Bash tool call:
```
Bash(
  command: '<SKILL_DIR>/data_intelligence_engine "What is Intel Core Ultra 358H?"',
  description: "Query knowledge base for Intel Core Ultra 358H specifications"
)
```

## Core Principles

⚠️ **ALWAYS use Bash tool to execute `<SKILL_DIR>/data_intelligence_engine` commands** ⚠️
⚠️ **Primary information source is `<SKILL_DIR>/data_intelligence_engine` output via Bash tool** ⚠️
⚠️ **Wait for Bash execution to complete before proceeding** ⚠️
⚠️ **Base the answer only on the returned chunks; if they do not contain the answer, say so instead of guessing** ⚠️

The main session can handle simple queries directly. For complex tasks, launch sub-agents.
For broad tasks (reports, comparisons), run several focused queries, one per product or topic, instead of one long question.

## Core Tool

### curl-based data_intelligence_engine Wrapper (Execute via Bash Tool)

Located at `<SKILL_DIR>/data_intelligence_engine`, this shell script calls the Data Intelligence Engine retrieval API (`POST /v1/retrieve`) directly with `curl`. It does not require Python or a virtual environment, except for `--include-media` which needs `python3` to decode media files. If `jq` is installed, the output is a numbered list of chunks; otherwise it is the raw JSON response, where the final results are in `chunks`.

**CRITICAL: You MUST use the Bash tool to execute these commands!**

#### Usage via Bash Tool

```javascript
// Simple query (retrieves the top 5 chunks)
Bash({
  command: '<SKILL_DIR>/data_intelligence_engine "your question here"',
  description: "Query knowledge base"
})
```

Optional query settings:

```bash
<SKILL_DIR>/data_intelligence_engine "your question" --top-k 10
<SKILL_DIR>/data_intelligence_engine "your question" --library enterprise-kb --pool documents
<SKILL_DIR>/data_intelligence_engine "your question" --media document --top-k 10 --rerank 5
<SKILL_DIR>/data_intelligence_engine "your question" --include-media
<SKILL_DIR>/data_intelligence_engine --list-pools
```

Options:
- `--top-k N`: chunks retrieved per source, 1-100 (default 5); raise it when the answer needs more context
- `--library NAME`: asset library to search, by name or ID (default: the deployment's configured library, or one discovered automatically, see below)
- `--pool ID`: asset pool to search, repeatable. Must be the pool **ID**, not its display name (default: every pool in the library)
- `--media LIST`: search only these modalities, comma-separated `document`, `image`, `video`, `audio` (default: every modality). Use `--media document` to get text passages only
- `--rerank N`: rerank the retrieved candidates and keep the best N; combine with a larger `--top-k` for better precision. **With visual candidates (`--include-media` or media hits), every candidate is decoded and scored by the VL reranker, so latency grows with `--top-k`, not just N: keep `--top-k` small (about 5) and N small (2-5). Large `--top-k` with rerank can take minutes**
- `--include-media`: also retrieve **visual evidence** for the hits (`include_media_data:true` on the engine): decoded image/video-frame files plus a manifest. Use for questions about what an image, document figure or video scene shows. See [Visual questions](#visual-questions---include-media)
- `--list-pools`: list the library's asset pools and indexed asset types, then exit. Run this first when you are unsure which pool to search

#### Choosing the library, pool and media

- **Pass no options by default.** The deployment may already configure the library, pool, media and reranking; an option you pass overrides that configuration for one call only.
- If no library is configured and you pass no `--library`, the script picks one library on the engine by itself (one holding the `--pool` IDs you passed, or else one with a pool that has assets) and reports it on stderr, for example `Note: searching library 'alpha'; also available: beta. Pass --library NAME to choose.`
- Pass `--library` / `--pool` only when the user names a library or pool, or when that note shows the wrong library was searched. Never invent library or pool names; if you do not know which one the user means, show the user the libraries listed in the note and ask.
- The engine cannot be told to search one particular source (embedding index); sources are selected only through the pools that hold them. If the user asks for one source, explain this instead of guessing a pool.
- **Document figures are not in image pools.** Standalone photos live in image-type pools, but figures extracted from PDFs/documents (`doc_image`) live in document/mixed pools. Do not narrow to an image pool just because the question mentions pictures.
- **Query with content words, never filenames.** Retrieval is semantic: ask with what the content is *about* (e.g. "personalized book recommendations", "child reading"), not the file name. Figure chunks often have little or no text, so a filename query cannot match them. If a query returns nothing useful, rephrase with related content words.
- When the pool layout is unknown or the results have the wrong content type, run `--list-pools` to see every pool ID and which asset types (pdf, image, video, audio) the library indexes.
- **Keep visual lookup queries short content-word phrases**, not the whole user question or a long sentence mixing filenames and attributes; long queries tend to hit the wrong pages.
- **Bound the search effort.** After about three focused retrieval attempts, stop rephrasing and answer with the evidence you already have, clearly stating what could not be found or confirmed. If more evidence is needed, narrow the query or pools rather than enlarging `--top-k`, especially with `--include-media` or `--rerank`.

#### Visual questions - `--include-media`

For a question about visual content — what is in an image, a document figure, or a video scene (colors, clothing, actions, what a figure shows) — add `--include-media`:

```bash
<SKILL_DIR>/data_intelligence_engine "your question" --include-media --top-k 5
```

The engine then attaches visual evidence to the retrieved chunks. The wrapper decodes it into image files under a temporary `openclaw-media-*` directory and prints a `## Media evidence` manifest instead of any base64 data. **Never print or paste data URIs into the conversation.** `--include-media` requires `python3`; without it the command fails instead of dumping raw JSON.

The manifest gives each hit its `status`, `reason`, `delivery`, and one line per decoded file with an evidence ID (`E{rank}` for images, `E{rank}F{frame}` for video frames) and, for frames, `time=mm:ss.mmm`.

Evidence availability:

- `status=included` and `delivery=ready/partial` mean a file was written. A retrieved chunk, path, or delivery status does not mean the model saw its pixels.
- Only a successful Read that returns an **image content block** makes that exact `E...` item observed. A failed or text-only Read does not.
- `skipped`, `failed`, `delivery=failed/unavailable`, and unread files supply no visual evidence: state that their visual content is unavailable and only their text was supplied. `delivery=shared` refers to an earlier image; use it only if that image was actually Read. Text in the same result can still support text claims.
- `reason=media_budget` means the engine's media budget did not cover that item; report the status, do not invent a cause.

Source attribution:

- Bind each visual observation to its exact evidence ID and source. For video, also cite the manifest's `time=mm:ss.mmm` for that frame.
- For a video question, choose the most relevant video result first. Read that source's frames and understand them **as one group** before deciding whether another video is needed. Keep different sources separate; do not describe every returned video by default.
- Sampled frames show only those moments. Do not turn gaps between frames into observed events, a complete recipe, or a full process.

Grounded answer:

- Answer what the user asked using retrieved text and observed images. Distinguish directly visible content, uncertain interpretation, and details that cannot be determined.
- A specific identity or fine detail may be stated when the evidence clearly supports it; otherwise express uncertainty. Do not promote a plausible interpretation into a verified fact. Do not infer a dish name, location, brand, currency, or language from appearance alone; quote on-screen text exactly as legible.
- **User-facing citations are natural-language only: the source file name, plus the frame time for video or the page for documents (e.g. "video7013.mp4, around 00:10"). Never show internal evidence IDs (`E2`, `E2F2`, ...) in the final answer — they are internal bookkeeping for your own verification, meaningless to the user.** Avoid unrelated detail.

Before sending, check that each visual claim refers to an actually Read image and that its source and time match (use the evidence IDs internally for this check). Remove or qualify claims whose evidence is missing or uncertain. Temporary media files can be deleted after the answer is complete.

Example output (with `jq`):

```text
[1] score=0.809 source=intel_products.txt
Intel Core Ultra X7 358H is a mobile processor designed for high-performance laptops. ...

[2] score=0.412 source=product_brief.pdf page=3
...

[3] score=0.386 source=product_brief.pdf page=4 kind=image
media: http://localhost:16022/v1/blob?library=enterprise-kb&source_id=...&media_key=...
context: text printed around the figure on the page ...
```

Each chunk shows its rank, relevance score, source file and, when known, its page. A text chunk is followed by its passage. A figure, image, video or audio chunk (`kind=...`) has no passage: it shows a `media:` URL that downloads the original media, plus the caption or surrounding page text as `context:`. Use `context:` only as a hint about what the media shows. Cite the source files (and pages) when presenting results. If the output says no matching content was found, tell the user the knowledge base has no information on the question.

If the command fails, it prints the engine's error and exits non-zero: `Asset library '...' not found` means the library name is wrong, `asset pool not found` means the pool ID is wrong, `no asset library ... has ...` means automatic discovery found no library with indexed assets (or with the given pool), `search unavailable for: ...` means the library has no searchable source for that modality, and a connection error means the engine is not reachable. Report the error to the user instead of guessing an answer.

The defaults come from environment variables set by whoever deployed the agent (`KB_ENGINE_URL`, `KB_LIBRARY`, `KB_POOL`, `KB_TARGET_MEDIA`, `KB_RERANK_TOP_N`, `KB_CONNECT_TIMEOUT`). Do not set them yourself; use the command-line options above to change a single call. Run `<SKILL_DIR>/data_intelligence_engine --help` for the full reference.

> [!IMPORTANT]
>
> - `curl` must be available in `PATH`
> - ALWAYS use Bash tool to execute commands
> - Never skip execution - always run the command!
