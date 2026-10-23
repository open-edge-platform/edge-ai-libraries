<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Video Summary Accuracy Analyzer

The Video Summary Accuracy Analyzer is an evaluation tool that measures the quality of a generated video summary by comparing it against a ground-truth reference summary. It provides a comprehensive set of metrics across four key dimensions:

- **Lexical Similarity**: Assesses word-level overlap and coverage between the generated summary and the reference summary.
- **Semantic Similarity**: Evaluates how well the generated summary preserves the meaning and context of the reference summary.
- **Factual Consistency**: Identifies alignment of key facts, entities, and events between the generated and reference summaries.
- **Temporal Coherence**: Measures the accuracy of event ordering and the overall narrative flow.

The analyzer is accessible through both a web-based dashboard and a REST API, enabling integration into automated evaluation workflows.

> This tool is designed solely for **summary evaluation**. It does not process video files, generate reference summaries, perform video summarization using VLMs or VSS
>

Users should first obtain the video content and corresponding summaries through their preferred annotation, labeling, or video-understanding pipeline. The analyzer can then be used to compare a generated summary against a reference summary and evaluate its quality across the supported metrics.

## Using the Capability

1. **Video with reference summary.** Have a video with refernce (ground-truth) summary against which generated summary will be evaluated.
2. **Generate a summary.** Run the same video through VLM or Video Search and Summarization (VSS) workflow and collect its generated summary. 
3. **Compare the summaries.** In Summary Evaluation tab, upload and submit a single Markdown file containing both the Reference and Generated summaries. Review the results for sentence-level comparisons, factual consistency, and temporal coherence.
4. **Inspect individual metrics if needed.** In Metrics tab, enter the reference text and generated text, then select any one metric (BERTScore, Semantic Similarity, ROUGE, or Factual Consistency) to review the results.

Example input file (`comparison.md`):

```markdown
## Reference
A person enters the room, places a bag on the table, and leaves.

## Generated
A person walks into a room, sets down a bag, and exits.
```

Use a human-reviewed reference that describes the video accurately. Keep the reference and generated summaries focused on the same video and task; metric scores support evaluation but do not replace reviewing the video and the summaries.

## Documentation

- [Get Started](./docs/user-guide/get-started.md): Configure, deploy, and use the dashboard and API with Docker Compose.
- [Build from Source](./docs/user-guide/build-from-source.md): Build the backend and UI container images.


## Components

- **Evaluation API:** FastAPI service for full-file evaluation and individual metrics.
- **Dashboard:** Gradio UI for uploading summary pairs and reviewing evaluation results.
- **Gateway:** NGINX routes dashboard and API requests through port `8101`.

## Links

- [Video Summary Accuracy Analyzer in Edge AI Libraries](https://github.com/open-edge-platform/edge-ai-libraries/tree/main/tools/video-summary-accuracy-analyzer)
- [Edge AI Libraries](https://github.com/open-edge-platform/edge-ai-libraries)
- [Issues](https://github.com/open-edge-platform/edge-ai-libraries/issues)
- [Pull Requests](https://github.com/open-edge-platform/edge-ai-libraries/pulls)
