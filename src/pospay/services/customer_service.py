# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from pospay.domain.customer import Customer
from pospay.repositories.customer_repo import CustomerRepository


@dataclass(frozen=True, slots=True)
class CustomerInput:
    customer_number: str
    name: str
    external_customer_id: str | None = None
    tax_id: str | None = None
    primary_contact_name: str | None = None
    email: str | None = None
    phone: str | None = None
    website: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    notes: str | None = None


def _apply_input(customer: Customer, data: CustomerInput) -> None:
    customer.customer_number = data.customer_number
    customer.name = data.name
    customer.external_customer_id = data.external_customer_id
    customer.tax_id = data.tax_id
    customer.primary_contact_name = data.primary_contact_name
    customer.email = data.email
    customer.phone = data.phone
    customer.website = data.website
    customer.address_line1 = data.address_line1
    customer.address_line2 = data.address_line2
    customer.city = data.city
    customer.state = data.state
    customer.postal_code = data.postal_code
    customer.notes = data.notes


def create_customer(session: Session, tenant_id: uuid.UUID, data: CustomerInput) -> Customer:
    repo = CustomerRepository(session, tenant_id)
    customer = Customer()
    _apply_input(customer, data)
    repo.add(customer)
    session.flush()
    return customer


def update_customer(session: Session, tenant_id: uuid.UUID, customer_id: uuid.UUID, data: CustomerInput) -> Customer | None:
    customer = CustomerRepository(session, tenant_id).get(customer_id)
    if customer is None:
        return None
    _apply_input(customer, data)
    session.flush()
    return customer


def list_customers(
    session: Session,
    tenant_id: uuid.UUID,
    *,
    limit: int | None = None,
    offset: int | None = None,
    order_by: Any = None,
) -> list[Customer]:
    return CustomerRepository(session, tenant_id).list(limit=limit, offset=offset, order_by=order_by)


def get_customer(session: Session, tenant_id: uuid.UUID, customer_id: uuid.UUID) -> Customer | None:
    return CustomerRepository(session, tenant_id).get(customer_id)


def get_customer_by_number(session: Session, tenant_id: uuid.UUID, customer_number: str) -> Customer | None:
    """Used by bulk file imports (accounts, users) to resolve a human-readable customer
    number in an uploaded row to this tenant's internal customer id — files never carry
    our UUIDs, only the number a bank employee would actually recognize."""
    matches = CustomerRepository(session, tenant_id).list(customer_number=customer_number)
    return matches[0] if matches else None
