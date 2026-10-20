from enum import Enum
from math import isfinite
from pydantic import BaseModel, Field, field_validator

class Algorithm(str, Enum):
    dijkstra = "dijkstra"
    bidirectional_dijkstra = "bidirectional_dijkstra"
    astar = "astar"
    bellman_ford = "bellman_ford"
    breadth_first = "breadth_first"

class Profile(str, Enum):
    standard = "standard"
    wheelchair = "wheelchair"
    stroller = "stroller"
    low_vision = "low_vision"
    avoid_mapped_stairs = "avoid_mapped_stairs"
    prefer_documented_paths = "prefer_documented_paths"

class RouteRequest(BaseModel):
    origin_latitude: float = Field(ge=-90, le=90)
    origin_longitude: float = Field(ge=-180, le=180)
    destination_stop_id: str = Field(min_length=1, max_length=100)
    algorithm: Algorithm = Algorithm.dijkstra
    profile: Profile = Profile.standard

    @field_validator("origin_latitude", "origin_longitude")
    @classmethod
    def finite_origin(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("Coordinates must be finite numbers")
        return value


class RouteComparisonRequest(BaseModel):
    origin_latitude: float = Field(ge=-90, le=90)
    origin_longitude: float = Field(ge=-180, le=180)
    destination_stop_id: str = Field(min_length=1, max_length=100)
    algorithm: Algorithm = Algorithm.astar
    profile: Profile = Profile.wheelchair

    @field_validator("origin_latitude", "origin_longitude")
    @classmethod
    def finite_origin(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("Coordinates must be finite numbers")
        return value
