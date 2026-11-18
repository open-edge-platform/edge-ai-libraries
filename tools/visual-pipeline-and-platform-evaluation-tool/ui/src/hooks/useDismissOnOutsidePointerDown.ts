import { useEffect, useRef, type RefObject } from "react";

/**
 * Selectors matching UI that Radix renders through a React portal
 * (Select/Dropdown/Popover/Dialog content). Such elements live outside the
 * observed element's DOM tree even though they are logically part of it, so
 * interacting with them must never trigger a dismiss.
 */
const OVERLAY_LAYER_SELECTORS = [
  '[data-slot="select-content"]',
  '[data-slot="dropdown-menu-content"]',
  '[data-slot="popover-content"]',
  '[data-slot="dialog-content"]',
  '[data-slot="alert-dialog-content"]',
  '[role="listbox"]',
  '[role="menu"]',
  '[role="dialog"]',
  '[role="alertdialog"]',
];

const PORTALLED_OVERLAY_SELECTOR = [
  "[data-radix-popper-content-wrapper]",
  ...OVERLAY_LAYER_SELECTORS,
].join(",");

/**
 * Only layers that are actually open. Radix keeps content mounted while it
 * plays its exit animation, and a closing layer must no longer block dismissal.
 */
const OPEN_OVERLAY_SELECTOR = OVERLAY_LAYER_SELECTORS.map(
  (selector) => `${selector}[data-state="open"]`,
).join(",");

const isOverlayLayerOpen = (): boolean =>
  document.body.style.pointerEvents === "none" ||
  Boolean(document.querySelector(OPEN_OVERLAY_SELECTOR));

const isPointInsideElement = (
  element: Element,
  x: number,
  y: number,
): boolean => {
  const rect = element.getBoundingClientRect();
  return x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom;
};

type UseDismissOnOutsidePointerDownOptions = {
  ref: RefObject<HTMLElement | null>;
  enabled: boolean;
  onDismiss: () => void;
  ignoreSelectors?: string[];
  shouldIgnore?: () => boolean;
};

/**
 * Dismisses a panel when the user interacts outside of it, while playing nicely
 * with portalled overlays (Radix Select, Dropdown, Popover, Dialog).
 *
 * Two details make this reliable where a naive `mousedown` + `contains()` check
 * fails:
 *
 * 1. It listens for `pointerdown` in the *capture* phase. Radix dismisses its
 *    own layers from a bubble-phase `pointerdown` listener, which always runs
 *    before any `mousedown` listener - by then the overlay is already closed and
 *    can no longer be detected.
 * 2. It hit-tests by coordinates instead of by event target. Portalled content
 *    lives outside the observed subtree, and while an overlay is open Radix sets
 *    `pointer-events: none` on `<body>`, which makes the browser retarget the
 *    event to `<body>`/`<html>` instead of the element under the cursor.
 */
export const useDismissOnOutsidePointerDown = ({
  ref,
  enabled,
  onDismiss,
  ignoreSelectors,
  shouldIgnore,
}: UseDismissOnOutsidePointerDownOptions): void => {
  const onDismissRef = useRef(onDismiss);
  const shouldIgnoreRef = useRef(shouldIgnore);
  const ignoreSelector = ignoreSelectors?.join(",") ?? "";

  useEffect(() => {
    onDismissRef.current = onDismiss;
    shouldIgnoreRef.current = shouldIgnore;
  }, [onDismiss, shouldIgnore]);

  useEffect(() => {
    if (!enabled) return;

    const handlePointerDown = (event: PointerEvent) => {
      if (shouldIgnoreRef.current?.()) return;

      const element = ref.current;
      if (!element) return;

      if (isOverlayLayerOpen()) return;

      if (isPointInsideElement(element, event.clientX, event.clientY)) return;

      const target = event.target as HTMLElement | null;

      if (target?.isConnected) {
        if (target.closest(PORTALLED_OVERLAY_SELECTOR)) return;
        if (ignoreSelector && target.closest(ignoreSelector)) return;
      }

      onDismissRef.current();
    };

    document.addEventListener("pointerdown", handlePointerDown, true);

    return () => {
      document.removeEventListener("pointerdown", handlePointerDown, true);
    };
  }, [enabled, ignoreSelector, ref]);
};
