# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from pospay.domain.decision import DecisionOutcome


class RecommendRequest(BaseModel):
    outcome: DecisionOutcome
    reason_code: str
    notes: str | None = None


class DecideRequest(BaseModel):
    outcome: DecisionOutcome
    reason_code: str
    notes: str | None = None


class DecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    exception_item_id: uuid.UUID
    outcome: DecisionOutcome
    reason_code: str
    notes: str | None
    submitted_by_user_id: uuid.UUID | None
    decided_by_user_id: uuid.UUID
    decided_at: datetime
