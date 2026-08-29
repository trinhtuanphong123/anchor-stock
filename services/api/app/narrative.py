"""app.narrative — the rule-based narrative for GET /api/tickers/{t}/analysis (P9.4, D-18).

Pure functions: no I/O, no FastAPI, no database access. Input is one ticker's latest indicator
row, already unpacked to plain floats/ints/None by the caller (see app.routes.tickers). Output
is a fixed-order list of descriptive statements plus a list of rules that had nothing to say.

**Never advisory.** ``docs/02`` §4 is explicit that a run produces no probabilistic statement and
no portfolio weights. Every rule states a fact about a stored number ("giá đang dưới MA20") --
never a recommendation ("nên mua/bán"), never a target, never a probability. Where a rule leans
on a market convention rather than a fact this system computed (RSI's 70/30 bands), the wording
names it as a convention, not as a property of the stock.

**A rule whose required inputs are NULL emits nothing.** A 200-day average has no value on bar
37 (P7's own warm-up rule), and a sentence generated from a NULL would be the most convincing
possible lie this narrative could tell. The rule is recorded as skipped, with which inputs were
missing, so silence is never mistaken for neutrality.

**Deterministic.** RULES is a fixed list, always walked in the same order, so the same input row
always yields the same narrative in the same sequence -- the same rule greedy follows when it
breaks ties by smallest index.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

Row = dict[str, Any]
RuleFn = Callable[[Row], str]


def _price_vs_ma(ma_key: str, ma_label: str) -> RuleFn:
    def rule(row: Row) -> str:
        close, ma = row["close"], row[ma_key]
        if close > ma:
            return (
                f"Giá đóng cửa ({close:.2f}) đang cao hơn "
                f"đường trung bình {ma_label} ({ma:.2f})."
            )
        if close < ma:
            return (
                f"Giá đóng cửa ({close:.2f}) đang thấp hơn "
                f"đường trung bình {ma_label} ({ma:.2f})."
            )
        return f"Giá đóng cửa đang bằng đường trung bình {ma_label} ({ma:.2f})."

    return rule


def _ma_alignment(row: Row) -> str:
    s20, s50, s200 = row["sma_20"], row["sma_50"], row["sma_200"]
    if s20 > s50 > s200:
        return (
            "Các đường trung bình xếp theo thứ tự MA20 > MA50 > MA200, "
            "thường được đọc là xu hướng tăng."
        )
    if s20 < s50 < s200:
        return (
            "Các đường trung bình xếp theo thứ tự MA20 < MA50 < MA200, "
            "thường được đọc là xu hướng giảm."
        )
    return "Các đường trung bình không xếp theo một thứ tự tăng hoặc giảm rõ rệt."


def _rsi_band(row: Row) -> str:
    rsi = row["rsi_14"]
    if rsi >= 70:
        return (
            f"RSI(14) đang ở mức {rsi:.1f}, trên ngưỡng 70 thông dụng "
            "(vùng quá mua theo quy ước)."
        )
    if rsi <= 30:
        return (
            f"RSI(14) đang ở mức {rsi:.1f}, dưới ngưỡng 30 thông dụng "
            "(vùng quá bán theo quy ước)."
        )
    if rsi >= 50:
        return f"RSI(14) đang ở mức {rsi:.1f}, trên mốc trung tính 50."
    return f"RSI(14) đang ở mức {rsi:.1f}, dưới mốc trung tính 50."


def _macd_momentum(row: Row) -> str:
    hist = row["macd_hist"]
    if hist > 0:
        return f"Biểu đồ MACD dương ({hist:.3f}), cho thấy động lượng tăng theo chỉ báo này."
    if hist < 0:
        return f"Biểu đồ MACD âm ({hist:.3f}), cho thấy động lượng giảm theo chỉ báo này."
    return "Biểu đồ MACD bằng 0, không cho thấy động lượng rõ rệt theo chỉ báo này."


def _bollinger_position(row: Row) -> str:
    close = row["close"]
    upper, lower, mid = row["bb_upper_20"], row["bb_lower_20"], row["bb_mid_20"]
    if close >= upper:
        return f"Giá đang ở tại hoặc trên dải Bollinger trên ({upper:.2f})."
    if close <= lower:
        return f"Giá đang ở tại hoặc dưới dải Bollinger dưới ({lower:.2f})."
    if close >= mid:
        return (
            "Giá đang nằm giữa đường giữa và dải trên của Bollinger Band "
            f"({mid:.2f} - {upper:.2f})."
        )
    return (
        "Giá đang nằm giữa dải dưới và đường giữa của Bollinger Band "
        f"({lower:.2f} - {mid:.2f})."
    )


def _volume_vs_average(row: Row) -> str:
    vol, avg = row["volume"], row["volume_sma_20"]
    if vol > avg:
        return (
            f"Khối lượng giao dịch phiên gần nhất ({vol:,}) cao hơn "
            f"trung bình 20 phiên ({avg:,.0f})."
        )
    if vol < avg:
        return (
            f"Khối lượng giao dịch phiên gần nhất ({vol:,}) thấp hơn "
            f"trung bình 20 phiên ({avg:,.0f})."
        )
    return f"Khối lượng giao dịch phiên gần nhất bằng trung bình 20 phiên ({avg:,.0f})."


def _range_position(row: Row) -> str:
    drawdown = row["drawdown_from_252d_high"]
    if drawdown >= -0.0001:
        return "Giá hiện đang ở gần mức cao nhất trong 252 phiên gần nhất."
    return (
        f"Giá hiện thấp hơn khoảng {abs(drawdown) * 100:.1f}% so với mức cao nhất "
        "trong 252 phiên gần nhất."
    )


def _trailing_return(key: str, period: str) -> RuleFn:
    """Return-over-a-window sentence.

    ``period`` is a COMPLETE adverbial phrase, preposition included -- "trong 5 phien gan nhat",
    "tu dau nam (YTD)". It used to be a bare noun phrase with "trong " prepended here, which read
    correctly for the three session windows and produced "trong tu dau nam (YTD)" for the
    year-to-date rule: one malformed sentence out of the thirteen on every ticker page. Carrying
    the preposition in the label is what stops the next window from having the same argument.

    A return of exactly zero drops the percentage rather than asserting "khong doi 0.00%", which
    states the same fact twice and reads as a measurement error.
    """

    def rule(row: Row) -> str:
        r = row[key]
        if r == 0:
            return f"Giá không đổi {period}."
        direction = "tăng" if r > 0 else "giảm"
        return f"Giá {direction} {abs(r) * 100:.2f}% {period}."

    return rule


# Fixed order. Each entry: (code, required input keys, rule function). A rule missing any
# required key is skipped rather than run on a guessed or zero-filled value.
RULES: list[tuple[str, tuple[str, ...], RuleFn]] = [
    ("price_vs_sma_20", ("close", "sma_20"), _price_vs_ma("sma_20", "20 phiên (MA20)")),
    ("price_vs_sma_50", ("close", "sma_50"), _price_vs_ma("sma_50", "50 phiên (MA50)")),
    ("price_vs_sma_200", ("close", "sma_200"), _price_vs_ma("sma_200", "200 phiên (MA200)")),
    ("ma_alignment", ("sma_20", "sma_50", "sma_200"), _ma_alignment),
    ("rsi_band", ("rsi_14",), _rsi_band),
    ("macd_momentum", ("macd_hist",), _macd_momentum),
    (
        "bollinger_position",
        ("close", "bb_upper_20", "bb_lower_20", "bb_mid_20"),
        _bollinger_position,
    ),
    ("volume_vs_average", ("volume", "volume_sma_20"), _volume_vs_average),
    ("range_position", ("drawdown_from_252d_high",), _range_position),
    ("ret_5d", ("ret_5d",), _trailing_return("ret_5d", "trong 5 phiên gần nhất")),
    ("ret_20d", ("ret_20d",), _trailing_return("ret_20d", "trong 20 phiên gần nhất")),
    ("ret_60d", ("ret_60d",), _trailing_return("ret_60d", "trong 60 phiên gần nhất")),
    ("ret_ytd", ("ret_ytd",), _trailing_return("ret_ytd", "từ đầu năm (YTD)")),
]


def _missing_keys(row: Row, keys: tuple[str, ...]) -> list[str]:
    return [k for k in keys if row.get(k) is None]


def build_narrative(row: Row) -> dict[str, Any]:
    """Walk RULES in order against one indicator row; never raises.

    Returns ``{"statements": [...], "skipped": [...]}``. A row with every input NULL (a ticker
    with no indicators computed yet) is a legitimate input, not an error case -- it simply
    produces an empty statement list and a fully populated skipped list.
    """
    statements: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for code, required, rule in RULES:
        missing = _missing_keys(row, required)
        if missing:
            skipped.append({"code": code, "reason": "missing_inputs", "missing": missing})
            continue
        statements.append(
            {
                "code": code,
                "text": rule(row),
                "inputs": {k: row[k] for k in required},
            }
        )

    return {"statements": statements, "skipped": skipped}
