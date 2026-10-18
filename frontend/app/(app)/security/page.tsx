import type { Metadata } from "next";

import { SecurityScreen } from "@/components/screens/SecurityScreen";

export const metadata: Metadata = { title: "Security drill" };

export default function Page() {
  return <SecurityScreen />;
}
