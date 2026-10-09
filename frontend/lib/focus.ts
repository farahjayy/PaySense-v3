/**
 * After something the person was focused on disappears (a deleted row, a closed step), keyboard
 * and screen-reader users would be dropped at the top of the document. Put them on the page
 * heading instead. Deferred a frame so it runs after a closing dialog has restored its own focus.
 */
export function focusPageHeading(root: Document = document): void {
  requestAnimationFrame(() => {
    root.querySelector<HTMLElement>("main h1")?.focus();
  });
}
