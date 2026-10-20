from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.observation_models import ObservationCreate
from backend.app.observations import create_observation, initialize_observations, list_observations


def test_observation_is_persisted_as_unverified(tmp_path: Path):
    path = tmp_path / "reports.sqlite3"
    initialize_observations(path)
    created = create_observation(latitude=37.33, longitude=-121.90,
                                category="sidewalk_obstruction", description="Temporary construction",
                                path=path)
    # Reopen through a separate read connection to cover persistence, not just the returned row.
    result = list_observations(path=path)
    assert result["count"] == 1
    assert result["observations"][0]["id"] == created["id"]
    assert result["observations"][0]["evidence_status"] == "COMMUNITY_REPORTED"
    assert result["observations"][0]["review_status"] == "UNREVIEWED"


def test_report_input_validates_coordinates_and_text_length():
    payload = ObservationCreate(latitude=37.33, longitude=-121.9,
                                category="uneven_surface", description="  loose paving  ")
    assert payload.description == "loose paving"
    with pytest.raises(ValidationError):
        ObservationCreate(latitude=91, longitude=0, category="other")
    with pytest.raises(ValidationError):
        ObservationCreate(latitude=0, longitude=0, category="other", description="x" * 501)


def test_report_text_remains_plain_and_control_characters_are_rejected():
    with pytest.raises(ValidationError):
        ObservationCreate(latitude=37.33, longitude=-121.9, category="other", description="unsafe\u0000text")
    payload = ObservationCreate(latitude=37.33, longitude=-121.9,
                                category="other", description="<script>alert(1)</script>")
    assert payload.description == "<script>alert(1)</script>"
