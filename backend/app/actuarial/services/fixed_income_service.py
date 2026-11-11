"""Fixed Income Analytics : obligations du référentiel et obligations théoriques.

Règle : aucune caractéristique contractuelle n'est inventée. Les obligations du
référentiel (TLT, SHY, LQD, HYG) sont des ETF sans coupon ni échéance uniques ;
pour elles, seules les statistiques de marché (cours réels) sont calculées, sauf
si une ligne bond_terms a été saisie avec sa provenance. Les calculs contractuels
(YTM, duration, convexité) portent sinon sur une obligation théorique dont
l'utilisateur saisit les caractéristiques.
"""

from datetime import date
from decimal import Decimal

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.actuarial.fixed_income.bond_pricing import flows_table, price, price_yield_curve
from app.actuarial.fixed_income.cashflows import Bond, cash_flows
from app.actuarial.fixed_income.convexity import convexity
from app.actuarial.fixed_income.curve_shocks import curve_scenarios, parallel_sensitivity
from app.actuarial.fixed_income.duration import dv01, macaulay_duration, modified_duration
from app.actuarial.fixed_income.yield_to_maturity import yield_to_maturity
from app.actuarial.models import BondTerms
from app.actuarial.risk.risk_metrics import annualized_return, annualized_volatility, max_drawdown
from app.actuarial.services.market_data_service import closes_by_asset
from app.models.models import Asset, AssetType, CouponPayment, Portfolio, Position, User


class BondNotFoundError(LookupError):
    pass


def analyze(
    bond: Bond,
    settlement: date,
    clean_price: float | None = None,
    ytm: float | None = None,
    curve_maturities: list[float] | None = None,
    curve_rates: list[float] | None = None,
    shock_bp: float = 100,
) -> dict:
    """Analyse complète à partir d'un prix (on en déduit le YTM) ou d'un rendement."""
    if (clean_price is None) == (ytm is None):
        raise ValueError("Indiquez soit un prix pied de coupon, soit un rendement actuariel")
    if ytm is None:
        ytm = yield_to_maturity(bond, settlement, clean_price)
    flows = cash_flows(bond, settlement)
    prices = price(bond, settlement, ytm)
    f = bond.frequency
    mod = modified_duration(flows, ytm, f)
    conv = convexity(flows, ytm, f)

    if curve_maturities:
        if len(curve_maturities) != len(curve_rates or []):
            raise ValueError("La courbe doit avoir autant de taux que de maturités")
        order = np.argsort(curve_maturities)
        mats = np.asarray(curve_maturities, dtype=float)[order]
        rates = np.asarray(curve_rates, dtype=float)[order]
        curve_source = "user_assumption"

        def curve(t):
            return np.interp(t, mats, rates)
    else:
        curve_source = "flat_at_ytm"

        def curve(t):
            return np.full_like(np.asarray(t, dtype=float), ytm)

    return {
        "settlement": settlement,
        "ytm": ytm,
        "clean_price": prices["clean"],
        "dirty_price": prices["dirty"],
        "accrued_interest": prices["accrued"],
        "macaulay_duration": macaulay_duration(flows, ytm, f),
        "modified_duration": mod,
        "convexity": conv,
        "dv01": dv01(flows, ytm, f, prices["dirty"]),
        "cash_flows": flows_table(flows, ytm, f),
        "price_yield_curve": price_yield_curve(flows, f, ytm),
        "parallel_sensitivity": parallel_sensitivity(flows, ytm, f, mod, conv),
        "curve_scenarios": curve_scenarios(flows, f, curve, shock_bp),
        "curve_source": curve_source,
        "shock_bp": shock_bp,
    }


def bond_from_terms(terms: BondTerms) -> Bond:
    return Bond(
        face_value=float(terms.face_value),
        coupon_rate=float(terms.coupon_rate),
        frequency=terms.coupon_frequency,
        maturity=terms.maturity_date,
        issue=terms.issue_date,
        day_count=terms.day_count,
    )


