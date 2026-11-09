declare module "playcanvas/scripts/esm/camera-controls.mjs" {
    import { Script, Vec2, Vec3 } from "playcanvas";

    export class CameraControls extends Script {
        static scriptName: string;
        focusPoint: Vec3;
        enableOrbit: boolean;
        enableFly: boolean;
        enablePan: boolean;
        zoomRange: Vec2;
        pitchRange: Vec2;
        yawRange: Vec2;
        moveSpeed: number;
        moveFastSpeed: number;
        moveSlowSpeed: number;
        focusDamping: number;
        moveDamping: number;
        rotateDamping: number;
        zoomDamping: number;
        focus(point: Vec3, resetZoom?: boolean): void;
        look(point: Vec3, resetZoom?: boolean): void;
        reset(focus: Vec3, position: Vec3): void;
    }
}

declare module "playcanvas/scripts/esm/grid.mjs" {
    import { Script, Color } from "playcanvas";

    export class Grid extends Script {
        static scriptName: string;
        static RESOLUTION_LOW: number;
        static RESOLUTION_MEDIUM: number;
        static RESOLUTION_HIGH: number;
        colorX: Color;
        colorZ: Color;
        resolution: number;
    }
}
