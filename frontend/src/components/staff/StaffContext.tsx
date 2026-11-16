import { createContext, ReactNode, useContext } from "react";

/** A glass toast at the top of the team app. Tap opens what it is about. */
export interface StaffToast {
  id?: number;
  tone: "amber" | "cyan" | "teal" | "magenta";
  icon: ReactNode;
  title: string;
  text?: string;
  onOpen?: () => void;
}

export interface StaffState {
  /** Chats handed to the team that nobody has taken yet. */
  needsHuman: number;
  /** Tickets waiting for payment or in progress. */
  openTickets: number;
  /** Name of the agency's AI consultant ("Sara"); empty until known. */
  agentName: string;
  toast: (t: StaffToast) => void;
  /** Re-read the badge counts now (after taking over a chat, moving a ticket…). */
  refreshCounts: () => void;
}

export const StaffContext = createContext<StaffState>({
  needsHuman: 0,
  openTickets: 0,
  agentName: "",
  toast: () => {},
  refreshCounts: () => {},
});

export function useStaff(): StaffState {
  return useContext(StaffContext);
}

/** "AB" from "Ali Bakr"; empty when the label is not a name (a phone number or an email). */
export function initials(label: string): string {
  if (!label || /^[+\d(]/.test(label) || label.includes("@")) return "";
  return label
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();
}
