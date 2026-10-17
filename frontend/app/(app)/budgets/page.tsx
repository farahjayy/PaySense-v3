import type { Metadata } from "next";

import { BudgetsScreen } from "@/components/screens/BudgetsScreen";

export const metadata: Metadata = { title: "Budgets" };

export default function Page() {
  return <BudgetsScreen />;
}
