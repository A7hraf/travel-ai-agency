import { CSSProperties, ReactNode } from "react";

/** Destination look per place: poster hue and airport code ("MCT → MLE"). Matched on the package's
 *  destination, country and title, in English or Arabic. Unknown places get a stable hue from their name. */
const PLACES: { words: string[]; hue: number; iata: string }[] = [
  { words: ["maldives", "male", "malé", "المالديف", "ماليه"], hue: 205, iata: "MLE" },
  { words: ["istanbul", "turkey", "türkiye", "turkiye", "cappadocia", "إسطنبول", "اسطنبول", "تركيا"], hue: 25, iata: "IST" },
  { words: ["salalah", "dhofar", "khareef", "صلالة", "ظفار"], hue: 150, iata: "SLL" },
  { words: ["dubai", "uae", "emirates", "دبي", "الإمارات"], hue: 65, iata: "DXB" },
  { words: ["georgia", "tbilisi", "batumi", "جورجيا", "تبليسي"], hue: 320, iata: "TBS" },
  { words: ["cairo", "egypt", "nile", "القاهرة", "مصر"], hue: 80, iata: "CAI" },
  { words: ["zanzibar", "tanzania", "زنجبار", "تنزانيا"], hue: 180, iata: "ZNZ" },
  { words: ["umrah", "makkah", "mecca", "madinah", "saudi", "jeddah", "عمرة", "مكة", "السعودية", "جدة"], hue: 100, iata: "JED" },
  { words: ["bali", "indonesia", "بالي", "إندونيسيا"], hue: 130, iata: "DPS" },
  { words: ["paris", "france", "swiss", "switzerland", "باريس", "فرنسا"], hue: 265, iata: "CDG" },
  { words: ["london", "uk", "united kingdom", "لندن"], hue: 240, iata: "LHR" },
  { words: ["thailand", "bangkok", "phuket", "تايلاند"], hue: 170, iata: "BKK" },
  { words: ["malaysia", "kuala lumpur", "ماليزيا"], hue: 140, iata: "KUL" },
];

export interface Place { hue: number; iata: string }

export function placeOf(...texts: (string | null | undefined)[]): Place {
  const hay = texts.filter(Boolean).join(" ").toLowerCase();
  const known = PLACES.find((p) => p.words.some((w) => hay.includes(w)));
  if (known) return { hue: known.hue, iata: known.iata };
  let h = 0;
  for (const ch of hay) h = (h * 31 + ch.charCodeAt(0)) % 360;
  const letters = (texts.find(Boolean) ?? "").normalize("NFD").replace(/[^A-Za-z]/g, "").toUpperCase();
  return { hue: h, iata: (letters + "XXX").slice(0, 3) };
}

/** A destination poster: photo when the package has one, otherwise the CSS art (sun, horizon,
 *  halftone) in the destination's hue, with the "DEPARTS MCT" stamp and the route line. */
export function Poster({ destination, country, title, imageUrl, className = "", style, stamp = true, route = true, children }: {
  destination: string;
  country?: string;
  title?: string;
  imageUrl?: string | null;
  className?: string;
  style?: CSSProperties;
  stamp?: boolean;
  route?: boolean;
  children?: ReactNode;
}) {
  const place = placeOf(destination, country, title);
  return (
    <div className={`poster ${imageUrl ? "has-photo" : ""} ${className}`} style={{ ["--h" as string]: place.hue, ...style }}>
      {imageUrl ? <img className="poster-photo" src={imageUrl} alt="" loading="lazy" /> : <div className="poster-sun" />}
      <div className="poster-bands" />
      {!imageUrl && <div className="poster-halftone" />}
      {route && <div className="poster-route">MCT → {place.iata}</div>}
      {stamp && <div className="poster-stamp" aria-hidden="true"><span>Departs<b>MCT</b>✈</span></div>}
      {children}
    </div>
  );
}
