/** Makes the Arabic texts of the Instagram channel available right away (locales/ar-instagram.ts).
 *  Texts already in the main dictionary win, so this keeps working once ar.ts merges AR_INSTAGRAM. */
import { AR } from "../../locales/ar";
import { AR_INSTAGRAM } from "../../locales/ar-instagram";

for (const [en, ar] of Object.entries(AR_INSTAGRAM) as [string, string][]) {
  if (!(en in AR)) AR[en] = ar;
}

export {};
