<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

# Agentic AI Security

AI agents combine model-generated decisions with tools that can read data,
write files and interact with services. Securing an agent deployment therefore
requires controls across inputs, tool execution, data handling and network
access, not just the inference endpoint.

Agent Harness Installer starts with agent sandboxing. This documentation
will grow as additional security capabilities are implemented.

## Available security features

| Feature | Scope | Status |
| --- | --- | --- |
| [Agent Sandboxing](./agentic-ai-security/agent-sandboxing.md) | Run OpenClaw, Hermes or Deep Agents Code in an OpenShell sandbox with restricted filesystem and network access | Available; OpenShell 0.1.5 on Linux with Docker |

Start with the [Agent Sandboxing getting started guide](./agentic-ai-security/agent-sandboxing.md#getting-started)
to install an agent, connect it to inference and verify its sandbox.
Sandboxing is opt-in through runtime selection; host deployment remains the
default. The installer supplies initial sandbox policies and inference
configuration so users do not need to author a policy to get started.

## Future areas

Potential future areas include prompt protection and PII masking. They are not
implemented security features of this integration today, and no delivery
schedule is implied.

Sandboxing, prompt protection and PII masking address different security
concerns and are intended to complement one another.

## Related documentation

- [Agent Harness Installer](./index.md)
- [Known limitations](./known-limitations.md)
- [Uninstall and data removal](./get-started/uninstall.md)

<!--hide_directive
:::{toctree}
:hidden:

./agentic-ai-security/agent-sandboxing.md

:::
hide_directive-->
