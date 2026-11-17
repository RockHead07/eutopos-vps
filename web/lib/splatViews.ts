import type { SplatView } from "./api";

/** Transform a model-frame view by a column-major splat world matrix. */
export function viewPose(view: SplatView, world: ArrayLike<number>): {
  position: [number, number, number];
  target: [number, number, number];
} {
  const [x, y, z] = view.center;
  const [fx, fy, fz] = view.forward;
  const position: [number, number, number] = [
    world[0] * x + world[4] * y + world[8] * z + world[12],
    world[1] * x + world[5] * y + world[9] * z + world[13],
    world[2] * x + world[6] * y + world[10] * z + world[14],
  ];
  const dx = world[0] * fx + world[4] * fy + world[8] * fz;
  const dy = world[1] * fx + world[5] * fy + world[9] * fz;
  const dz = world[2] * fx + world[6] * fy + world[10] * fz;
  const length = Math.hypot(dx, dy, dz);
  return {
    position,
    target: [position[0] + dx / length, position[1] + dy / length, position[2] + dz / length],
  };
}
