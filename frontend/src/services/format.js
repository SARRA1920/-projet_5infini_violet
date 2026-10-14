// Formatage à la française des montants reçus en texte (Decimal côté API).
// Uniquement de la manipulation de chaîne : aucune conversion en Number,
// donc aucun arrondi ni calcul en JavaScript.

const GROUP = "\u202f"; // espace fine insécable, séparateur de milliers

export function formatDecimal(value, minDecimals = 2) {
  if (value === null || value === undefined || value === "") return "—";
  const text = String(value);
  const negative = text.startsWith("-");
  const [intPart, decPart = ""] = (negative ? text.slice(1) : text).split(".");
  let decimals = decPart;
  while (decimals.length > minDecimals && decimals.endsWith("0")) {
    decimals = decimals.slice(0, -1);
  }
  decimals = decimals.padEnd(minDecimals, "0");
  const grouped = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, GROUP);
  return `${negative ? "-" : ""}${grouped}${decimals ? `,${decimals}` : ""}`;
}

// "up" si strictement positif, "down" si négatif, "" si nul (lecture du texte).
export function signClass(value) {
  if (value === null || value === undefined) return "";
  const text = String(value);
  if (/^-?0*(\.0*)?$/.test(text)) return "";
  return text.startsWith("-") ? "down" : "up";
}

export function formatSigned(value, minDecimals = 2) {
  const formatted = formatDecimal(value, minDecimals);
  return signClass(value) === "up" ? `+${formatted}` : formatted;
}

// executed_at arrive sans fuseau ; la base PostgreSQL est en UTC.
export function formatDateTime(value) {
  if (!value) return "—";
  const iso = /[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`;
  return new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}
