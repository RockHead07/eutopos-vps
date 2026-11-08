export interface CamPose {
  x: number;
  y: number;
  z: number;
  yaw: number;
  pitch: number;
}

export interface PlayCanvasCam {
  position: [number, number, number];
  target: [number, number, number];
  forward: [number, number, number];
  up: [number, number, number];
}

/**
 * Parse cam query string in building frame: "x,y,z,yaw,pitch" (all numbers).
 * Returns null if string is empty, has incorrect token count, or contains NaN/Infinity.
 */
export function parseCam(s: string | null): CamPose | null {
  if (!s) return null;
  const parts = s.split(",").map((p) => p.trim());
  if (parts.length !== 5) return null;
  const nums = parts.map(Number);
  if (nums.some((n) => isNaN(n) || !isFinite(n))) return null;
  return {
    x: nums[0],
    y: nums[1],
    z: nums[2],
    yaw: nums[3],
    pitch: nums[4],
  };
}

/**
 * Convert building camera pose to PlayCanvas coordinates.
 * Building frame: z is up.
 * yaw: rotated around building z-axis counter-clockwise viewed from above, 0 = facing +x.
 * pitch: positive = looking up.
 * Building forward vector: f = (cos p * cos y, cos p * sin y, sin p).
 * PlayCanvas world frame:
 * Point (x, y, z) -> (x, z, -y).
 * Forward (fx, fy, fz) -> (fx, fz, -fy).
 * Target = position + forward.
 * Up = (0, 1, 0).
 */
export function camToPlayCanvas(cam: CamPose): PlayCanvasCam {
  const radYaw = (cam.yaw * Math.PI) / 180;
  const radPitch = (cam.pitch * Math.PI) / 180;
  const cosP = Math.cos(radPitch);
  const sinP = Math.sin(radPitch);
  const fx = cosP * Math.cos(radYaw);
  const fy = cosP * Math.sin(radYaw);
  const fz = sinP;

  // Building (x, y, z) -> PlayCanvas (x, z, -y)
  const px = cam.x;
  const py = cam.z;
  const pz = -cam.y;

  // Forward (fx, fy, fz) -> PlayCanvas (fx, fz, -fy)
  const dfx = fx;
  const dfy = fz;
  const dfz = -fy;

  return {
    position: [px, py, pz],
    target: [px + dfx, py + dfy, pz + dfz],
    forward: [dfx, dfy, dfz],
    up: [0, 1, 0],
  };
}
