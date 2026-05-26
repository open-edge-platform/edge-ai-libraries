# Vector Retriever

`vector-retriever` provides OpenAI-style semantic retrieval over multiple vector backends with a unified query contract, backend pushdown where possible, and deterministic fallback filtering where required.

The microservice supports batch queries, rich metadata filtering through the `where` grammar, legacy compatibility aliases (`tags`, `time_filter`, `filters`), per-query `top_k`, image query input (base64 or URL as an alternative to text), and optional explain output (`explain_filters`) for pushdown diagnostics.

## Documentation

- **Overview**
  - [Overview](docs/user-guide/Overview.md): High-level introduction to service capabilities and usage model.
  - [Architecture](docs/user-guide/overview-architecture.md): Request flow, backend model, and pushdown/fallback execution design.

- **Getting Started**
  - [Get Started](docs/user-guide/get-started.md): Setup, backend startup modes, and first query walkthrough.
  - [System Requirements](docs/user-guide/system-requirements.md): Runtime and dependency requirements.

- **Usage**
  - [API Reference](docs/user-guide/api-reference.md): Endpoint contracts, request/response shapes, and examples.
  - [Filter Grammar](docs/user-guide/filter-grammar.md): Primary `where` grammar, operators, and safety limits.
  - [Add New Retriever Backend](docs/user-guide/add-new-retriever-backend.md): Backend integration contract and implementation guide.
  - [Functional Notebook Walkthroughs](tests/functional/notebooks/README.md): End-to-end backend-specific validation notebooks.

- **Deployment**
  - [How to Build from Source](docs/user-guide/how-to-build-from-source.md): Build and packaging instructions.

- **API Docs**
  - [OpenAPI Specification](docs/user-guide/api-docs/openapi.yaml): Machine-readable API spec.

- **Release Notes**
  - [Release Notes](docs/user-guide/release-notes.md): Version updates, behavior changes, and fixes.

See [Get Started](docs/user-guide/get-started.md) for detailed setup instructions.
