"""Modèle actuariel fréquence-sévérité (modèle collectif).

Perte agrégée sur une période : S = X_1 + ... + X_N, avec
- N le nombre de pertes (fréquence : Poisson ou binomiale négative),
- X_i les montants (sévérité : Gamma, lognormale ou Pareto),
- N et les X_i indépendants, les X_i indépendants et de même loi.
Moments : E[S] = E[N] E[X] ; Var[S] = E[N] Var[X] + Var[N] E[X]².
"""
