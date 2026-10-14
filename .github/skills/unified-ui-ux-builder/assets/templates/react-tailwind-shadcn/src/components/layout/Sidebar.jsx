// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
//
// App Shell sidebar — vertical nav list. Use for multi-page apps (see
// references/layout-patterns.md, pattern 1). Omit entirely for single-page
// Dashboard Grid or Split Panel apps.

export default function Sidebar({ items = [], activeId, onSelect }) {
  return (
    <nav className="w-56 shrink-0 border-r border-border bg-card p-3 flex flex-col gap-1">
      {items.map(({ id, label, icon: Icon }) => (
        <button
          key={id}
          onClick={() => onSelect?.(id)}
          className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-left transition-colors ${
            id === activeId
              ? 'bg-primary/10 text-primary font-medium'
              : 'text-muted-foreground hover:bg-muted hover:text-foreground'
          }`}
        >
          {Icon ? <Icon size={16} strokeWidth={1.8} /> : null}
          {label}
        </button>
      ))}
    </nav>
  );
}
