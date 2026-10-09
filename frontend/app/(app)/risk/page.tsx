import type { Metadata } from "next";

import { RiskScreen } from "@/components/screens/RiskScreen";

export const metadata: Metadata = { title: "BNPL risk check" };

export default function Page() {
  return <RiskScreen />;
}
