export interface FeatureInfo { key: string; label: string; kind: "tab" | "ai" | "part" | "extra"; parent: string | null; metered: boolean; levels: string[] }
export interface Grant { on: boolean; limit: number | null; period: "month" | "total"; seats: number | null; admins_only?: boolean; price: string | null; levels: string[] }
export interface FeatureState { catalog: FeatureInfo[]; grants: Record<string, Grant>; usage: Record<string, number>; seats?: Record<string, number[]> }
export const LEVEL_LABELS: Record<string, string> = {
  basic: "Basic figures", marketing: "Marketing data", deep: "Deep analysis", finance: "Finance",
  segments: "Client groups", predictions: "Who travels next", targeting: "Messages to a group",
  platform_keys: "Your central keys", own_keys: "Its own keys",
};
