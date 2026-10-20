import { Skeleton } from "@/components/ui/States";

// Shown inside the shell the moment a link is clicked, until the next page arrives. It fades in
// late (`.route-loading`) so a fast page switch does not flash it.
export default function Loading() {
  return (
    <div className="route-loading mx-auto max-w-4xl space-y-6">
      <div className="h-9 w-48 rounded bg-line motion-safe:animate-pulse" />
      <Skeleton lines={6} label="Loading page" />
    </div>
  );
}
