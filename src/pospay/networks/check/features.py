# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pospay.domain.check_image import CheckImage, OcrStatus
from pospay.domain.exception_item import ExceptionItem
from pospay.domain.issued_item import IssuedItem
from pospay.domain.paid_item import PaidItem
from pospay.networks.check.rules import normalize_payee
from rapidfuzz import fuzz


def build_check_features(session: Session, exception_item: ExceptionItem) -> dict[str, Any]:
    """Feature vector for the check ML model (see ml/ in the architecture plan). The core
    per-item and OCR-derived fields are built here. Historical/statistical features
    (issuer_exception_rate_30d, amount_zscore_vs_issuer_history, check_number_gap) are
    added alongside the Phase 5 training pipeline, which is the first consumer that needs
    the aggregate-query pattern they require."""
    paid_item = session.get(PaidItem, exception_item.source_item_id)
    issued_item = (
        session.get(IssuedItem, exception_item.related_reference_id) if exception_item.related_reference_id else None
    )
    check_image = session.execute(
        select(CheckImage).where(CheckImage.paid_item_id == paid_item.id, CheckImage.ocr_status == OcrStatus.COMPLETED)
    ).scalars().first()

    exception_types = exception_item.exception_types.split(",") if exception_item.exception_types else []

    if issued_item is not None:
        amount_delta_abs = abs(float(paid_item.presented_amount) - float(issued_item.amount))
        amount_delta_pct = amount_delta_abs / float(issued_item.amount) if issued_item.amount else 0.0
        days_since_issue = (paid_item.presented_date - issued_item.issue_date).days
    else:
        amount_delta_abs = 0.0
        amount_delta_pct = 0.0
        days_since_issue = 0

    if issued_item is not None and check_image is not None and check_image.ocr_extracted_payee:
        payee_similarity_score = float(
            fuzz.token_set_ratio(
                normalize_payee(check_image.ocr_extracted_payee), normalize_payee(issued_item.payee_name)
            )
        )
    else:
        payee_similarity_score = 0.0

    return {
        "tenant_id": str(exception_item.tenant_id),
        "amount_delta_abs": amount_delta_abs,
        "amount_delta_pct": amount_delta_pct,
        "days_since_issue": days_since_issue,
        "payee_similarity_score": payee_similarity_score,
        "ocr_confidence": float(check_image.ocr_confidence) if check_image and check_image.ocr_confidence else 0.0,
        "is_duplicate_paid": "duplicate_paid" in exception_types,
        "is_stopped": "stopped" in exception_types,
        "is_not_in_file": "not_in_file" in exception_types,
        "is_voided": "voided" in exception_types,
    }
