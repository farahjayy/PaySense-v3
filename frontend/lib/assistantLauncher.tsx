"use client";

import { createContext, useContext } from "react";

/** Opens the assistant panel, optionally with a question already in the message box (never sent
 * for the person: they press Send). Provided by the app shell; null outside it. */
export type OpenAssistant = (prompt?: string) => void;

export const AssistantLauncher = createContext<OpenAssistant | null>(null);

export function useOpenAssistant(): OpenAssistant | null {
  return useContext(AssistantLauncher);
}
