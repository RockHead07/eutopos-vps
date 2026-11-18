"""API untuk pengelolaan gedung (Building) dan hubungan area."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlmodel import select

from server import auth, uploads
from server.db import DEFAULT_ORG_SLUG, Area, Building, Organization

router = APIRouter()


class BuildingIn(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    name: str = Field(min_length=1)


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


@router.post("/api/buildings", status_code=201)
async def create_building(request: Request, user: uploads.User, s: uploads.DB) -> BuildingOut:
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
        raise HTTPException(415, "send with Content-Type: application/json")
    if not auth.is_admin(user):
        raise HTTPException(403, "only admins can create buildings")
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(422, "invalid json") from None
    try:
        body = BuildingIn.model_validate(data)
    except Exception as e:
        raise HTTPException(422, str(e)) from e

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
