import { useEffect, useState } from "react";
import { actuarialApi } from "../services/actuarial.js";

// Portefeuilles de l'utilisateur et actifs disponibles (sélecteurs du module Actuariat).
export default function useActuarialRefs() {
  const [portfolios, setPortfolios] = useState([]);
  const [assets, setAssets] = useState([]);

  useEffect(() => {
    actuarialApi("/portfolios").then(setPortfolios).catch(() => setPortfolios([]));
    actuarialApi("/assets").then(setAssets).catch(() => setAssets([]));
  }, []);

  return { portfolios, assets, assetsWithHistory: assets.filter((a) => a.observations >= 2) };
}
