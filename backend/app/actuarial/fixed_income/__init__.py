"""Obligations à taux fixe : flux, prix, rendement actuariel, duration, convexité, chocs de taux.

Conventions :
- coupon = valeur nominale x taux de coupon / fréquence, versé aux dates obtenues en
  reculant depuis l'échéance par pas de 12 / fréquence mois ;
- temps t des flux en années depuis la date de règlement, selon la base de calcul
  (ACT/365, ACT/360 ou 30/360) ;
- actualisation à composition périodique : DF(t) = (1 + y/f)^(-f t) ;
- prix plein (dirty) = somme des flux actualisés ; prix pied de coupon (clean) =
  prix plein - coupon couru ; coupon couru au prorata des jours de la période en cours.
"""
