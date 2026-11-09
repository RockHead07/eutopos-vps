import { Mat4, Vec3 } from "playcanvas";

/**
 * Maps a direction or vector in building space (x right, y forward, z up)
 * to PlayCanvas space (x right, y up, z backward):
 * (vx, vy, vz) -> (vx, vz, -vy)
 */
export function buildingToPlayCanvas(v: Vec3): Vec3 {
    return new Vec3(v.x, v.z, -v.y);
}

/**
 * Maps a direction or vector in PlayCanvas space
 * back to building space:
 * (vx, vy, vz) -> (vx, -vz, vy)
 */
export function playCanvasToBuilding(v: Vec3): Vec3 {
    return new Vec3(v.x, -v.z, v.y);
}

/**
 * P is the mapping from building space to PlayCanvas space:
 * [1,  0,  0, 0]
 * [0,  0,  1, 0]
 * [0, -1,  0, 0]
 * [0,  0,  0, 1]
 *
 * P^-1 = P^T:
 * [1,  0,  0, 0]
 * [0,  0, -1, 0]
 * [0,  1,  0, 0]
 * [0,  0,  0, 1]
 *
 * Stored in column-major order in Float32Array:
 * col 0: [1,  0, 0, 0]
 * col 1: [0,  0, 1, 0]
 * col 2: [0, -1, 0, 0]
 * col 3: [0,  0, 0, 1]
 */
const P_INV = new Mat4();
P_INV.data[0] = 1;
P_INV.data[1] = 0;
P_INV.data[2] = 0;
P_INV.data[3] = 0;

P_INV.data[4] = 0;
P_INV.data[5] = 0;
P_INV.data[6] = 1;
P_INV.data[7] = 0;

P_INV.data[8] = 0;
P_INV.data[9] = -1;
P_INV.data[10] = 0;
P_INV.data[11] = 0;

P_INV.data[12] = 0;
P_INV.data[13] = 0;
P_INV.data[14] = 0;
P_INV.data[15] = 1;

/**
 * Computes M' = P^-1 * W where W is the camera world transform.
 * Passing M' to ViewCube.update aligns the ViewCube so that the
 * building's vertical +Z axis points UP on screen when the camera is upright.
 */
export function getBuildingCameraMatrix(cameraWorldTransform: Mat4, out: Mat4 = new Mat4()): Mat4 {
    return out.mul2(P_INV, cameraWorldTransform);
}
