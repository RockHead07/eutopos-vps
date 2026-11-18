import { test } from "node:test";
import assert from "node:assert/strict";
// @ts-expect-error Node's type stripping requires the .ts extension.
import { buildingOfArea, type Building } from "./buildings.ts";

const sampleBuildings: Building[] = [
  { id: 1, slug: "hcm", name: "HCM", area_ids: ["floor10", "floor9"] },
  { id: 2, slug: "pens", name: "PENS", area_ids: ["pens-lab"] },
];

test("buildingOfArea returns building when area is known", () => {
  const b = buildingOfArea(sampleBuildings, "floor10");
  assert.equal(b?.slug, "hcm");
  assert.equal(b?.name, "HCM");

  const b2 = buildingOfArea(sampleBuildings, "pens-lab");
  assert.equal(b2?.slug, "pens");
});

test("buildingOfArea returns undefined when area is unknown", () => {
  const b = buildingOfArea(sampleBuildings, "unknown-area");
  assert.equal(b, undefined);
});
