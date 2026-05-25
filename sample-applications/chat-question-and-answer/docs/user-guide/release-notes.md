# Release Notes: Chat Q&A


## Version 2026.1.0-rc1

**May 14, 2026**

**New**
    - EMF deployment package support has been removed.
    - Security fixes.

**Known Issues**

- The upload button is temporarily disabled during chat response generation to prevent delays. File or link uploads trigger embedding generation, which runs on the same OVMS server as the LLM, potentially slowing response streaming if both run together.
- Chat data is stored in localStorage for session continuity. After container restarts, old chats may reappear — clear your browser’s localStorage to start fresh.
- Limited validation done on EMT-S due to EMT-S issues. It is not recommended to use Chat Q&A modular on EMT-S until full validation is completed.
- DeepSeek/Phi Models are observed, at times, to continue generating responses in an endless loop. Close the browser and restart in such cases.
- When multiple applications use the model download service concurrently, downloads may take longer than usual. In such cases, retry with increased `SLEEP_SECS` in the `download_ovms_model` function in `setup.sh`.




## Previous Releases

## Version 2.1.0

**April 1, 2026**

**New**

- Integrated Model Download functionality with the sample application for Helm and Docker deployments

[Release Notes 2025](./release-notes/release-notes-2025.md)

<!--hide_directive
:::{toctree}
:hidden:

Release Notes 2025 <./release-notes/release-notes-2025.md>

:::
hide_directive-->