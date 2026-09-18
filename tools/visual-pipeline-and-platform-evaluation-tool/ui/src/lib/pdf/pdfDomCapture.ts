import domtoimage from "dom-to-image";

export const PDF_EXPORT_IGNORE_ATTRIBUTE = "data-export-ignore";

export const isPdfExportIgnored = (node: Node) =>
  node instanceof Element && node.hasAttribute(PDF_EXPORT_IGNORE_ATTRIBUTE);

// Tables render inside a horizontally scrollable container (see
// `components/ui/table.tsx`). dom-to-image only captures the currently
// visible (clipped) width of such containers, which cuts off the right
// side of any table wider than the viewport. We temporarily expand these
// containers to their full natural width before taking the snapshot so
// the whole table is included in the export. Since shrinking the
// container to its natural (`max-content`) width can make it narrower
// than its parent, we also center it horizontally so narrow tables don't
// end up left-aligned with blank space to their right.
const SCROLLABLE_TABLE_CONTAINER_SELECTOR = '[data-slot="table-container"]';

type ScrollableTableContainerStyle = {
  element: HTMLElement;
  overflow: string;
  width: string;
  marginLeft: string;
  marginRight: string;
};

const expandScrollableTableContainers = (
  root: HTMLElement,
): ScrollableTableContainerStyle[] => {
  const elements = Array.from(
    root.querySelectorAll<HTMLElement>(SCROLLABLE_TABLE_CONTAINER_SELECTOR),
  );

  return elements.map((element) => {
    const original: ScrollableTableContainerStyle = {
      element,
      overflow: element.style.overflow,
      width: element.style.width,
      marginLeft: element.style.marginLeft,
      marginRight: element.style.marginRight,
    };

    element.style.overflow = "visible";
    element.style.width = "max-content";
    element.style.marginLeft = "auto";
    element.style.marginRight = "auto";

    return original;
  });
};

const restoreScrollableTableContainers = (
  originalStyles: ScrollableTableContainerStyle[],
) => {
  originalStyles.forEach(
    ({ element, overflow, width, marginLeft, marginRight }) => {
      element.style.overflow = overflow;
      element.style.width = width;
      element.style.marginLeft = marginLeft;
      element.style.marginRight = marginRight;
    },
  );
};

// The export root itself is often centered on the page via a `mx-auto`
// (or similar) margin. `getComputedStyle` resolves that `auto` margin to a
// concrete pixel value, which dom-to-image then copies verbatim onto the
// cloned node. Since the SVG used for rendering is sized to the node's own
// `scrollWidth` (which excludes margins), that copied margin shows up as
// blank space on the left of the exported image and pushes content past
// the right edge, where it gets clipped. Neutralize the root's margin for
// the duration of the capture so the content starts flush at (0, 0).
type RootMarginStyle = {
  marginLeft: string;
  marginRight: string;
  marginTop: string;
  marginBottom: string;
};

const resetRootMargin = (node: HTMLElement): RootMarginStyle => {
  const original: RootMarginStyle = {
    marginLeft: node.style.marginLeft,
    marginRight: node.style.marginRight,
    marginTop: node.style.marginTop,
    marginBottom: node.style.marginBottom,
  };

  node.style.marginLeft = "0";
  node.style.marginRight = "0";
  node.style.marginTop = "0";
  node.style.marginBottom = "0";

  return original;
};

const restoreRootMargin = (node: HTMLElement, original: RootMarginStyle) => {
  node.style.marginLeft = original.marginLeft;
  node.style.marginRight = original.marginRight;
  node.style.marginTop = original.marginTop;
  node.style.marginBottom = original.marginBottom;
};

// When the exported content spans multiple PDF pages, naively slicing the
// captured image at fixed height intervals can cut a table row in half
// right at the page break. To avoid that, we record the bottom edge (in
// px, relative to the export root) of every table row before capturing,
// so pagination can later snap each page break to the nearest row
// boundary instead of an arbitrary pixel offset.
const TABLE_ROW_SELECTOR = '[data-slot="table-row"]';

const getRowBreakOffsetsPx = (node: HTMLElement): number[] => {
  const nodeTop = node.getBoundingClientRect().top;
  const rows = Array.from(
    node.querySelectorAll<HTMLElement>(TABLE_ROW_SELECTOR),
  );
  const offsets = rows.map(
    (row) => row.getBoundingClientRect().bottom - nodeTop,
  );

  return Array.from(new Set(offsets)).sort((a, b) => a - b);
};

export type CapturedPdfNode = {
  /** Base64 data URL of the rasterized node. */
  imageData: string;
  /** MIME image format the data URL was encoded with. */
  format: "image/png" | "image/jpeg";
  /** Bottom edges of every table row (px, relative to the node), sorted ascending. */
  rowBreakOffsetsPx: number[];
};

type CaptureNodeAsImageOptions = {
  node: HTMLElement;
  backgroundColor: string;
  imageQuality: number;
  filter: (node: Node) => boolean;
};

/**
 * Rasterizes `node` into a JPEG data URL, applying a handful of temporary
 * DOM mutations first so the export doesn't inherit clipping/centering
 * quirks from the live page layout (see the helpers above for details on
 * each fix). All mutations are reverted before this function returns,
 * regardless of success or failure.
 *
 * JPEG (rather than PNG) is used deliberately: dom-to-image's `toPng`
 * ignores the `quality` option entirely and always produces a lossless
 * (and often multi-megabyte) image, which is slow to encode/decode for
 * large tables. Since the export always paints an opaque background,
 * JPEG's lack of alpha support is not a concern, and `imageQuality` now
 * has a real, meaningful effect on export speed and PDF file size.
 */
export const captureNodeAsImage = async ({
  node,
  backgroundColor,
  imageQuality,
  filter,
}: CaptureNodeAsImageOptions): Promise<CapturedPdfNode> => {
  const originalContainerStyles = expandScrollableTableContainers(node);
  const originalRootMargin = resetRootMargin(node);

  try {
    const rowBreakOffsetsPx = getRowBreakOffsetsPx(node);
    const imageData = await domtoimage.toJpeg(node, {
      bgcolor: backgroundColor,
      quality: imageQuality,
      filter,
    });

    return { imageData, format: "image/jpeg", rowBreakOffsetsPx };
  } finally {
    restoreRootMargin(node, originalRootMargin);
    restoreScrollableTableContainers(originalContainerStyles);
  }
};
