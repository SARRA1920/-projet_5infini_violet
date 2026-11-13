// Module Actuariat : appels API et formatage des indicateurs.
// Les indicateurs arrivent en fractions (0.023 = 2,3 %) : ce sont des estimations
// statistiques en float, contrairement aux montants comptables de format.js.
import { api } from "./api.js";

export function actuarialApi(path, params) {
  const query = params ? `?${new URLSearchParams(params)}` : "";
  return api(`/api/actuarial${path}${query}`);
}

const percent = new Intl.NumberFormat("fr-FR", { style: "percent", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const amount = new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const ratio = new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const missing = (value) => value === null || value === undefined || Number.isNaN(value);

export const fmtPct = (value) => (missing(value) ? "—" : percent.format(value));
export const fmtAmount = (value) => (missing(value) ? "—" : amount.format(value));
export const fmtRatio = (value) => (missing(value) ? "—" : ratio.format(value));
const compact = new Intl.NumberFormat("fr-FR", { notation: "compact", maximumFractionDigits: 1 });
export const fmtCompact = (value) => (missing(value) ? "—" : compact.format(value));
export const fmtNum = (value, digits = 4) =>
  missing(value) ? "—" : value.toLocaleString("fr-FR", { minimumFractionDigits: digits, maximumFractionDigits: digits });
export const toneOf = (value) => (missing(value) || value === 0 ? "" : value > 0 ? "up" : "down");

export const ASSET_CLASS_LABELS = {
  stock: "Actions",
  bond: "Obligations",
  commodity: "Matières premières",
  forex: "Devises",
  cash: "Liquidités",
};

export const ASSET_CLASS_COLORS = {
  stock: "#8eb7ff",
  bond: "#3dd68c",
  commodity: "#f5b94a",
  forex: "#c084fc",
  cash: "#6f7d92",
};

export const METHOD_LABELS = {
  historical: "Historique",
  parametric: "Paramétrique",
  monte_carlo: "Monte Carlo",
};

export const PERIODS = [
  { value: 63, label: "3 mois" },
  { value: 126, label: "6 mois" },
  { value: 252, label: "1 an" },
  { value: 504, label: "2 ans" },
  { value: 0, label: "Tout l'historique" },
];

// Saisie en pourcentage ("3,5") -> fraction (0.035) ; null si vide ou invalide.
export function percentToFraction(text) {
  if (text === "" || text === null || text === undefined) return null;
  const value = Number(String(text).replace(",", ".")) / 100;
  return Number.isFinite(value) ? value : null;
}

export function parseNumber(text) {
  if (text === "" || text === null || text === undefined) return null;
  const value = Number(String(text).replace(",", "."));
  return Number.isFinite(value) ? value : null;
}

export function postActuarial(path, body) {
  return api(`/api/actuarial${path}`, { method: "POST", body: JSON.stringify(body) });
}

export const DATA_SOURCE_LABELS = {
  real_market_data: "Données de marché réelles",
  synthetic: "Données synthétiques",
  user_assumption: "Hypothèse utilisateur",
  simulated: "Résultat simulé",
};
