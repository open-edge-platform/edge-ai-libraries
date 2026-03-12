# Release Notes: Chat Q&A

## Version 2.1.0

**April 1, 2026**

**New**

- Integrated Model Download functionality with the sample application for Helm and Docker deployments

**Known Issues**

- The upload button is temporarily disabled during chat response generation to prevent delays. File or link uploads trigger embedding generation, which runs on the same OVMS server as the LLM, potentially slowing response streaming if both run together.
- Chat data is stored in localStorage for session continuity. After container restarts, old chats may reappear — clear your browser’s localStorage to start fresh.
- Limited validation done on EMT-S due to EMT-S issues. It is not recommended to use Chat QnA modular on EMT-S until full validation is completed.
- DeepSeek/Phi Models are observed, at times, to continue generating responses in an endless loop. Close the browser and restart in such cases.

## Previous Releases

- [Release Notes 2025](./release-notes/release-notes-2025.md)

<!--hide_directive
:::{toctree}
:hidden:

Release Notes 2025 <./release-notes/release-notes-2025.md>

:::
hide_directive-->