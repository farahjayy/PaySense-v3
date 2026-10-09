import type { Metadata } from "next";

import { RecurringScreen } from "@/components/screens/RecurringScreen";

export const metadata: Metadata = { title: "Recurring items" };

export default function Page() {
  return <RecurringScreen />;
}
