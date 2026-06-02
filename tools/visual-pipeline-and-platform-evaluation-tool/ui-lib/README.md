# @vippet/ui

Reusable UI components library for VIPPET applications. Built with React, Tailwind CSS v4, Radix UI, and shadcn/ui patterns.

## Installation

```bash
npm install @vippet/ui
```

### Peer Dependencies

Ensure your app has these installed:

```bash
npm install react react-dom tailwindcss
```

## Usage

### 1. Import the styles

In your app's main CSS file (e.g., `index.css`), import the library styles:

```css
@import "@vippet/ui/styles.css";
```

This provides the design tokens (colors, typography, spacing), Tailwind base setup, and dark mode support.

### 2. Use components

```tsx
import { Button, Card, CardHeader, CardTitle, CardContent } from "@vippet/ui";

function MyPage() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Hello</CardTitle>
      </CardHeader>
      <CardContent>
        <Button variant="default">Click me</Button>
      </CardContent>
    </Card>
  );
}
```

## Available Components

| Component | Description |
|-----------|-------------|
| `Accordion` | Collapsible content sections |
| `AlertDialog` | Modal confirmation dialogs |
| `Badge` | Status/label indicators |
| `Button` | Primary action element with variants |
| `Card` | Content container with header/footer |
| `Checkbox` | Boolean input control |
| `Dialog` | Modal overlay |
| `DropdownMenu` | Context/action menus |
| `Input` | Text input field |
| `InputGroup` | Input with addons (icons, buttons) |
| `Label` | Form field labels |
| `Popover` | Floating content panel |
| `Progress` | Progress bar indicator |
| `RadioGroup` | Single-select option group |
| `Resizable` | Resizable panel layout |
| `Select` | Dropdown selection |
| `Separator` | Visual divider |
| `Sheet` | Slide-in panel |
| `Skeleton` | Loading placeholder |
| `Slider` | Range input |
| `Switch` | Toggle control |
| `Table` | Data table |
| `Tabs` | Tabbed navigation |
| `Textarea` | Multi-line text input |
| `Toaster` | Toast notifications (sonner) |
| `Tooltip` | Hover information |

## Utilities

- `cn(...inputs)` — Tailwind class merge utility (clsx + tailwind-merge)

## Design Tokens

The library ships with a complete design token system:

- **Base palette** — Brand colors, neutrals, and accent palette
- **Semantic tokens** — Role-based tokens (background, foreground, primary, etc.)
- **Dark mode** — Automatic `.dark` class-based theming

You can also import tokens individually:

```css
@import "@vippet/ui/tokens/colors-base.css";
@import "@vippet/ui/tokens/colors-semantic.css";
```

## Development

```bash
npm run dev     # Build in watch mode
npm run build   # Production build
npm run lint    # Lint
npm run clean   # Remove dist/
```
