"""Shared number, money and count formatters.

Audit finding P1-07: the same rupee amount appeared as `₹765000.00`,
`INR 45000.00`, `480000` and `₹7.2L` on four screens, because each template
reached for `'%.2f'|format(...)` on its own. Alerts said "1 records".

Every user-facing number now goes through a filter registered here, so a
change of convention happens once. Raw values stay raw in exports, the API
and the audit payload -- those are machine surfaces and a grouped string
would be a regression there.

Two conventions, chosen once:

* **Indian digit grouping.** `765000` renders `7,65,000`: the last three
  digits, then pairs. Western grouping on an Indian campus reads as a
  different number entirely.
* **Trailing `.00` is noise.** A whole rupee amount renders without paise;
  a fractional one keeps exactly two. A ledger column that must stay
  decimal-aligned asks for it with `paise=True`.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

RUPEE = "₹"

#: What an absent number renders as. One em dash everywhere, so "no value"
#: never reads as a different state on a different screen.
BLANK = "—"


def _decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def indian_group(digits: str) -> str:
    """Group an unsigned integer string the Indian way: `7,65,000`."""
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    pairs = []
    while len(head) > 2:
        pairs.insert(0, head[-2:])
        head = head[:-2]
    if head:
        pairs.insert(0, head)
    return ",".join(pairs + [tail])


def number(value, *, places: int | None = None) -> str:
    """A grouped number with no currency mark.

    ``places=None`` keeps two decimals only when the value has them.
    """
    amount = _decimal(value)
    if amount is None:
        return BLANK
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    if places is None:
        places = 0 if amount == amount.to_integral_value() else 2
    quantised = amount.quantize(Decimal(1) if places == 0 else Decimal("1." + "0" * places))
    whole, _, fraction = str(quantised).partition(".")
    grouped = indian_group(whole)
    return f"{sign}{grouped}.{fraction}" if fraction else f"{sign}{grouped}"


def money(value, *, currency: str = "INR", paise: bool = False) -> str:
    """`₹7,65,000`, or `₹7,65,000.50` when the amount has paise.

    A currency other than INR keeps its ISO code in front rather than
    borrowing the rupee sign, because the budget table does store one.
    """
    amount = _decimal(value)
    if amount is None:
        return BLANK
    rendered = number(amount, places=2 if paise else None)
    if (currency or "INR").upper() == "INR":
        return f"{RUPEE}{rendered}"
    return f"{currency.upper()} {rendered}"


def short_money(value, *, currency: str = "INR") -> str:
    """Compact Indian money for a KPI foot: `₹7.2L`, `₹45K`, `₹900`.

    Only for a figure that sits beside its exact counterpart or opens one.
    A number nobody can reconcile is worse than a long number.
    """
    amount = _decimal(value)
    if amount is None:
        return BLANK
    mark = RUPEE if (currency or "INR").upper() == "INR" else f"{currency.upper()} "
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    if amount >= Decimal(10000000):
        return f"{sign}{mark}{amount / Decimal(10000000):.1f}Cr"
    if amount >= Decimal(100000):
        return f"{sign}{mark}{amount / Decimal(100000):.1f}L"
    if amount >= Decimal(1000):
        return f"{sign}{mark}{amount / Decimal(1000):.0f}K"
    return f"{sign}{mark}{number(amount, places=0)}"


def percent(part, whole, *, places: int = 0) -> str:
    """`62%`, or an em dash when the denominator is zero.

    Returning `0%` for "nothing to measure" is the same lie the budget KPI
    used to tell when a project had no estimate at all.
    """
    numerator, denominator = _decimal(part), _decimal(whole)
    if numerator is None or not denominator:
        return BLANK
    return f"{numerator * 100 / denominator:.{places}f}%"


def pluralise(count, singular: str, plural: str | None = None) -> str:
    """`1 record` / `2 records`. Fixes the "1 records" in the alert header."""
    try:
        count = int(count)
    except (TypeError, ValueError):
        count = 0
    word = singular if count == 1 else (plural or f"{singular}s")
    return f"{count} {word}"


def register_filters(app) -> None:
    app.jinja_env.filters["money"] = money
    app.jinja_env.filters["money_exact"] = lambda value, currency="INR": money(value, currency=currency, paise=True)
    app.jinja_env.filters["short_money"] = short_money
    app.jinja_env.filters["number"] = number
    app.jinja_env.filters["pluralise"] = pluralise
    app.jinja_env.globals["percent"] = percent
    app.jinja_env.globals["BLANK"] = BLANK
