import { Banner } from "@/components/ui/Banner";
import type { Notice } from "@/lib/forecast";

/** Data-quality notes, shown beside the number they qualify rather than hidden below it. */
export function Notices({ items }: { items: readonly Notice[] }) {
  if (items.length === 0) return null;
  return (
    <ul className="space-y-2" aria-label="Things to know about this forecast">
      {items.map((n) => (
        <li key={n.id}>
          <Banner tone={n.tone} title={n.title}>
            {n.body}
          </Banner>
        </li>
      ))}
    </ul>
  );
}
