"""Tests du gain réalisé : (prix de vente - prix moyen d'achat) x quantité."""
from datetime import date, timedelta
from decimal import Decimal

from app.models.models import PriceHistory, TransactionSide
from app.services.trading import place_order


def set_price(db, asset, close, days_ahead):
    """Ajoute un cours plus récent : get_current_price lit le dernier connu."""
    value = Decimal(str(close))
    db.add(
        PriceHistory(
            asset_id=asset.id,
            date=date.today() + timedelta(days=days_ahead),
            open=value, high=value, low=value, close=value, volume=1000,
        )
    )
    db.flush()


class TestRealizedPnl:
    def test_buy_has_no_realized_pnl(self, db, seed_data):
        """Un achat ne réalise rien : la colonne reste vide."""
        tx = place_order(
            db, seed_data["portfolio"].id, "AAPL", TransactionSide.BUY, Decimal("10")
        )
        assert tx.realized_pnl is None

    def test_sell_at_same_price_is_zero(self, db, seed_data):
        """Vente au prix d'achat : ni gain ni perte."""
        pid = seed_data["portfolio"].id
        place_order(db, pid, "AAPL", TransactionSide.BUY, Decimal("10"))
        tx = place_order(db, pid, "AAPL", TransactionSide.SELL, Decimal("4"))
        assert tx.realized_pnl == Decimal("0.00")

    def test_sell_with_gain(self, db, seed_data):
        """Acheté 172, vendu 180 : (180 - 172) x 4 = 32."""
        pid = seed_data["portfolio"].id
        place_order(db, pid, "AAPL", TransactionSide.BUY, Decimal("10"))
        set_price(db, seed_data["aapl"], "180", 1)
        tx = place_order(db, pid, "AAPL", TransactionSide.SELL, Decimal("4"))
        assert tx.realized_pnl == Decimal("32.00")

    def test_sell_with_loss(self, db, seed_data):
        """Acheté 172, vendu 160 : (160 - 172) x 5 = -60."""
        pid = seed_data["portfolio"].id
        place_order(db, pid, "AAPL", TransactionSide.BUY, Decimal("10"))
        set_price(db, seed_data["aapl"], "160", 1)
        tx = place_order(db, pid, "AAPL", TransactionSide.SELL, Decimal("5"))
        assert tx.realized_pnl == Decimal("-60.00")

    def test_uses_average_buy_price(self, db, seed_data):
        """10 à 172 puis 10 à 182 : prix moyen 177. Vendu 187 : (187 - 177) x 5 = 50."""
        pid = seed_data["portfolio"].id
        place_order(db, pid, "AAPL", TransactionSide.BUY, Decimal("10"))
        set_price(db, seed_data["aapl"], "182", 1)
        place_order(db, pid, "AAPL", TransactionSide.BUY, Decimal("10"))
        set_price(db, seed_data["aapl"], "187", 2)
        tx = place_order(db, pid, "AAPL", TransactionSide.SELL, Decimal("5"))
        assert tx.realized_pnl == Decimal("50.00")
