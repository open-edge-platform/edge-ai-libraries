// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
//
// App Shell header — matches the reference app's header
// (visual-pipeline-and-platform-evaluation-tool/ui/src/components/Layout.tsx):
// fixed 60px bar, sidebar trigger + divider + page title on the left, optional
// live-status pill and a light/dark theme toggle on the right. Rename the page
// title per-route; keep the status-dot color mapping as-is so every app's
// "connected/degraded/offline" language stays consistent.

const STATUS_STYLE = {
  connected: { dot: 'bg-[var(--success)]', label: 'Connected' },
  degraded: { dot: 'bg-[color-mix(in_oklch,var(--destructive)_60%,var(--success)_40%)]', label: 'Degraded' },
  offline: { dot: 'bg-[var(--destructive)]', label: 'Offline' },
};

export default function Header({ pageTitle = 'Page Title', status, onToggleTheme, isDark }) {
  const s = status ? (STATUS_STYLE[status] ?? STATUS_STYLE.connected) : null;

  return (
    <header className="flex h-[60px] shrink-0 items-center gap-2 justify-between border-b bg-background px-4">
      <div className="flex items-center gap-2">
        <span className="font-semibold text-lg">{pageTitle}</span>
      </div>

      <div className="flex items-center gap-3 px-4">
        {s && (
          <span className="flex items-center gap-2 rounded-full bg-muted px-3 py-1">
            <span className={`w-[7px] h-[7px] rounded-full ${s.dot}`} />
            <span className="text-xs font-medium text-muted-foreground">{s.label}</span>
          </span>
        )}
        <button
          type="button"
          onClick={onToggleTheme}
          aria-label="Toggle theme"
          className="inline-flex items-center justify-center size-9 rounded-md hover:bg-accent"
        >
          {isDark ? '\u2600' : '\u263E'}
        </button>
      </div>
    </header>
  );
}

