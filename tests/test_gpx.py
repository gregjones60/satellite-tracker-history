from pathlib import Path
import pytest
from custom_components.spot_trace_history.gpx import parse_gpx


def test_real_spot_activity_report():
    sample = Path(__file__).parent / "fixtures" / "activity_report.gpx"
    points = parse_gpx(sample, {"Bluey": "vehicle-123", "Ultimate": "trailer-456"})
    assert len(points) == 4
    assert {p["device"] for p in points} == {"vehicle-123", "trailer-456"}
    assert all(p["time"] > 0 for p in points)
    assert all(-90 <= p["lat"] <= 90 and -180 <= p["lon"] <= 180 for p in points)


def test_invalid_gpx(tmp_path):
    file = tmp_path / "bad.gpx"
    file.write_text("<not-gpx/>")
    with pytest.raises(ValueError, match="GPX 1.1"):
        parse_gpx(file)
