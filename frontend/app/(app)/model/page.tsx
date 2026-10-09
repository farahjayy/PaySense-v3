import type { Metadata } from "next";

import { ModelScreen } from "@/components/screens/ModelScreen";

export const metadata: Metadata = { title: "About the model" };

export default function Page() {
  return <ModelScreen />;
}
