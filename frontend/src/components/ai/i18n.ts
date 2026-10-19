/** Makes the Arabic texts of the AI training and WhatsApp screens available right away
 *  (locales/ar-ai.ts; texts already in the main dictionary win). */
import { AR } from "../../locales/ar";
import { AR_AI } from "../../locales/ar-ai";

for (const [en, ar] of Object.entries(AR_AI) as [string, string][]) {
  if (!(en in AR)) AR[en] = ar;
}

export {};
