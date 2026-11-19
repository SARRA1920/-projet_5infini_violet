// Module IA : appels API vers /api/ia et formatage.
// Les rendements et scores arrivent en fractions (0.023 = 2,3 %).
import { api } from "./api.js";

export function iaApi(path, params) {
  const query = params ? `?${new URLSearchParams(params)}` : "";
  return api(`/api/ia${path}${query}`);
}

export function postIa(path, body) {
  return api(`/api/ia${path}`, { method: "POST", body: JSON.stringify(body) });
}

const percent = new Intl.NumberFormat("fr-FR", {
  style: "percent",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const price = new Intl.NumberFormat("fr-FR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const missing = (value) => value === null || value === undefined || Number.isNaN(value);

export const fmtPct = (value) => (missing(value) ? "—" : percent.format(value));
export const fmtPrice = (value) => (missing(value) ? "—" : price.format(value));
export const toneOf = (value) => (missing(value) || value === 0 ? "" : value > 0 ? "up" : "down");

// Étiquettes lisibles pour les actions et labels de sentiment.
export const ACTION_LABELS = { BUY: "Acheter", SELL: "Vendre", HOLD: "Conserver" };
export const ACTION_TONES = { BUY: "up", SELL: "down", HOLD: "" };
export const SENTIMENT_LABELS = { positif: "Positif", neutre: "Neutre", négatif: "Négatif" };
export const SENTIMENT_TONES = { positif: "up", neutre: "", négatif: "down" };

// Horizons proposés à l'utilisateur (en jours).
export const HORIZONS = [
  { value: 1, label: "J+1" },
  { value: 3, label: "J+3" },
  { value: 5, label: "J+5" },
  { value: 10, label: "J+10" },
  { value: 21, label: "J+21" },
];
