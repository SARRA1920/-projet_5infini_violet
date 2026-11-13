"""Module Actuariat : Actuarial & Quantitative Risk Analytics.

Calculs actuariels et quantitatifs (risque, modèles stochastiques, obligations,
optimisation, modèles de pertes). Aucun modèle d'IA ou de Machine Learning.

Organisation :
- risk/, stochastic/, fixed_income/, optimization/, loss_models/ : fonctions
  mathématiques pures (tableaux numpy en entrée, aucun accès à la base) ;
- services/ : lecture des données existantes (price_history, portfolios,
  positions, transactions) et assemblage des résultats ;
- api.py : routes FastAPI sous /api/actuarial ;
- models.py : tables propres au module (migrations additives uniquement).

Conventions communes (détaillées dans risk/var.py) :
- rendements simples quotidiens r_t = P_t / P_(t-1) - 1 ;
- perte L = -r, positive quand on perd de l'argent ;
- résultats en fractions (0.023 = 2,3 %), montants dans la devise des cours ;
- 252 jours de bourse par an.
"""