def terms_out(terms: BondTerms | None) -> dict | None:
    if terms is None:
        return None
    return {
        "face_value": float(terms.face_value),
        "coupon_rate": float(terms.coupon_rate),
        "coupon_frequency": terms.coupon_frequency,
        "issue_date": terms.issue_date,
        "maturity_date": terms.maturity_date,
        "day_count": terms.day_count,
        "source": terms.source,
    }


def _market_stats(series: list[tuple[date, float]]) -> dict | None:
    if len(series) < 3:
        return None
    closes = np.array([c for _, c in series])
    returns = closes[1:] / closes[:-1] - 1
    return {
        "last_price": float(closes[-1]),
        "last_date": series[-1][0],
        "observations": len(series),
        "annualized_return": annualized_return(returns),
        "annualized_volatility": annualized_volatility(returns.tolist()),
        "max_drawdown": max_drawdown(returns.tolist()),
    }


def _user_coupons(db: Session, user: User, asset_id: int) -> dict:
    """Coupons enregistrés dans coupon_payments pour les positions de l'utilisateur sur cet actif."""
    count, total = db.execute(
        select(func.count(CouponPayment.id), func.coalesce(func.sum(CouponPayment.amount), 0))
        .join(Position, CouponPayment.position_id == Position.id)
        .join(Portfolio, CouponPayment.portfolio_id == Portfolio.id)
        .where(Portfolio.user_id == user.id, Position.asset_id == asset_id)
    ).one()
    return {"count": int(count), "total": float(Decimal(total))}


def list_bonds(db: Session, user: User) -> list[dict]:
    bonds = db.scalars(select(Asset).where(Asset.asset_type == AssetType.BOND).order_by(Asset.symbol)).all()
    closes = closes_by_asset(db, [b.id for b in bonds])
    terms = {t.asset_id: t for t in db.scalars(select(BondTerms))}
    return [
        {
            "asset_id": bond.id,
            "symbol": bond.symbol,
            "name": bond.name,
            "has_terms": bond.id in terms,
            "market": _market_stats(closes.get(bond.id, [])),
            "coupons": _user_coupons(db, user, bond.id),
        }
        for bond in bonds
    ]


def bond_detail(db: Session, user: User, asset_id: int, settlement: date) -> dict:
    asset = db.get(Asset, asset_id)
    if asset is None or asset.asset_type != AssetType.BOND:
        raise BondNotFoundError("Obligation introuvable")
    series = closes_by_asset(db, [asset.id]).get(asset.id, [])
    terms = db.scalar(select(BondTerms).where(BondTerms.asset_id == asset.id))
    market = _market_stats(series)
    result = {
        "asset_id": asset.id,
        "symbol": asset.symbol,
        "name": asset.name,
        "market": market,
        "coupons": _user_coupons(db, user, asset.id),
        "terms": terms_out(terms),
        "analysis": None,
        "message": None,
    }
    if terms is None:
        result["message"] = (
            "Caractéristiques contractuelles non disponibles (coupon, échéance, nominal) : "
            "seules les statistiques de marché sont calculées. Utilisez une obligation théorique "
            "pour les calculs de rendement actuariel, de duration et de convexité."
        )
    elif market is None:
        result["message"] = "Aucun cours enregistré : prix de marché indisponible pour l'analyse."
    else:
        # Hypothèse : le dernier cours est un prix pied de coupon dans la même unité que le nominal.
        result["analysis"] = analyze(bond_from_terms(terms), settlement, clean_price=market["last_price"])
    return result


def upsert_terms(db: Session, asset_id: int, values: dict) -> BondTerms:
    asset = db.get(Asset, asset_id)
    if asset is None or asset.asset_type != AssetType.BOND:
        raise BondNotFoundError("Obligation introuvable")
    Bond(
        face_value=values["face_value"], coupon_rate=values["coupon_rate"], frequency=values["coupon_frequency"],
        maturity=values["maturity_date"], issue=values.get("issue_date"), day_count=values["day_count"],
    )  # contrôles de cohérence
    terms = db.scalar(select(BondTerms).where(BondTerms.asset_id == asset_id)) or BondTerms(asset_id=asset_id)
    for key, value in values.items():
        setattr(terms, key, value)
    db.add(terms)
    db.commit()
    return terms
