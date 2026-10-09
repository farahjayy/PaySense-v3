import type { Metadata } from "next";

import { PlansScreen } from "@/components/screens/PlansScreen";

export const metadata: Metadata = { title: "BNPL plans" };

export default function Page() {
  return <PlansScreen />;
}
