"""Module IA : Intelligence & Prédictions.

Trois briques, alignées sur la maquette frontend « IA & Prédictions » :
- **Prédiction de cours** : régression du rendement futur à horizon N jours,
  à partir de features techniques (rendements lagués, SMA, RSI, volatilité).
  Modèle RandomForestRegressor (scikit-learn), entraîné à la demande sur
  l'historique local (price_history) et mis en cache en mémoire.
- **Analyse de sentiment** : score des titres d'actualité financière via
  VADER (lexique, léger, sans téléchargement de modèle). FinBERT est prévu
  comme évolution ultérieure (voir sentiment.py).
- **Agent de trading** : policy rule-based combinant prédiction, indicateurs
  techniques et sentiment pour produire un signal BUY / SELL / HOLD + score
  de confiance + raisons explicables.

Organisation :
- features.py : construction des features techniques (fonctions pures,
  tableaux numpy en entrée/sortie, aucun accès à la base) ;
- prediction.py : entraînement + inférence + cache en mémoire du modèle ;
- sentiment.py : analyse de sentiment des titres de news ;
- agent.py : agent de trading (policy + scoring) ;
- schemas.py : modèles Pydantic pour les réponses API ;
- api.py : routes FastAPI sous /api/ia.

Conventions (cohérentes avec app.actuarial et app.services.analysis) :
- rendements simples quotidiens r_t = P_t / P_(t-1) - 1 ;
- résultats en fractions (0.023 = 2,3 %) ;
- 252 jours de bourse par an pour les annualisations.
"""

__all__ = ["features", "prediction", "sentiment", "agent", "schemas", "api"]
