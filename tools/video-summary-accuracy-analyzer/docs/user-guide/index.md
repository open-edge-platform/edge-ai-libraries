# Video Summary Accuracy Analyzer

<!--hide_directive
<div class="component_card_widget">
  <a class="icon_github" href="https://github.com/open-edge-platform/edge-ai-libraries/tree/main/tools/video-summary-accuracy-analyzer">
     GitHub
  </a>
  <a class="icon_document" href="https://github.com/open-edge-platform/edge-ai-libraries/blob/main/tools/video-summary-accuracy-analyzer/README.md">
     Readme
  </a>
</div>
hide_directive-->

The Video Summary Accuracy Analyzer is an evaluation tool that measures the quality of a generated
video summary by comparing it against a ground-truth reference summary. It is accessible through
both a web-based dashboard and a REST API, enabling integration into automated evaluation workflows.

> This tool is designed solely for **summary evaluation**. It does not process video files, generate
> reference summaries, or perform video summarization using VLMs, video summarization tools, or
> pipeline workflows.

## Key Metrics

- **Lexical Similarity**: Assesses word-level overlap and coverage between the generated summary
  and the reference summary.
- **Semantic Similarity**: Evaluates how well the generated summary preserves the meaning and
  context of the reference summary.
- **Factual Consistency**: Identifies alignment of key facts, entities, and events between the
  generated and reference summaries.
- **Temporal Coherence**: Measures the accuracy of event ordering and the overall narrative flow.

## Next Steps

- [Get Started](./get-started.md): Configure, deploy, and use the dashboard and API with Docker Compose.
- [Build from Source](./build-from-source.md): Build the backend and UI container images.

<!--hide_directive
:::{toctree}
:hidden:

./get-started.md
./build-from-source.md

:::
hide_directive-->
