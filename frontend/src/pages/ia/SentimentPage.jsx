import { useState, useEffect } from "react";
import { api } from "../../services/api.js";
import { iaApi, postIa } from "../../services/ia.js";
import { fmtPct, toneOf, SENTIMENT_LABELS, SENTIMENT_TONES } from "../../services/ia.js";

export default function SentimentPage() {
  const [text, setText] = useState("");
  const [result, setResult] = useState(null);
  const [symbol, setSymbol] = useState("AAPL");
  const [symbolData, setSymbolData] = useState(null);
  const [assets, setAssets] = useState([]);

  // Liste des actifs disponibles (ceux qui ont un cours en base) pour le menu déroulant.
  useEffect(() => {
    api("/quotes")
      .then(setAssets)
      .catch(() => {});
  }, []);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function analyzeText(e) {
    e.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const data = await postIa("/sentiment/analyze", { text });
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function fetchSymbol(e) {
    e.preventDefault();
    setLoading(true);
    setError("");
    setSymbolData(null);
    try {
      const data = await iaApi(`/sentiment/${symbol.toUpperCase()}`);
      setSymbolData(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="ia-section">
      <div className="ia-panel">
        <h2>Analyser un texte</h2>
        <p className="ia-help">
          Collez un titre d'actualité ou un commentaire financier. Le moteur est
          multilingue : lexique financier français (négation, intensifiants) pour un
          texte FR, VADER ou lexique financier anglais pour un texte EN — score entre
          -1 (très négatif) et +1 (très positif). La « méthode » affiche le moteur
          réellement utilisé.
        </p>
        <form className="ia-form" onSubmit={analyzeText}>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Ex : Apple annonce des bénéfices record au 3e trimestre, battant les attentes."
            rows={3}
            required
          />
          <button type="submit" disabled={loading}>
            {loading ? "Analyse…" : "Analyser le sentiment"}
          </button>
        </form>

        {result && (
          <div className="sentiment-result">
            <div className={`sentiment-badge ${SENTIMENT_TONES[result.label] || ""}`}>
              {SENTIMENT_LABELS[result.label] || result.label}
            </div>
            <div className="sentiment-score">
              Score : <strong className={toneOf(result.score)}>{result.score.toFixed(3)}</strong>
            </div>
            <div className="sentiment-bar">
              <div
                className="sentiment-bar-fill"
                style={{ width: `${((result.score + 1) / 2) * 100}%` }}
              />
            </div>
            <p className="sentiment-source">Méthode : {result.source}</p>
          </div>
        )}
      </div>

      <div className="ia-panel">
        <h2>Sentiment par actif</h2>
        <p className="ia-help">
          Récupère le sentiment agrégé des titres d'actualité associés à un symbole.
          Les titres proviennent du flux RSS Yahoo Finance (repli Google News) et sont
          <strong> filtrés</strong> : seuls les titres mentionnant le ticker ou le nom
          de l'entreprise sont analysés. Le scoring est multilingue (FR/EN) ; le score
          global est la moyenne des titres pertinents, entre -1 et +1.
        </p>
        <form className="ia-form" onSubmit={fetchSymbol}>
          <label>
            Symbole
            <select value={symbol} onChange={(e) => setSymbol(e.target.value)} required>
              {assets.length === 0 && <option value="">Chargement des actifs…</option>}
              {assets.map((a) => (
                <option key={a.symbol} value={a.symbol}>
                  {a.symbol} — {a.name}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" disabled={loading}>
            {loading ? "Chargement…" : "Récupérer"}
          </button>
        </form>

        {symbolData && (
          <div className="sentiment-result">
            <div className={`sentiment-badge ${SENTIMENT_TONES[symbolData.aggregate_label] || ""}`}>
              {SENTIMENT_LABELS[symbolData.aggregate_label] || symbolData.aggregate_label}
            </div>
            <div className="sentiment-score">
              Score global :{" "}
              <strong className={toneOf(symbolData.aggregate_score)}>
                {symbolData.aggregate_score.toFixed(3)}
              </strong>
            </div>
            {symbolData.headlines.length > 0 ? (
              <ul className="headline-list">
                {symbolData.headlines.map((h, i) => (
                  <li key={i}>
                    <span>{h.title}</span>
                    <em className={SENTIMENT_TONES[h.label] || ""}>
                      {SENTIMENT_LABELS[h.label] || h.label} ({h.score.toFixed(2)})
                    </em>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="banner">
                Aucun titre pertinent pour {symbolData.symbol} pour l'instant — soit la
                source RSS (Yahoo Finance / Google News) est momentanément indisponible,
                soit aucun titre récent ne mentionne {symbolData.symbol}. Le score global
                reste neutre tant qu'aucun titre pertinent n'est trouvé.
              </p>
            )}
            {symbolData.headlines.length > 0 && (
              <p className="sentiment-source">
                Méthode : {symbolData.source} — {symbolData.headlines.length} titre(s)
                pertinent(s) après filtrage
              </p>
            )}
          </div>
        )}
      </div>

      {error && <p className="banner error">{error}</p>}
    </div>
  );
}
