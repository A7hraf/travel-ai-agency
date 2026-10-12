import { useI18n } from "../lang";

// Official Omani rial sign (Central Bank of Oman, 2025; Unicode U+20C4). Drawn as a vector because
// most fonts do not contain the new sign yet. Traced from the MIT-licensed "oman-currency" package.
const OMR_PATH = "M1 479C0 478 1 475 4 472C6 469 8 465 9 464C9 463 11 460 13 456C16 453 19 447 22 442C24 437 30 428 34 422C38 416 41 411 41 410C41 409 44 404 48 398C53 390 56 386 58 386C59 386 136 385 228 385C320 385 397 385 399 384L402 384L396 377C387 368 376 354 370 345C368 342 366 338 364 337L362 334L231 334C114 334 100 334 99 332C99 330 106 317 116 300C122 292 126 284 126 283C127 281 137 265 142 258C143 256 144 255 144 254C144 254 146 250 148 247C151 242 152 240 156 239C160 237 162 237 217 237C279 238 287 238 323 237C325 237 326 236 326 236C326 235 327 234 327 234C328 233 329 228 329 211C329 198 330 189 330 188C331 188 331 184 332 181C332 177 333 174 333 172C333 171 334 168 334 165C335 162 335 159 336 159C337 158 337 156 337 154C337 152 338 149 338 148C339 147 340 145 340 144C340 142 341 140 342 139C342 137 343 135 343 134C343 133 344 131 344 129C345 128 346 125 347 123C348 121 349 119 349 118C349 116 350 114 352 112C353 109 354 107 355 106C355 105 356 103 357 102C357 100 358 98 358 98C358 97 359 94 361 92C363 90 364 87 364 86C364 85 367 80 383 55C385 52 387 50 387 50C388 50 389 48 391 45C393 42 398 36 401 32C405 29 408 25 408 25C408 23 421 15 429 10C438 6 441 5 452 3C459 1 476 1 486 3C497 5 506 7 516 11C523 13 528 16 542 23C545 24 548 26 550 28C551 29 553 30 553 30C555 30 563 36 576 46C592 58 609 75 609 78C609 80 574 214 573 216C571 219 570 219 564 211C558 204 533 180 527 175C489 143 455 128 423 129C409 130 402 132 391 137C381 142 373 150 368 158C366 163 366 164 366 172C366 180 366 181 369 188C375 201 383 212 398 228C407 238 407 238 430 238C439 238 449 238 453 238C461 238 487 238 512 238C519 238 544 238 566 238C588 238 676 238 762 237C917 237 922 237 922 240C922 241 910 262 895 288L868 334L700 334L532 334L538 338C548 345 581 362 594 367C612 374 631 381 633 381C635 381 636 381 637 382C639 384 650 384 735 385C795 385 823 386 824 387C825 387 818 400 799 432C785 457 772 478 772 479L771 481L386 481C34 481 1 481 1 479Z";

export function OmrSign({ title = "Omani rial" }: { title?: string }) {
  return (
    <svg className="omr-sign" viewBox="0 0 924 482" role="img" aria-label={title}>
      <title>{title}</title>
      <path fill="currentColor" fillRule="evenodd" d={OMR_PATH} />
    </svg>
  );
}

export type Lang = "en" | "ar";

function fractionDigits(currency: string): number {
  try {
    return new Intl.NumberFormat("en", { style: "currency", currency }).resolvedOptions().maximumFractionDigits ?? 2;
  } catch {
    return 2;
  }
}

/** The number only, with the currency's own decimals (3 for the Omani rial: 1 rial = 1000 baisa). */
export function formatAmount(value: number, currency: string, lang: Lang = "en"): string {
  const digits = fractionDigits(currency);
  return new Intl.NumberFormat(lang === "ar" ? "ar-OM-u-nu-latn" : "en-OM", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

/** Text form, for places where a picture cannot be used (titles, confirm boxes). */
export function moneyText(value: number, currency: string, lang: Lang = "en"): string {
  const amount = formatAmount(value, currency, lang);
  if (currency === "OMR") return lang === "ar" ? `${amount} ر.ع.` : `OMR ${amount}`;
  return `${amount} ${currency}`;
}

export function Money({ value, currency, lang: langProp }: { value: number; currency: string; lang?: Lang }) {
  const { lang: uiLang } = useI18n();
  const lang = langProp ?? uiLang;
  const amount = formatAmount(value, currency, lang);
  if (currency !== "OMR") {
    return <span className="money" dir="ltr">{amount} {currency}</span>;
  }
  // Arabic: amount then sign (read right to left). English: sign then amount.
  return lang === "ar" ? (
    <span className="money" dir="rtl">{amount}&nbsp;<OmrSign title="ريال عماني" /></span>
  ) : (
    <span className="money" dir="ltr"><OmrSign />&nbsp;{amount}</span>
  );
}
