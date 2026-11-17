import { test } from "node:test";
import assert from "node:assert/strict";
// @ts-expect-error Node's type stripping requires the .ts extension.
import { viewPose } from "./splatViews.ts";

const I = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
const view = { name: "a.jpg", center: [1, 2, 3] as [number, number, number], forward: [0, 0, 1] as [number, number, number] };

test("identity matrix", () => {
  assert.deepEqual(viewPose(view, I), { position: [1, 2, 3], target: [1, 2, 4] });
});

test("translation", () => {
  const world = [...I];
  world[12] = 10;
  world[14] = -5;
  assert.deepEqual(viewPose(view, world), { position: [11, 2, -2], target: [11, 2, -1] });
});

test("scale 2 keeps unit look direction", () => {
  const world = [...I];
  world[0] = world[5] = world[10] = 2;
  assert.deepEqual(viewPose(view, world), { position: [2, 4, 6], target: [2, 4, 7] });
});

test("rotation 180 about X", () => {
  const world = [...I];
  world[5] = world[10] = -1;
  assert.deepEqual(viewPose(view, world), { position: [1, -2, -3], target: [1, -2, -4] });
});
