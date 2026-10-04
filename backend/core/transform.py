"""Engine-independent transforms for the GraphWorld protocol."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class Transform:
    """Meters, right-handed Z-up coordinates, quaternion rotation."""

    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "Transform":
        value = value or {}
        position = tuple(float(x) for x in (value.get("position") or (0.0, 0.0, 0.0)))
        rotation = tuple(float(x) for x in (value.get("rotation") or (0.0, 0.0, 0.0, 1.0)))
        scale = tuple(float(x) for x in (value.get("scale") or (1.0, 1.0, 1.0)))
        if len(position) != 3 or len(rotation) != 4 or len(scale) != 3:
            raise ValueError("Transform requires position[3], rotation[4], and scale[3]")
        norm = sqrt(sum(x * x for x in rotation))
        if norm <= 1e-12:
            raise ValueError("Transform rotation quaternion cannot be zero")
        return cls(position, tuple(x / norm for x in rotation), scale)

    def to_dict(self) -> dict[str, list[float]]:
        return {"position": list(self.position), "rotation": list(self.rotation), "scale": list(self.scale)}

    def compose(self, child: "Transform") -> "Transform":
        """Compose a local transform onto this transform without an engine dependency."""
        px, py, pz = _rotate(self.rotation, tuple(child.position[index] * self.scale[index] for index in range(3)))
        return Transform(
            (self.position[0] + px, self.position[1] + py, self.position[2] + pz),
            _quat_multiply(self.rotation, child.rotation),
            tuple(self.scale[index] * child.scale[index] for index in range(3)),
        )


IDENTITY_TRANSFORM = Transform()


def _quat_multiply(left: tuple[float, float, float, float], right: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    lx, ly, lz, lw = left
    rx, ry, rz, rw = right
    result = (lw * rx + lx * rw + ly * rz - lz * ry,
              lw * ry - lx * rz + ly * rw + lz * rx,
              lw * rz + lx * ry - ly * rx + lz * rw,
              lw * rw - lx * rx - ly * ry - lz * rz)
    norm = sqrt(sum(value * value for value in result))
    return tuple(value / norm for value in result) if norm > 1e-12 else (0.0, 0.0, 0.0, 1.0)


def _rotate(rotation: tuple[float, float, float, float], vector: tuple[float, float, float]) -> tuple[float, float, float]:
    x, y, z, w = rotation
    vx, vy, vz = vector
    qv = (w * vx + y * vz - z * vy, w * vy + z * vx - x * vz, w * vz + x * vy - y * vx)
    uv = (x * qv[2] - z * qv[1], y * qv[0] - x * qv[2], z * qv[1] - y * qv[0])
    uuv = (x * uv[2] - z * uv[1], y * uv[0] - x * uv[2], z * uv[1] - y * uv[0])
    return (vx + 2.0 * (uv[0] + uuv[0]), vy + 2.0 * (uv[1] + uuv[1]), vz + 2.0 * (uv[2] + uuv[2]))

__all__ = ["IDENTITY_TRANSFORM", "Transform"]
