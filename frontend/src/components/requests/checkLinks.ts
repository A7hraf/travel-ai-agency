/** Links for the team to check an option on booking sites (route, dates and travellers already filled in).
 *  Only for staff: the client never sees them. */
export interface TripCase { from?: string | null; to?: string | null; depart?: string | null; back?: string | null; people?: number }
export interface CheckLink { label: string; url: string }

const q = (s: string) => encodeURIComponent(s.replace(/\s+/g, " ").trim());

export function checkLinks(category: string, title: string, provider: string | null | undefined, c: TripCase): CheckLink[] {
  const to = c.to?.trim() ?? "";
  const name = [provider, title].filter(Boolean).join(" ");
  const people = Math.max(1, c.people ?? 1);
  if (category === "flight") {
    const words = [`Flights from ${c.from || "Muscat"} to ${to}`, c.depart && `on ${c.depart}`, c.back && `returning ${c.back}`,
      provider && `with ${provider}`, people > 1 && `${people} passengers`].filter(Boolean).join(" ");
    return [{ label: "Google Flights", url: `https://www.google.com/travel/flights?q=${q(words)}` }];
  }
  if (category === "hotel") {
    const dates = c.depart && c.back ? `&checkin=${c.depart}&checkout=${c.back}` : "";
    return [
      { label: "Booking.com", url: `https://www.booking.com/searchresults.html?ss=${q(`${name} ${to}`)}${dates}&group_adults=${people}` },
      { label: "Google Hotels", url: `https://www.google.com/travel/search?q=${q(`${name} ${to}`)}` },
    ];
  }
  if (category === "activity") {
    return [
      { label: "GetYourGuide", url: `https://www.getyourguide.com/s/?q=${q(`${title} ${to}`)}` },
      { label: "Tripadvisor", url: `https://www.tripadvisor.com/Search?q=${q(`${name} ${to}`)}` },
    ];
  }
  return [{ label: "Google Maps", url: `https://www.google.com/maps/search/${q(`${name} ${to}`)}` }];
}
