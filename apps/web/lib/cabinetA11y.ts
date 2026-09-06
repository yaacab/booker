/** Stable DOM id for cabinet widget headings (aria-labelledby). */
export function cabinetWidgetHeadingId(title: string): string {
  const slug = title
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-+|-+$/g, "");
  return `cabinet-widget-${slug || "section"}`;
}

/** CSS selector fragment for reduced-motion cabinet hover resets. */
export const CABINET_REDUCED_MOTION_SELECTORS = [
  ".dashboard-list li a:hover",
  ".dashboard-grid .card:hover",
  ".grid > .card:hover",
] as const;
