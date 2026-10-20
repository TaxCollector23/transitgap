from pathlib import Path

from backend.app.data_sources import arcgis


def test_arcgis_metadata_query_batches_ids_and_preserves_provenance(tmp_path: Path, monkeypatch):
    calls = []

    def fake_get_json(url, params, timeout_seconds=20):
        calls.append((url, dict(params)))
        if url.endswith("/185"):
            return {"capabilities": "Query,Extract", "geometryType": "esriGeometryPolygon",
                    "objectIdField": "OBJECTID", "maxRecordCount": 2,
                    "copyrightText": "City of San Jose",
                    "sourceSpatialReference": {"latestWkid": 2227},
                    "supportedQueryFormats": "JSON, geoJSON",
                    "advancedQueryCapabilities": {"supportsPagination": True}}
        if url.endswith("/query") and params.get("returnIdsOnly"):
            return {"objectIds": [7, 8, 9]}
        if url.endswith("/query"):
            ids = [int(value) for value in params["objectIds"].split(",")]
            return {"features": [{"type": "Feature", "id": oid,
                                  "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
                                  "properties": {"OBJECTID": oid, "ADACOMPLY": "Unknown"}}
                                 for oid in ids]}
        return {"licenseInfo": "Use subject to City terms", "accessInformation": "City GIS"}

    monkeypatch.setattr(arcgis, "_get_json", fake_get_json)
    result = arcgis.fetch_feature_layer(layer_url="https://example.test/185",
                                       item_info_url="https://example.test/info",
                                       bbox=(-121.92, 37.31, -121.89, 37.35),
                                       cache_path=tmp_path / "sidewalks.json")
    assert [feature["id"] for feature in result["features"]] == [7, 8, 9]
    assert result["metadata"]["source_spatial_reference"] == 2227
    assert result["metadata"]["license_info"] == "Use subject to City terms"
    assert result["features"][0]["properties"]["ADACOMPLY"] == "Unknown"
    batches = [params["objectIds"] for url, params in calls if url.endswith("/query") and "objectIds" in params]
    assert batches == ["7,8", "9"]
    assert (tmp_path / "sidewalks.json").exists()


def test_stale_cache_is_available_after_network_failure(tmp_path: Path):
    path = tmp_path / "cache.json"
    path.write_text('{"type":"FeatureCollection","metadata":{"retrieved_at":"2026-01-01T00:00:00+00:00"},"features":[]}', encoding="utf-8")
    result = arcgis.load_cached_or_stale(path, RuntimeError("offline"))
    assert result["metadata"]["availability"] == "stale"
    assert result["metadata"]["last_refresh_error"] == "offline"
