export interface Building {
  id: number;
  slug: string;
  name: string;
  area_ids: string[];
}

export function buildingOfArea(
  buildings: Building[],
  areaId: string
): Building | undefined {
  return buildings.find((b) => b.area_ids.includes(areaId));
}
