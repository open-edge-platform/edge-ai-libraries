# Uninstall

```bash
./uninstall.sh                  # prompts, keeps exported models
./uninstall.sh --yes --delete-models --agent openclaw
./uninstall.sh --yes --keep-agent-data --agent hermes   # keep ~/.hermes (sessions, memories, skills)
```

Removes registered sandboxes, the OpenVINO Model Server container, the
installed agent (its actual package — e.g. `npm uninstall -g openclaw`,
`uv tool uninstall deepagents-code`, or Hermes's own data directory
`~/.hermes` — not just its CLI shim), and the `~/.intel-agent` state
directory. Docker, Node.js/nvm, and the Intel compute runtime are left in
place. Pass `--keep-agent-data` to preserve Hermes's or dcode's
config/sessions/memories/skills instead of deleting them.
