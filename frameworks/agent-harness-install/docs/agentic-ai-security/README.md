<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

# Agentic AI Security

AI agents combine model-generated decisions with tools that can read data,
write files and interact with services. Securing an agent deployment therefore
requires controls across inputs, tool execution, data handling and network
access, not just the inference endpoint.

Agent Harness Install is starting with agent sandboxing. This documentation
will grow as additional security capabilities are implemented.

## Available security features

| Feature | Scope | Status |
|---|---|---|
| [Agent Sandboxing](agent-sandboxing.md) | Run OpenClaw or Hermes in an OpenShell sandbox with restricted filesystem and network access | Available; OpenShell 0.1.5 on Linux with Docker |

Start with the [Agent Sandboxing getting started guide](agent-sandboxing.md#getting-started)
to install an agent, connect it to inference and verify its sandbox.

## Future areas

Potential future areas include prompt protection and PII masking. They are not
implemented security features of this integration today, and no delivery
schedule is implied.

These controls address different risks. Sandboxing limits an agent's execution
environment; it does not establish that prompts are trustworthy, prevent every
prompt-injection attack, or automatically identify and mask sensitive data.
No single control makes an agent deployment secure.

## Related documentation

- [Agent Harness Install](../../README.md)
- [Known limitations](../user-guide/known-limitations.md)
- [Uninstall and data removal](../user-guide/uninstall.md)
