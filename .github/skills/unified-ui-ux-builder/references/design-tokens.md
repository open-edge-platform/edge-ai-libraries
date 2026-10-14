# Design Tokens

Consolidated from **only** the three reference apps this skill is grounded in (see `SKILL.md`
"Survey of the repo"):

- **Stack A** — `edge-ai-libraries/tools/visual-pipeline-and-platform-evaluation-tool/ui`
  (React + Redux Toolkit + Tailwind v4 + Radix-primitive/shadcn-style components)
- **Stack B** — `edge-ai-suites/education-ai-suite/smart-classroom/ui`
  (React + Redux Toolkit + plain CSS, no UI kit)
- **Stack C** — `edge-ai-suites/metro-ai-suite/live-video-analysis/live-video-captioning`
  (vanilla JS, no build step)

Each stack has its **own** primary accent — all three sit in the same Intel-blue hue family but are
not the same hex value. Reuse the accent of whichever reference stack a new/extended app is based
on; do not blend them or invent a fourth blue.

> **Ask, don't assume:** these tokens are the *defaults* for each stack, not forced choices. Before
> finalizing a new app's palette, confirm with the user: (1) whether they want a secondary semantic
> accent beyond the shared status colors; (2) whether both light and dark themes are required, or
> just one (stack A defaults to light, stack C defaults to dark); (3) if extending an existing app
> that already has its own token values, keep those — don't silently replace them with a reference
> stack's values just because they're documented here.

## Stack A — React + Redux Toolkit + Tailwind v4 + Radix (shadcn-style)

Source: `ui/src/tokens/colors-base.css`, `ui/src/tokens/colors-semantic.css`, `ui/src/index.css`.
Colors are defined in OKLCH; hex equivalents are shown for reference.

**Base palette** (`colors-base.css`):

| Token | OKLCH | Hex |
|---|---|---|
| `--classic-blue` (primary, light theme) | `oklch(0.377 0.152 258.338)` | `#0054AE` |
| `--classic-blue-tint-1` | `oklch(0.625 0.158 247.996)` | `#0099EC` |
| `--classic-blue-hover` | `oklch(0.333 0.137 258.653)` | `#004A9D` |
| `--energy-blue` (primary, dark theme) | `oklch(0.807 0.126 232.661)` | `#00C7FD` |
| `--energy-blue-tint-1` | `oklch(0.867 0.096 233.398)` | `#6DDCFF` |
| `--carbon` (neutral gray) | `oklch(0.577 0 0)` | `#808080` |
| `--carbon-10` (border/accent tint) | `oklch(0.934 0.0001 263.28)` | `#E9E9E9` |
| `--carbon-tint-1` | `oklch(0.725 0 0)` | `#AEAEAE` |
| `--spark-light-gray-100` (card/surface) | `oklch(0.9694 0.0011 201.14)` | `#F4F5F5` |
| `--green` (success) | `oklch(0.548 0.186 142.495)` | `#008A00` |
| `--electric-coral` (destructive) | `oklch(0.5859 0.2057 13.88)` | `#DA2E56` |
| `--electric-moss` (success, dark theme) | `oklch(0.8078 0.1822 127.53)` | `#9FD541` |
| `--electric-geode` (optional 3rd accent) | `oklch(0.5794 0.2752 308.89)` | `#A923F1` |

**Semantic mapping** (`colors-semantic.css`) — light theme (`:root`):

```css
--radius: 0.625rem;
--background: var(--white);           --foreground: var(--black);
--card: var(--spark-light-gray-100);   --card-foreground: var(--black);
--primary: var(--classic-blue);        --primary-foreground: var(--white);
--secondary: var(--spark-light-gray-100);
--muted: var(--spark-light-gray-100);  --muted-foreground: var(--carbon);
--accent: var(--carbon-10);
--success: var(--green);               --destructive: var(--electric-coral);
--border: var(--carbon-10);            --input: var(--carbon-tint-1);  --ring: var(--carbon);
--sidebar: var(--spark-light-gray-100);
```

