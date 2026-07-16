"""Paper (simulated) trading service.

Manages paper-trade accounts, order placement with immediate execution
at market price, position tracking, and P&L calculation.

Orders use *market-order semantics*: they fill immediately at the current
Binance price.  Limit orders are supported but also fill at market if the
limit price is better than or equal to the market price.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.data.providers.akshare_provider import AkshareProvider
from app.data.providers.binance_provider import BinanceProvider
from app.data.providers.yfinance_provider import YFinanceProvider
from app.models.etf import ETFInfo
from app.models.trading import PaperTradeAccount, PaperTradeOrder, PaperTradePosition

if TYPE_CHECKING:
    from app.data.providers.base import DataProvider


class PaperTradingError(Exception):
    """Raised when a paper-trade operation cannot be completed."""


# ---------------------------------------------------------------------------
# Auto-trade sizing (quant P0-8)
#
# Position sizing is now scaled by signal strength rather than a fixed
# allocation.  ``BASE_POSITION_PCT`` is the allocation used when the
# signal strength is at the maximum (100).  A weaker signal (e.g. 40/100)
# is allocated ``BASE * 40/100`` of equity, capped at
# ``MAX_POSITION_PCT``.
# ---------------------------------------------------------------------------
BASE_POSITION_PCT = Decimal("0.10")   # 10% baseline for a max-strength signal
MAX_POSITION_PCT = Decimal("0.25")    # hard cap regardless of strength
MIN_POSITION_PCT = Decimal("0.01")    # below this we skip the trade (rounding)


class PaperTradingService:
    """Simulated trading with market-aware provider selection.

    Provider mapping by instrument code suffix:
      - .SH / .SZ → A股 → AkshareProvider
      - .HK      → 港股 → (暂时不支持，返回错误)
      - .US      → 美股 → YFinanceProvider
      - 无后缀 / BTC / ETH → 加密 → BinanceProvider

    Usage::

        service = PaperTradingService(db)
        account = service.create_account("My Account", Decimal("10000"))
        order = service.place_order(account.id, "BTC.US", "BUY", Decimal("0.01"))
        pnl = service.get_pnl_summary(account.id)
    """

    def __init__(self, db: Session):
        self.db = db
        self._providers: dict[str, "DataProvider"] = {}

    def _get_provider_for_code(self, instrument_code: str) -> "DataProvider":
        """Select the appropriate provider based on instrument code suffix.

        Returns the provider instance for the given market. Raises
        PaperTradingError if no provider is available for the market.
        """
        # Determine market from code suffix
        if instrument_code.endswith(".SH") or instrument_code.endswith(".SZ"):
            market = "cn"
        elif instrument_code.endswith(".HK"):
            market = "hk"
        elif instrument_code.endswith(".US"):
            market = "us"
        else:
            # No suffix: assume crypto (BTC, ETH, etc.)
            market = "crypto"

        # Return cached provider if available
        if market in self._providers:
            return self._providers[market]

        # Create provider based on market
        if market == "cn":
            provider = AkshareProvider()
            # Health check warns but doesn't block - actual fetch errors are more informative
            if not provider.check_health():
                import logging
                logging.warning("AkshareProvider health check failed, but allowing use")
            self._providers[market] = provider
            return provider

        elif market == "hk":
            # 港股暂不支持，返回明确错误
            raise PaperTradingError("该市场暂无可用行情源: 港股")

        elif market == "us":
            provider = YFinanceProvider()
            if not provider.check_health():
                import logging
                logging.warning("YFinanceProvider health check failed, but allowing use")
            self._providers[market] = provider
            return provider

        elif market == "crypto":
            provider = BinanceProvider()
            # Health check warns but doesn't block - network issues may be transient
            if not provider.check_health():
                import logging
                logging.warning("BinanceProvider health check failed, but allowing use")
            self._providers[market] = provider
            return provider

        # Fallback (should not reach here)
        raise PaperTradingError(f"未知市场: {instrument_code}")

    def _get_provider(self, instrument_code: str) -> "DataProvider":
        """Get provider for a single instrument. Convenience method."""
        return self._get_provider_for_code(instrument_code)

    # ------------------------------------------------------------------
    # Account CRUD
    # ------------------------------------------------------------------

    def create_account(
        self, name: str, initial_balance: Decimal = Decimal("10000"), user_id: int | None = None
    ) -> PaperTradeAccount:
        """Create a new paper-trade account."""
        account = PaperTradeAccount(
            user_id=user_id,
            name=name,
            initial_balance=initial_balance,
            cash=initial_balance,
        )
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        return account

    def get_account(self, account_id: int, user_id: int | None = None) -> PaperTradeAccount | None:
        """Return a single account or None."""
        query = self.db.query(PaperTradeAccount).filter(
            PaperTradeAccount.id == account_id,
            PaperTradeAccount.status == "active",
        )
        if user_id:
            query = query.filter(PaperTradeAccount.user_id == user_id)
        return query.first()

    def get_accounts(self, user_id: int | None = None) -> list[PaperTradeAccount]:
        """Return all active accounts."""
        query = self.db.query(PaperTradeAccount).filter(
            PaperTradeAccount.status == "active"
        )
        if user_id:
            query = query.filter(PaperTradeAccount.user_id == user_id)
        return query.order_by(PaperTradeAccount.created_at.desc()).all()

    def archive_account(self, account_id: int, user_id: int | None = None) -> bool:
        """Soft-delete by setting status='archived'."""
        account = self.get_account(account_id, user_id)
        if not account:
            return False
        account.status = "archived"
        self.db.commit()
        return True

    # ------------------------------------------------------------------
    # Order placement
    # ------------------------------------------------------------------

    def place_order(
        self,
        account_id: int,
        instrument_code: str,
        order_type: str,  # BUY | SELL
        quantity: Decimal,
        price: Decimal | None = None,
        signal_id: int | None = None,
    ) -> PaperTradeOrder:
        """Place and immediately execute a simulated order.

        Returns the filled order.  Raises ``PaperTradingError`` when the
        order cannot be placed (insufficient funds, unknown instrument, etc.).

        If *price* is omitted the order fills at the current Binance last
        price (market order).  If a limit price is supplied the order only
        fills when the market price is at-or-better than the limit.
        """
        # 1. Validate account
        account = self.get_account(account_id)
        if not account:
            raise PaperTradingError(f"Account {account_id} not found or archived")

        # 2. Validate instrument
        instrument = (
            self.db.query(ETFInfo)
            .filter(ETFInfo.code == instrument_code)
            .first()
        )
        if not instrument:
            raise PaperTradingError(f"Instrument {instrument_code} not found")

        # 3. Get current market price (use market-specific provider)
        try:
            provider = self._get_provider(instrument_code)
            quotes_df = provider.fetch_realtime_quotes([instrument_code])
            if quotes_df.empty:
                raise PaperTradingError(f"No price data for {instrument_code}")
            market_price = Decimal(str(quotes_df.iloc[0]["price"]))
        except PaperTradingError:
            raise
        except Exception as exc:
            raise PaperTradingError(f"Failed to fetch price for {instrument_code}: {exc}") from exc

        if market_price <= 0:
            raise PaperTradingError(f"Invalid market price {market_price} for {instrument_code}")

        # 4. Check limit price
        if price is not None:
            if order_type == "BUY" and market_price > price:
                raise PaperTradingError(
                    f"Market price {market_price} > limit {price} — order would not fill"
                )
            if order_type == "SELL" and market_price < price:
                raise PaperTradingError(
                    f"Market price {market_price} < limit {price} — order would not fill"
                )
            execution_price = price if order_type == "BUY" else price
        else:
            execution_price = market_price

        # 5. Validate funds
        notional = execution_price * quantity
        if order_type == "BUY":
            if account.cash < notional:
                raise PaperTradingError(
                    f"Insufficient cash: need {notional}, have {account.cash}"
                )
        else:
            # SELL — check position
            position = self._get_or_create_position(account_id, instrument_code)
            if position.quantity < quantity:
                raise PaperTradingError(
                    f"Insufficient position: need {quantity}, have {position.quantity}"
                )

        # 6. Create the order record
        order = PaperTradeOrder(
            account_id=account_id,
            instrument_code=instrument_code,
            order_type=order_type,
            price=execution_price,
            quantity=quantity,
            filled_quantity=quantity,  # immediate fill
            status="filled",
            signal_id=signal_id,
            filled_at=datetime.now(timezone.utc),
        )
        order.instrument_name = instrument.name
        self.db.add(order)

        # 7. Update account cash
        if order_type == "BUY":
            account.cash -= notional
        else:
            account.cash += notional

        # 8. Update position (VWAP for BUY, reduce for SELL)
        position = self._get_or_create_position(account_id, instrument_code)
        if order_type == "BUY":
            if position.quantity == 0:
                position.avg_cost = execution_price
                position.quantity = quantity
            else:
                old_qty = position.quantity
                total_cost = old_qty * position.avg_cost + quantity * execution_price
                position.quantity = old_qty + quantity
                position.avg_cost = total_cost / position.quantity
        else:
            # SELL — reduce position, realise PnL
            realized = quantity * (execution_price - position.avg_cost)
            position.realized_pnl = (position.realized_pnl or 0) + realized
            position.quantity -= quantity
            if position.quantity <= 0:
                position.avg_cost = Decimal("0")
                position.quantity = Decimal("0")
                position.market_value = Decimal("0")
                position.unrealized_pnl = Decimal("0")

        # Mark to market (only for non-zero positions)
        if position.quantity > 0:
            position.market_value = position.quantity * execution_price
            position.unrealized_pnl = position.quantity * (execution_price - position.avg_cost)
        self.db.add(position)

        self.db.commit()
        self.db.refresh(order)
        return order

    def cancel_order(self, order_id: int) -> bool:
        """Cancel a pending paper-trade order."""
        order = self.db.query(PaperTradeOrder).filter(
            PaperTradeOrder.id == order_id,
            PaperTradeOrder.status == "pending",
        ).first()
        if not order:
            return False
        order.status = "cancelled"
        self.db.commit()
        return True

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    def get_positions(self, account_id: int) -> list[PaperTradePosition]:
        """Return positions with quantity > 0, enriched with instrument name."""
        positions = (
            self.db.query(PaperTradePosition)
            .filter(
                PaperTradePosition.account_id == account_id,
                PaperTradePosition.quantity > 0,
            )
            .all()
        )

        # Enrich with instrument names
        codes = [p.instrument_code for p in positions]
        instruments = {}
        if codes:
            rows = (
                self.db.query(ETFInfo.code, ETFInfo.name)
                .filter(ETFInfo.code.in_(codes))
                .all()
            )
            instruments = {r.code: r.name for r in rows}

        # Enrich with live prices (group by market for provider selection)
        quotes: dict[str, Decimal] = {}
        try:
            # Group codes by market
            market_codes: dict[str, list[str]] = {}
            for code in codes:
                if code.endswith(".SH") or code.endswith(".SZ"):
                    market = "cn"
                elif code.endswith(".HK"):
                    market = "hk"
                elif code.endswith(".US"):
                    market = "us"
                else:
                    market = "crypto"
                market_codes.setdefault(market, []).append(code)

            # Fetch quotes from each market's provider
            for market, market_code_list in market_codes.items():
                try:
                    provider = self._get_provider(market_code_list[0])
                    quotes_df = provider.fetch_realtime_quotes(market_code_list)
                    if not quotes_df.empty:
                        for _, row in quotes_df.iterrows():
                            quotes[row["etf_code"]] = Decimal(str(row["price"]))
                except PaperTradingError:
                    # Skip unavailable markets
                    continue
                except Exception:
                    continue
        except Exception:
            pass

        for pos in positions:
            pos.instrument_name = instruments.get(pos.instrument_code)
            current_price = quotes.get(pos.instrument_code)
            if current_price is not None:
                pos.current_price = current_price
                pos.market_value = pos.quantity * current_price
                if pos.quantity > 0:
                    pos.unrealized_pnl = pos.quantity * (current_price - pos.avg_cost)
                if pos.avg_cost > 0 and pos.quantity > 0:
                    pos.pnl_pct = ((current_price - pos.avg_cost) / pos.avg_cost) * 100

        return positions

    def get_orders(
        self, account_id: int, limit: int = 50
    ) -> list[PaperTradeOrder]:
        """Return recent orders for an account, newest first."""
        orders = (
            self.db.query(PaperTradeOrder)
            .filter(PaperTradeOrder.account_id == account_id)
            .order_by(PaperTradeOrder.created_at.desc())
            .limit(limit)
            .all()
        )

        # Enrich with instrument names
        codes = [o.instrument_code for o in orders]
        instruments = {}
        if codes:
            rows = (
                self.db.query(ETFInfo.code, ETFInfo.name)
                .filter(ETFInfo.code.in_(codes))
                .all()
            )
            instruments = {r.code: r.name for r in rows}

        for order in orders:
            order.instrument_name = instruments.get(order.instrument_code)

        return orders

    # ------------------------------------------------------------------
    # PnL
    # ------------------------------------------------------------------

    def get_pnl_summary(self, account_id: int) -> dict:
        """Return a P&L summary dict for the account."""
        account = self.get_account(account_id)
        if not account:
            raise PaperTradingError(f"Account {account_id} not found")

        # Aggregate positions in a single query.  We previously delegated
        # to ``update_market_values`` here, which issued its own
        # ``SELECT * FROM paper_trade_position`` plus a commit — a
        # textbook N+1 pattern (extra DB round-trip per call).  Instead,
        # we now fetch positions once and refresh market values inline
        # with a single batched Binance quote request.
        positions = (
            self.db.query(PaperTradePosition)
            .filter(PaperTradePosition.account_id == account_id)
            .all()
        )

        # Refresh market values inline: batched quote fetch per market, in-memory
        # update, single commit.  Failures are swallowed so a transient
        # provider outage doesn't break the summary endpoint.
        quotes: dict[str, Decimal] = {}
        try:
            open_codes = list({p.instrument_code for p in positions if p.quantity > 0})
            if open_codes:
                # Group codes by market
                market_codes: dict[str, list[str]] = {}
                for code in open_codes:
                    if code.endswith(".SH") or code.endswith(".SZ"):
                        market = "cn"
                    elif code.endswith(".HK"):
                        market = "hk"
                    elif code.endswith(".US"):
                        market = "us"
                    else:
                        market = "crypto"
                    market_codes.setdefault(market, []).append(code)

                # Fetch quotes from each market's provider
                for market, market_code_list in market_codes.items():
                    try:
                        provider = self._get_provider(market_code_list[0])
                        quotes_df = provider.fetch_realtime_quotes(market_code_list)
                        if not quotes_df.empty:
                            for _, row in quotes_df.iterrows():
                                quotes[row["etf_code"]] = Decimal(str(row["price"]))
                    except PaperTradingError:
                        continue
                    except Exception:
                        continue

                for pos in positions:
                    if pos.quantity <= 0:
                        continue
                    price = quotes.get(pos.instrument_code)
                    if price is None or price <= 0:
                        continue
                    pos.market_value = pos.quantity * price
                    pos.unrealized_pnl = pos.quantity * (price - pos.avg_cost)
                self.db.commit()
        except Exception:
            pass

        total_market_value = Decimal("0")
        total_unrealized = Decimal("0")
        total_realized = Decimal("0")
        for pos in positions:
            total_market_value += pos.market_value or 0
            total_unrealized += pos.unrealized_pnl or 0
            total_realized += pos.realized_pnl or 0

        total_pnl = total_unrealized + total_realized
        total_equity = account.cash + total_market_value
        pnl_pct = None
        if account.initial_balance > 0:
            pnl_pct = (total_pnl / account.initial_balance) * 100

        # Trade statistics
        orders = (
            self.db.query(PaperTradeOrder)
            .filter(
                PaperTradeOrder.account_id == account_id,
                PaperTradeOrder.status == "filled",
            )
            .order_by(PaperTradeOrder.created_at.asc())
            .all()
        )

        trade_count = len(orders)
        win_count = 0
        if trade_count > 0:
            # Per-SELL realised PnL via FIFO cost-basis matching against
            # prior BUY orders on the same instrument.  This correctly
            # attributes wins/losses to each closing trade, including
            # multiple round-trips on the same instrument.
            buy_lots: dict[str, list[dict]] = {}
            realised_pnls: list[Decimal] = []
            for o in orders:
                if o.order_type == "BUY":
                    buy_lots.setdefault(o.instrument_code, []).append({
                        "qty": Decimal(o.filled_quantity or 0),
                        "price": Decimal(o.price or 0),
                    })
                elif o.order_type == "SELL":
                    remaining = Decimal(o.filled_quantity or 0)
                    sell_price = Decimal(o.price or 0)
                    lots = buy_lots.get(o.instrument_code, [])
                    pnl = Decimal("0")
                    while remaining > 0 and lots:
                        lot = lots[0]
                        take = min(remaining, lot["qty"])
                        pnl += take * (sell_price - lot["price"])
                        lot["qty"] -= take
                        remaining -= take
                        if lot["qty"] <= 0:
                            lots.pop(0)
                    # If we sold more than held, treat unmatched quantity
                    # as a flat break-even so the win-rate count is not
                    # distorted by short positions.
                    realised_pnls.append(pnl)
            win_count = sum(1 for p in realised_pnls if p > 0)
            denom = max(1, len(realised_pnls))
            win_rate = Decimal(str(win_count)) / Decimal(str(denom))
        else:
            win_rate = None

        return {
            "account_id": account_id,
            "total_equity": total_equity,
            "cash": account.cash,
            "market_value": total_market_value,
            "unrealized_pnl": total_unrealized,
            "realized_pnl": total_realized,
            "total_pnl": total_pnl,
            "pnl_pct": pnl_pct,
            "trade_count": trade_count,
            "win_count": win_count,
            "win_rate": win_rate,
        }

    # ------------------------------------------------------------------
    # Market-value sync
    # ------------------------------------------------------------------

    def update_market_values(self, account_id: int | None = None) -> int:
        """Fetch latest prices from market-specific providers and update position market values.

        If *account_id* is None, all active accounts are updated.
        Returns the number of positions updated.
        """
        query = self.db.query(PaperTradePosition).filter(
            PaperTradePosition.quantity > 0
        )
        if account_id is not None:
            query = query.filter(PaperTradePosition.account_id == account_id)

        positions = query.all()
        if not positions:
            return 0

        codes = list({p.instrument_code for p in positions})

        # Group codes by market
        market_codes: dict[str, list[str]] = {}
        for code in codes:
            if code.endswith(".SH") or code.endswith(".SZ"):
                market = "cn"
            elif code.endswith(".HK"):
                market = "hk"
            elif code.endswith(".US"):
                market = "us"
            else:
                market = "crypto"
            market_codes.setdefault(market, []).append(code)

        quotes: dict[str, Decimal] = {}
        try:
            # Fetch quotes from each market's provider
            for market, market_code_list in market_codes.items():
                try:
                    provider = self._get_provider(market_code_list[0])
                    quotes_df = provider.fetch_realtime_quotes(market_code_list)
                    if not quotes_df.empty:
                        for _, row in quotes_df.iterrows():
                            quotes[row["etf_code"]] = Decimal(str(row["price"]))
                except PaperTradingError:
                    continue
                except Exception:
                    continue
        except Exception:
            return 0

        updated = 0
        for pos in positions:
            price = quotes.get(pos.instrument_code)
            if price is None or price <= 0:
                continue
            pos.market_value = pos.quantity * price
            if pos.quantity > 0:
                pos.unrealized_pnl = pos.quantity * (price - pos.avg_cost)
            updated += 1

        self.db.commit()
        return updated

    # ------------------------------------------------------------------
    # Auto-trade from signals
    # ------------------------------------------------------------------

    def auto_trade_from_signals(
        self,
        account_id: int,
        trade_date: date | None = None,
    ) -> list[PaperTradeOrder]:
        """Execute trades for all active BUY/SELL signals on the given date.

        Signals are looked up from the ``signal`` table.  Each BUY allocates
        a fixed percentage of available cash (default 10%).  Each SELL closes
        the full position.
        """
        from app.models.etl import Signal

        if trade_date is None:
            trade_date = date.today()

        signals = (
            self.db.query(Signal)
            .filter(Signal.trade_date == trade_date)
            .order_by(Signal.created_at.asc())
            .all()
        )

        orders: list[PaperTradeOrder] = []
        account = self.get_account(account_id)
        if not account:
            return orders

        for sig in signals:
            try:
                if sig.signal_type == "BUY":
                    # Scale position by signal strength (quant P0-8).
                    # sizing = BASE_POSITION_PCT * (abs(strength) / 100),
                    # capped at MAX_POSITION_PCT.  Strength defaults to
                    # 50 (HOLD-strength) so an unscaled signal still
                    # gets a meaningful allocation.
                    strength = abs(int(sig.strength or 50))
                    strength_ratio = Decimal(strength) / Decimal("100")
                    sizing_pct = BASE_POSITION_PCT * strength_ratio
                    if sizing_pct > MAX_POSITION_PCT:
                        sizing_pct = MAX_POSITION_PCT
                    if sizing_pct < MIN_POSITION_PCT:
                        # Below 1% — rounding/fees would dominate. Skip.
                        continue

                    positions = self.get_positions(account_id)
                    total_mv = sum((p.market_value or 0) for p in positions)
                    equity = account.cash + total_mv
                    allocation = equity * sizing_pct
                    market_price = self._get_current_price(sig.etf_code)
                    if market_price is None or market_price <= 0:
                        continue
                    quantity = allocation / market_price
                    # Round to reasonable precision (8 decimals for crypto)
                    quantity = quantity.quantize(Decimal("0.00000001"))
                    if quantity <= 0:
                        continue
                    order = self.place_order(
                        account_id, sig.etf_code, "BUY", quantity, signal_id=sig.id
                    )
                    orders.append(order)

                elif sig.signal_type == "SELL":
                    position = (
                        self.db.query(PaperTradePosition)
                        .filter(
                            PaperTradePosition.account_id == account_id,
                            PaperTradePosition.instrument_code == sig.etf_code,
                            PaperTradePosition.quantity > 0,
                        )
                        .first()
                    )
                    if position is None:
                        continue
                    order = self.place_order(
                        account_id,
                        sig.etf_code,
                        "SELL",
                        position.quantity,
                        signal_id=sig.id,
                    )
                    orders.append(order)
            except PaperTradingError:
                # Skip signals that can't be executed (e.g. insufficient funds)
                continue

        return orders

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_or_create_position(
        self, account_id: int, instrument_code: str
    ) -> PaperTradePosition:
        """Return existing position or create a new zero-position row."""
        position = (
            self.db.query(PaperTradePosition)
            .filter(
                PaperTradePosition.account_id == account_id,
                PaperTradePosition.instrument_code == instrument_code,
            )
            .first()
        )
        if position is None:
            position = PaperTradePosition(
                account_id=account_id,
                instrument_code=instrument_code,
                quantity=0,
                avg_cost=0,
            )
            self.db.add(position)
            self.db.flush()  # assign an id without committing
        return position

    def _get_current_price(self, instrument_code: str) -> Decimal | None:
        """Fetch the latest price for a single instrument using market-specific provider."""
        try:
            provider = self._get_provider(instrument_code)
            quotes_df = provider.fetch_realtime_quotes([instrument_code])
            if quotes_df.empty:
                return None
            return Decimal(str(quotes_df.iloc[0]["price"]))
        except PaperTradingError:
            return None
        except Exception:
            return None
