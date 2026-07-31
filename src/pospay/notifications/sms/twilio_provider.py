# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from pospay.config import get_settings


class TwilioSmsProvider:
    """The only real SMS provider for v1. Requires `pip install pospay[sms]` (the
    `twilio` package) -- imported lazily here, not at module load time, so a deployment
    that never enables SMS never needs it installed, same lazy-optional-dependency shape
    as ocr/textract_provider.py's boto3 import."""

    name = "twilio"

    def __init__(self) -> None:
        try:
            from twilio.rest import Client
        except ImportError as exc:
            raise RuntimeError("twilio SMS provider requires the 'sms' extra: pip install pospay[sms]") from exc

        settings = get_settings()
        if not settings.twilio_account_sid or not settings.twilio_auth_token or not settings.twilio_from_number:
            raise RuntimeError(
                "POSPAY_TWILIO_ACCOUNT_SID, POSPAY_TWILIO_AUTH_TOKEN, and POSPAY_TWILIO_FROM_NUMBER "
                "must all be configured to send SMS"
            )
        self._client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        self._from_number = settings.twilio_from_number

    def send(self, *, to: str, body: str) -> None:
        self._client.messages.create(to=to, from_=self._from_number, body=body)
