"""Échéancier des flux d'une obligation à taux fixe."""

import calendar
from dataclasses import dataclass
from datetime import date

FREQUENCIES = (1, 2, 4, 12)
DAY_COUNTS = ("ACT/365", "ACT/360", "30/360")


@dataclass(frozen=True)
class Bond:
    face_value: float
    coupon_rate: float  # 0.045 pour 4,5 % par an
    frequency: int  # coupons par an
    maturity: date
    issue: date | None = None
    day_count: str = "ACT/365"

    def __post_init__(self):
        if self.face_value <= 0:
            raise ValueError("La valeur nominale doit être strictement positive")
        if not 0 <= self.coupon_rate <= 1:
            raise ValueError("Le taux de coupon doit être entre 0 et 100 %")
        if self.frequency not in FREQUENCIES:
            raise ValueError(f"La fréquence doit valoir {', '.join(map(str, FREQUENCIES))}")
        if self.day_count not in DAY_COUNTS:
            raise ValueError(f"Base de calcul inconnue : {self.day_count}")
        if self.issue and self.issue >= self.maturity:
            raise ValueError("La date d'émission doit précéder l'échéance")

    @property
    def coupon(self) -> float:
        return self.face_value * self.coupon_rate / self.frequency


@dataclass(frozen=True)
class CashFlow:
    date: date
    time: float  # années depuis le règlement
    coupon: float
    principal: float

    @property
    def amount(self) -> float:
        return self.coupon + self.principal


def add_months(day: date, months: int) -> date:
    """Décale de `months` mois en gardant le jour, borné au dernier jour du mois."""
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def year_fraction(start: date, end: date, day_count: str) -> float:
    if day_count == "ACT/360":
        return (end - start).days / 360
    if day_count == "30/360":
        d1, d2 = min(start.day, 30), end.day
        if d1 == 30 and d2 == 31:
            d2 = 30
        return ((end.year - start.year) * 360 + (end.month - start.month) * 30 + d2 - d1) / 360
    return (end - start).days / 365


def coupon_schedule(bond: Bond, settlement: date) -> tuple[date, list[date]]:
    """(date du coupon précédent, dates des coupons restants), en reculant depuis l'échéance."""
    if settlement >= bond.maturity:
        raise ValueError("La date de règlement doit précéder l'échéance")
    if bond.issue and settlement < bond.issue:
        raise ValueError("La date de règlement précède la date d'émission")
    step = 12 // bond.frequency
    dates = [bond.maturity]
    k = 1
    while True:
        previous = add_months(bond.maturity, -step * k)
        if previous <= settlement:
            break
        dates.append(previous)
        k += 1
    if bond.issue and previous < bond.issue:
        previous = bond.issue  # premier coupon couru depuis l'émission
    return previous, sorted(dates)


def cash_flows(bond: Bond, settlement: date) -> list[CashFlow]:
    _, dates = coupon_schedule(bond, settlement)
    return [
        CashFlow(
            date=day,
            time=year_fraction(settlement, day, bond.day_count),
            coupon=bond.coupon,
            principal=bond.face_value if day == bond.maturity else 0.0,
        )
        for day in dates
    ]


def accrued_interest(bond: Bond, settlement: date) -> float:
    """Coupon couru = coupon x jours écoulés / jours de la période en cours."""
    previous, dates = coupon_schedule(bond, settlement)
    period = (dates[0] - previous).days
    return bond.coupon * (settlement - previous).days / period if period else 0.0
