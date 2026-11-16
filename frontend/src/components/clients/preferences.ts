/** The client preferences the AI learns and the team writes (same keys as the server's client_profile.py). */
export const PREFERENCE_LABELS: [string, string][] = [
  ["airline", "Favourite airline"],
  ["cabin", "Class"],
  ["seat", "Seat (window, aisle, emergency exit…)"],
  ["flight_time", "Flight time (morning, night…)"],
  ["hotel_stars", "Hotel stars"],
  ["hotel_style", "Hotel features (pool, beach, city centre…)"],
  ["room", "Room (bed type, view, connecting rooms…)"],
  ["meal", "Meals and diet"],
  ["transport", "Transport (private car, driver…)"],
  ["activities", "Activities they like"],
  ["special_needs", "Special needs"],
  ["notes", "Other notes"],
];
export const PREFERENCE_LABEL = Object.fromEntries(PREFERENCE_LABELS);
