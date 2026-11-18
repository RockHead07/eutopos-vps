"""Fixture dan helper bersama untuk pengujian."""

import pytest
from sqlmodel import Session, select

from server.db import (
    DEFAULT_BUILDING_NAME,
    DEFAULT_BUILDING_SLUG,
    DEFAULT_ORG_NAME,
    DEFAULT_ORG_SLUG,
    Building,
    Organization,
)


def make_building(session: Session) -> Building:
    """Helper pengujian: pastikan organisasi dan gedung bawaan (HCM) ada."""
    org = session.exec(select(Organization).where(Organization.slug == DEFAULT_ORG_SLUG)).first()
    if org is None:
        org = Organization(slug=DEFAULT_ORG_SLUG, name=DEFAULT_ORG_NAME)
        session.add(org)
        session.commit()
        session.refresh(org)
    bld = session.exec(
        select(Building).where(Building.slug == DEFAULT_BUILDING_SLUG, Building.org_id == org.id)
    ).first()
    if bld is None:
        bld = Building(org_id=org.id, slug=DEFAULT_BUILDING_SLUG, name=DEFAULT_BUILDING_NAME)
        session.add(bld)
        session.commit()
        session.refresh(bld)
    return bld


@pytest.fixture
def default_building(session: Session) -> Building:
    return make_building(session)