Dark theme (`.dark`) swaps `--primary` to `--energy-blue`, `--success` to `--electric-moss`,
`--background`/`--card` to dark grays (`--spark-dark-gray-50` `#242528` / `--spark-dark-gray-200`
`#3C3E42`) — see the full block in `assets/templates/react-tailwind-shadcn/src/index.css`.

**Status utilities** — `status-info` / `status-success` / `status-error` (no dedicated "warning"
token; reuse a palette color like `--electric-geode` if a new app genuinely needs a 4th state) are
built with `color-mix(in oklch, var(--status-color) 12%, var(--background))` for background,
`32%` for border, `72%` for foreground — reuse this exact `color-mix` pattern rather than
hand-picking tint percentages.

**Typography:** `--font-sans: "Montserrat", "Open Sans", ui-sans-serif, system-ui, sans-serif`,
`--font-heading: "Montserrat", ui-sans-serif, system-ui, sans-serif`. No custom font-size scale —
uses Tailwind's built-in `text-xs`…`text-lg` utilities directly.

**Radius:** `--radius: 0.625rem` (10px); derived `--radius-sm` (6px), `--radius-md` (8px),
`--radius-lg` (10px), `--radius-xl` (14px) via `calc(var(--radius) ± offset)`.

**Shadows:** no global shadow token — components use Tailwind's `shadow-xs` utility directly.

**Spacing:** Tailwind's built-in scale (`gap-2`/`gap-4`/`gap-6`, `p-4`/`px-6`/`py-2`), no custom
spacing tokens.

**Theming:** `next-themes`, `attribute="class"`, `defaultTheme="light"`; toggle button switches
`light ⇄ dark`; logo swaps per theme too.

## Stack B — React + Redux Toolkit + plain CSS (no UI kit)

Source: `smart-classroom/ui/src/index.css`.

```css
:root {
  --font-display: "IntelOne Display", "Inter", system-ui, sans-serif;
  --font-text: "IntelOne Text", "Inter", system-ui, sans-serif;
  --font-mono: "Roboto Mono", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;

  --color-dark: #2B2C30;      /* body/heading text */
  --color-light: #FFF;
  --color-gray-700: #6A6D75;  /* labels */
  --color-gray-900: #2B2C30;
  --color-theme: #0071c5;     /* primary accent */

  background-color: #f5f7fa; /* page background */

  --control-padding: 8px 12px;
  --control-radius: 4px;
  --control-font-size: 14px;
  --control-border-color: #ccc;
  --control-background: #f7f7f7;
  --control-focus-color: #007bff;
  --control-focus-ring: 0 0 0 2px rgba(0, 123, 255, 0.25);

  --z-index-header: 50;
  --z-index-toast: 1100;
  --z-index-video-stream: 1000;
  --z-index-modal: 9999;
}
```

There is no formal numbered gray ramp beyond `gray-700`/`gray-900` — other grays (panel background
`#f8f8f8`, border `#e6e7e8`, input `#f7f7f7`) are embedded directly in component CSS files, one per
component under `src/assets/css/`. Reuse these exact values for consistency when adding new
components in this stack rather than picking new ones.

**Status colors** (component-local, not root tokens — reuse these exact values):

| Semantic use | Value |
|---|---|
| Success | `#4caf50` (dot), background `#ecfdf3` |
| Warning | `#ff9800` / gold `#e6b800`, `#f0a202`; background `#fff8e6`, `#fef3c7` |
| Error | `#d9534f`, `#d32f2f`, `#dc2626`; dark text `#b71c1c`; background `#fdecea`, `#fee4e2` |
| Info | `#0071c5`, `#3498db`, `#1976d2`; background `#eff7fd`, `#eff8ff` |

**Typography sizes:** headings via `h1,h2,h3,h4 { font-family: var(--font-display); font-weight:
400; }`, `h2 { font-size: clamp(18px, 5vw, 24px); }`; labels `clamp(11px, 2.5vw, 12px)`; buttons
`font-size: 12px; font-weight: 500; border-radius: 4px; padding: 6px 16px;`. Common sizes in the
wild: 10–12px (metadata), 13–14px (body/controls), 16px (tab labels), 18px (subheadings), 24–28px
(screen headings).

