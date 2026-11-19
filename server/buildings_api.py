"""API untuk pengelolaan gedung (Building) dan hubungan area."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlmodel import select

from server import auth, uploads
from server.db import DEFAULT_ORG_SLUG, Area, Building, Organization

router = APIRouter()


class BuildingIn(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,39}$")  # sama dengan pola area di uploads.py
    name: str = Field(min_length=1, max_length=100)


class BuildingOut(BaseModel):
    id: int
    slug: str
    name: str
    area_ids: list[str]


@router.get("/api/buildings")
def list_buildings(user: uploads.User, s: uploads.DB) -> list[BuildingOut]:
    stmt = select(Building).order_by(Building.name)
    buildings = list(s.exec(stmt))
    stmt_areas = select(Area.id, Area.building_id).order_by(Area.id)
    areas_by_bld: dict[int, list[str]] = {}
    for area_id, bld_id in s.exec(stmt_areas):
        areas_by_bld.setdefault(bld_id, []).append(area_id)
    return [
        BuildingOut(
            id=b.id,
            slug=b.slug,
            name=b.name,
            area_ids=areas_by_bld.get(b.id, []),
        )
        for b in buildings
    ]


def _admin_json(request: Request, user: uploads.User) -> None:
    # Sama dengan endpoint tulis lain: application/json (tutup CSRF lewat preflight), admin saja.
    # Jadi dependency agar jalan sebelum body divalidasi (non-JSON harus 415, bukan 422).
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
        raise HTTPException(415, "send with Content-Type: application/json")
    if not auth.is_admin(user):
        raise HTTPException(403, "only admins can create buildings")


@router.post("/api/buildings", status_code=201, dependencies=[Depends(_admin_json)])
def create_building(body: BuildingIn, s: uploads.DB) -> BuildingOut:
    default_org = s.exec(select(Organization).where(Organization.slug == DEFAULT_ORG_SLUG)).first()
    if default_org is None:
        raise HTTPException(500, "default organization not found")

    existing = s.exec(
        select(Building).where(Building.org_id == default_org.id, Building.slug == body.slug)
    ).first()
    if existing is not None:
        return JSONResponse(status_code=409, content={"code": "building_exists"})

    bld = Building(org_id=default_org.id, slug=body.slug, name=body.name)
    s.add(bld)
    s.commit()
    s.refresh(bld)
    return BuildingOut(id=bld.id, slug=bld.slug, name=bld.name, area_ids=[])
