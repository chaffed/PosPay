# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from decimal import Decimal

from pospay.web.templates import _currency, _format_metrics


def test_currency_formats_decimal():
    assert _currency(Decimal("1234.5")) == "$1,234.50"
    assert _currency(Decimal("0")) == "$0.00"


def test_currency_passes_none_through():
    assert _currency(None) is None


def test_format_metrics_renders_precision_recall_as_percent():
    result = _format_metrics({"precision": 0.5, "recall": 1.0, "auc": 0.75})
    assert result == "Precision: 50%, Recall: 100%, AUC: 0.75"


def test_format_metrics_handles_error_shape():
    result = _format_metrics({"error": "insufficient training data"})
    assert result == "Error: insufficient training data"


def test_format_metrics_handles_empty_or_none():
    assert _format_metrics(None) == "—"
    assert _format_metrics({}) == "—"
