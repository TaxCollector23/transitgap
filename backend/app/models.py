from enum import Enum
from pydantic import BaseModel, Field, field_validator

class Algorithm(str, Enum):
    dijkstra = "dijkstra"
    bidirectional_dijkstra = "bidirectional_dijkstra"
    astar = "astar"

class Profile(str, Enum):
    standard = "standard"
    avoid_mapped_stairs = "avoid_mapped_stairs"

class RouteRequest(BaseModel):
    origin_latitude: float = Field(ge=-90, le=90)
    origin_longitude: float = Field(ge=-180, le=180)
    destination_stop_id: str = Field(min_length=1, max_length=100)
    algorithm: Algorithm = Algorithm.dijkstra
    profile: Profile = Profile.standard

class Coordinate(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

    @field_validator("latitude", "longitude")
    @classmethod
    def finite_coordinate(cls, value: float) -> float:
        if not (-float("inf") < value < float("inf")):
            raise ValueError("Coordinate must be finite")
        return value
