"""P9.4 — closed-form tests for app.narrative, the rule-based ticker analysis.

Pure-function tests: no ASGI harness, no FastAPI, no database -- app.narrative takes a dict and
returns a dict. What these assert, and why each one exists:

* Each rule's three (or more) branches produce the expected direction word, from a fixture
  chosen so the branch is unambiguous -- the same idiom P7's indicator selftest uses (closed-form
  fixtures, not a second implementation of the same logic).
* A rule with a missing required input is skipped, never run on a guessed value -- and the
  skipped entry names exactly which keys were missing.
* An all-NULL row produces zero statements and every rule skipped -- the single most likely way
  this endpoint could tell a convincing lie, since a sentence generated from NULL still reads as
  a fact.
* The same row, run twice, yields byte-identical output -- RULES is a fixed list walked in a
  fixed order.
* No statement's text contains advisory language ("nen mua", "nen ban", "khuyen nghi") -- docs/02
  §4 forbids it, and this is the closest a unit test can come to enforcing wording by machine.
"""

from __future__ import annotations

import unittest

from app.narrative import RULES, build_narrative

# One row with every rule's inputs present, values chosen so each branch below is unambiguous.
FULL_ROW = {
    "close": 24.95,
    "sma_20": 23.88,
    "sma_50": 22.12,
    "sma_200": 20.57,
    "rsi_14": 62.35,
    "macd_hist": 0.1544,
    "bb_upper_20": 25.2345,
    "bb_lower_20": 22.5185,
    "bb_mid_20": 23.8765,
    "volume": 3456789,
    "volume_sma_20": 2987654.5,
    "drawdown_from_252d_high": -0.136678,
    "ret_5d": 0.0523456,
    "ret_20d": -0.0100000,
    "ret_60d": 0.0300000,
    "ret_ytd": 0.3400000,
}

ALL_CODES = [code for code, _, _ in RULES]


class RuleSetShapeTests(unittest.TestCase):
    def test_thirteen_rules_in_a_fixed_order(self):
        self.assertEqual(len(RULES), 13)
        self.assertEqual(len(ALL_CODES), len(set(ALL_CODES)), "rule codes must be unique")

    def test_full_row_produces_a_statement_per_rule(self):
        result = build_narrative(FULL_ROW)
        self.assertEqual(len(result["statements"]), 13)
        self.assertEqual(result["skipped"], [])
        self.assertEqual([s["code"] for s in result["statements"]], ALL_CODES)

    def test_determinism_same_row_twice_is_byte_identical(self):
        first = build_narrative(dict(FULL_ROW))
        second = build_narrative(dict(FULL_ROW))
        self.assertEqual(first, second)

    def test_all_null_row_is_zero_statements_fully_skipped(self):
        empty_row = dict.fromkeys(FULL_ROW)
        result = build_narrative(empty_row)

        self.assertEqual(result["statements"], [])
        self.assertEqual(len(result["skipped"]), 13)
        for entry in result["skipped"]:
            self.assertEqual(entry["reason"], "missing_inputs")
            self.assertTrue(entry["missing"])

    def test_partial_row_skips_only_rules_missing_their_own_inputs(self):
        row = {"close": 24.95, "sma_20": 23.88}
        result = build_narrative(row)

        codes_with_statements = {s["code"] for s in result["statements"]}
        self.assertEqual(codes_with_statements, {"price_vs_sma_20"})

        skipped_by_code = {s["code"]: s["missing"] for s in result["skipped"]}
        self.assertIn("sma_50", skipped_by_code["price_vs_sma_50"])
        self.assertIn("rsi_14", skipped_by_code["rsi_band"])

    def test_no_statement_text_reads_as_advisory(self):
        result = build_narrative(FULL_ROW)
        banned = ("nên mua", "nên bán", "khuyến nghị", "mục tiêu giá", "xác suất")
        for statement in result["statements"]:
            lowered = statement["text"].lower()
            for phrase in banned:
                self.assertNotIn(phrase, lowered, statement["text"])

    def test_statement_carries_its_own_inputs(self):
        result = build_narrative(FULL_ROW)
        by_code = {s["code"]: s for s in result["statements"]}
        self.assertEqual(
            by_code["price_vs_sma_20"]["inputs"], {"close": 24.95, "sma_20": 23.88}
        )


class PriceVsSmaTests(unittest.TestCase):
    def _text(self, close, sma_20):
        row = dict(FULL_ROW, close=close, sma_20=sma_20)
        by_code = {s["code"]: s["text"] for s in build_narrative(row)["statements"]}
        return by_code["price_vs_sma_20"]

    def test_above(self):
        self.assertIn("cao hơn", self._text(25.0, 20.0))

    def test_below(self):
        self.assertIn("thấp hơn", self._text(15.0, 20.0))

    def test_equal(self):
        self.assertIn("bằng", self._text(20.0, 20.0))


class MaAlignmentTests(unittest.TestCase):
    def _text(self, s20, s50, s200):
        row = dict(FULL_ROW, sma_20=s20, sma_50=s50, sma_200=s200)
        by_code = {s["code"]: s["text"] for s in build_narrative(row)["statements"]}
        return by_code["ma_alignment"]

    def test_uptrend_order(self):
        self.assertIn("xu hướng tăng", self._text(30, 20, 10))

    def test_downtrend_order(self):
        self.assertIn("xu hướng giảm", self._text(10, 20, 30))

    def test_no_clear_order(self):
        text = self._text(20, 30, 10)
        self.assertNotIn("xu hướng tăng", text)
        self.assertNotIn("xu hướng giảm", text)


