import type { Metadata } from "next";

import { AccountScreen } from "@/components/screens/AccountScreen";

export const metadata: Metadata = { title: "Your data" };

export default function Page() {
  return <AccountScreen />;
}
