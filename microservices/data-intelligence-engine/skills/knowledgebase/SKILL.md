---
name: knowledgebase
description: "Generic RAG query skill - Retrieve any information from the local knowledge base and generate structured reports, summaries, or Q&A responses. Use for: product comparisons, technical analysis, documentation generation, competitive analysis, benchmark reports, specification queries, or any knowledge base retrieval task."
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

Located at `<SKILL_DIR>/data_intelligence_engine`, this shell script calls the Data Intelligence Engine retrieval API (`POST /v1/retrieve`) directly with `curl`. It does not require Python or a virtual environment. If `jq` is installed, the output is a numbered list of chunks; otherwise it is the raw JSON response, where the final results are in `chunks`.

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
```

Options:
- `--top-k N`: chunks retrieved per source, 1-100 (default 5); raise it when the answer needs more context
- `--library NAME`: asset library to search, by name or ID (default: the deployment's configured library, or one discovered automatically, see below)
- `--pool ID`: asset pool to search, repeatable. Must be the pool **ID**, not its display name (default: every pool in the library)
- `--media LIST`: search only these modalities, comma-separated `document`, `image`, `video`, `audio` (default: every modality). Use `--media document` to get text passages only
- `--rerank N`: rerank the retrieved candidates and keep the best N; combine with a larger `--top-k` for better precision

#### Choosing the library, pool and media

- **Pass no options by default.** The deployment may already configure the library, pool, media and reranking; an option you pass overrides that configuration for one call only.
- If no library is configured and you pass no `--library`, the script picks one library on the engine by itself (one holding the `--pool` IDs you passed, or else one with a pool that has assets) and reports it on stderr, for example `Note: searching library 'alpha'; also available: beta. Pass --library NAME to choose.`
- Pass `--library` / `--pool` only when the user names a library or pool, or when that note shows the wrong library was searched. Never invent library or pool names; if you do not know which one the user means, show the user the libraries listed in the note and ask.
- The engine cannot be told to search one particular source (embedding index); sources are selected only through the pools that hold them. If the user asks for one source, explain this instead of guessing a pool.

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