class RsiBandTests(unittest.TestCase):
    def _text(self, rsi):
        row = dict(FULL_ROW, rsi_14=rsi)
        by_code = {s["code"]: s["text"] for s in build_narrative(row)["statements"]}
        return by_code["rsi_band"]

    def test_overbought_names_the_convention(self):
        text = self._text(75.0)
        self.assertIn("quá mua", text)
        self.assertIn("quy ước", text)

    def test_oversold_names_the_convention(self):
        text = self._text(25.0)
        self.assertIn("quá bán", text)
        self.assertIn("quy ước", text)

    def test_above_midline(self):
        self.assertIn("trên mốc trung tính", self._text(55.0))

    def test_below_midline(self):
        self.assertIn("dưới mốc trung tính", self._text(45.0))


class MacdMomentumTests(unittest.TestCase):
    def _text(self, hist):
        row = dict(FULL_ROW, macd_hist=hist)
        by_code = {s["code"]: s["text"] for s in build_narrative(row)["statements"]}
        return by_code["macd_momentum"]

    def test_positive(self):
        self.assertIn("dương", self._text(0.5))

    def test_negative(self):
        self.assertIn("âm", self._text(-0.5))

    def test_zero(self):
        self.assertIn("bằng 0", self._text(0.0))


class BollingerPositionTests(unittest.TestCase):
    def _text(self, close):
        row = dict(FULL_ROW, close=close, bb_upper_20=25.0, bb_lower_20=20.0, bb_mid_20=22.5)
        by_code = {s["code"]: s["text"] for s in build_narrative(row)["statements"]}
        return by_code["bollinger_position"]

    def test_at_or_above_upper(self):
        self.assertIn("dải Bollinger trên", self._text(25.5))

    def test_at_or_below_lower(self):
        self.assertIn("dải Bollinger dưới", self._text(19.5))

    def test_between_mid_and_upper(self):
        self.assertIn("dải trên", self._text(23.5))

    def test_between_lower_and_mid(self):
        self.assertIn("đường giữa", self._text(21.0))


class VolumeVsAverageTests(unittest.TestCase):
    def _text(self, volume, average):
        row = dict(FULL_ROW, volume=volume, volume_sma_20=average)
        by_code = {s["code"]: s["text"] for s in build_narrative(row)["statements"]}
        return by_code["volume_vs_average"]

    def test_above_average(self):
        self.assertIn("cao hơn", self._text(2_000_000, 1_000_000))

    def test_below_average(self):
        self.assertIn("thấp hơn", self._text(500_000, 1_000_000))

    def test_equal_average(self):
        self.assertIn("bằng", self._text(1_000_000, 1_000_000))


class RangePositionTests(unittest.TestCase):
    def _text(self, drawdown):
        row = dict(FULL_ROW, drawdown_from_252d_high=drawdown)
        by_code = {s["code"]: s["text"] for s in build_narrative(row)["statements"]}
        return by_code["range_position"]

    def test_at_the_high(self):
        self.assertIn("gần mức cao nhất", self._text(0.0))

    def test_below_the_high_reports_the_percentage(self):
        text = self._text(-0.15)
        self.assertIn("15.0%", text)


class TrailingReturnTests(unittest.TestCase):
    def _text(self, code, key, value):
        row = dict(FULL_ROW, **{key: value})
        by_code = {s["code"]: s["text"] for s in build_narrative(row)["statements"]}
        return by_code[code]

    def test_positive_return_says_tang(self):
        self.assertIn("tăng", self._text("ret_5d", "ret_5d", 0.05))

    def test_negative_return_says_giam(self):
        self.assertIn("giảm", self._text("ret_20d", "ret_20d", -0.05))

    def test_zero_return_says_khong_doi(self):
        self.assertIn("không đổi", self._text("ret_ytd", "ret_ytd", 0.0))

    # The three above pass on a malformed sentence, because a substring check cannot see grammar.
    # These pin the whole sentence. The bug they would have caught was live on every ticker page:
    # "Giá tăng 17.92% trong từ đầu năm (YTD)."
    def test_session_window_sentences_read_correctly(self):
        self.assertEqual(
            self._text("ret_5d", "ret_5d", 0.05),
            "Giá tăng 5.00% trong 5 phiên gần nhất.",
        )
        self.assertEqual(
            self._text("ret_20d", "ret_20d", -0.0812),
            "Giá giảm 8.12% trong 20 phiên gần nhất.",
        )
        self.assertEqual(
            self._text("ret_60d", "ret_60d", 0.1234),
            "Giá tăng 12.34% trong 60 phiên gần nhất.",
        )

    def test_ytd_label_is_not_prefixed_with_trong(self):
        text = self._text("ret_ytd", "ret_ytd", 0.1792)
        self.assertEqual(text, "Giá tăng 17.92% từ đầu năm (YTD).")
        self.assertNotIn("trong từ đầu năm", text)

    def test_zero_return_drops_the_percentage(self):
        self.assertEqual(
            self._text("ret_5d", "ret_5d", 0.0),
            "Giá không đổi trong 5 phiên gần nhất.",
        )
        self.assertEqual(
            self._text("ret_ytd", "ret_ytd", 0.0),
            "Giá không đổi từ đầu năm (YTD).",
        )

    def test_no_statement_reads_trong_trong_or_trong_tu(self):
        """Guards the whole family, not just the one label that was wrong."""
        for statement in build_narrative(FULL_ROW)["statements"]:
            self.assertNotIn("trong trong", statement["text"])
            self.assertNotIn("trong từ", statement["text"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main(verbosity=2)
