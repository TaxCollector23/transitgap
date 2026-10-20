# Phase 4 evaluation

## Question

Does comparing San José sidewalk polygons with explicit OSM pedestrian ways reveal useful places to gather more information?

## Method

The adapter queries the San José Sidewalks ArcGIS layer using a WGS84 envelope around the Diridon study area, batches by object ID, preserves the original IDs and attributes, and clips municipal polygons to the configured circular study area in EPSG:26910. It compares those polygons with explicit OSM pedestrian paths, not road centerlines. Correspondence is set to 5 m; nearby ambiguity is reviewed through 14 m. These thresholds are engineering choices, not empirically calibrated accuracy limits.

## Reproducibility and current results

The source was reachable during implementation. A bounded envelope response contained 1,829 GeoJSON features, while its service count endpoint reported 1,828 IDs. That one-feature discrepancy has not been explained. The envelope response is not the clipped circular study-area count.

The final GroundTruth index evaluation has **not been executed** in this workspace. Therefore, clipped municipal features, matched/ambiguous classifications, candidates, distinct VTA stops and sampled route pairs are not reported here. Run the implementation's `evaluation()` output and record it here after the Python environment and packaged OSM/GTFS data are available. Do not infer these counts from the envelope response.

## Interpretation

Proximity cannot establish that two source features describe the same physical sidewalk, particularly across opposite sides of a street or around an intersection. The City layer describes polygon areas and has a source accuracy disclaimer. OSM tags are community-maintained and may be absent. A source difference identifies an investigation opportunity, not missing physical infrastructure. No independent field validation was performed, so no ground-truth accuracy claim is supported.