**Spacing:** no formal scale; recurring literal values are `4px, 6px, 8px, 10px, 12px, 16px, 20px,
24px`.

**Radius:** no formal scale; recurring values `0` (flat tabs/inputs), `4px` (`--control-radius`,
default controls/buttons), `6px` (banners), `8px` (cards/containers), `9–12px` (modals), `50%`
(circular indicators), `999px` (pill badges).

**Shadows:** component-local, typical values `0 2px 8px rgba(0,0,0,0.1)`, `0 4px 12px
rgba(0,0,0,0.15)`, modal overlay `0 8px 32px rgba(0,0,0,0.2)`.

**i18n:** `i18next` + `react-i18next`, `src/i18n/{en,zh}.json` — only add this if the new app
genuinely needs multi-language (ask the user).

## Stack C — Vanilla JS, no build step

Source: `live-video-captioning/app/ui/css/styles.css`.

Dark is the **default** theme (`:root`); light is an override via `[data-theme="light"]` — note
this is the opposite convention from stacks A/B, where light is default.

```css
:root {
    --bg: #050814;
    --bg-gradient: radial-gradient(circle at 20% -10%, #12225b 0%, #050814 55%);
    --panel: #0d152c;
    --panel-strong: #111c38;
    --accent: #1a73e8;       /* primary */
    --accent-strong: #0f5cc8;
    --text: #f5f7fb;
    --muted: #8ca0c2;
    --border: rgba(255, 255, 255, 0.08);
    --shadow: 0 18px 38px rgba(5, 8, 20, 0.55);
    --input-bg: #0b1026;
    --input-border: var(--border);
}
[data-theme="light"] {
    --bg: #f6f8fc;
    --bg-gradient: radial-gradient(circle at 20% -10%, #ffffff 0%, #e8eef8 55%);
    --panel: #ffffff;
    --panel-strong: #f1f4fb;
    --accent: #1a73e8;       /* same accent in both themes */
    --accent-strong: #0f5cc8;
    --text: #0b152c;
    --muted: #5b6a85;
    --border: rgba(0, 0, 0, 0.08);
    --shadow: 0 12px 28px rgba(0, 0, 0, 0.12);
    --input-bg: #eef2fb;
    --input-border: rgba(0, 0, 0, 0.12);
}
```

Toggle with `document.documentElement.setAttribute('data-theme', 'light' | 'dark')`; persist to
`localStorage` under a per-app key (e.g. `lvc-theme`); resolve initial theme as
`localStorage → prefers-color-scheme: dark → light fallback`.

**Status colors** (hard-coded in component selectors, not custom properties — reuse verbatim):

| Semantic use | Value |
|---|---|
| Active/connected | `#22c55e`, glow `rgba(34, 197, 94, 0.65)` |
| Error/disconnected | `#ef4444`, glow `rgba(239, 68, 68, 0.65)` |
| Danger button | `#dc3545` |
| Metric accents | CPU `#1ad0ff`, NPU `#b388ff`, RAM `var(--muted)` |

**Typography:** system font stack — `-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto',
'Helvetica Neue', Arial, sans-serif`. Headings: `h1, h2 { font-size: clamp(1.2rem, 2vw, 1.8rem); }`.
No global type-scale tokens; representative sizes `0.7rem`–`0.85rem` for compact status/metadata
text.

**Spacing:** literal values, no scale — `header { gap: 12px; padding: 4px 16px; }`,
`main { padding: 5px 20px; }`, `.panels { gap: 6px; }`, `.field-row { gap: 8px; }`.

**Radius:** no token — `.card { border-radius: 10px; }`, buttons `6px`, dots `50%`.

**Shadow:** single `--shadow` token per theme (see above), consumed by `.card` and tooltips.

## Cross-stack invariant

All three independently converge on an Intel-blue-family primary (`#0054AE` / `#0071c5` /
`#1a73e8`) and the same green/red semantics for success/error. This is the one thing to preserve
when building a new app in any of the three stacks — pick the *reference stack's own* accent value
above, don't average them or invent a new one.
