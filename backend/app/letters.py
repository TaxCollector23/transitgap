"""Editable civic drafts from actual evaluated stop records. Nothing is sent."""


def generate_letter(detail):
    from datetime import datetime, timezone

    stop_id = detail["stop_id"]

    def miles(value):
        return f"{value / 1609.344:.2f} miles"

    return (
        f"To the appropriate VTA or local public works accessibility team,\n\n"
        f"Please assess pedestrian access to {detail['stop_name']} (VTA stop {stop_id}), "
        f"at {detail['latitude']}, {detail['longitude']}.\n\n"
        f"TransitGap's ten-minute network model reaches {miles(detail['standard']['reachable_length_m'])} "
        f"under the standard profile and {miles(detail['wheelchair']['reachable_length_m'])} under its wheelchair profile. "
        f"These are model results using OpenStreetMap walking paths and VTA GTFS, not an on-site inspection. "
        f"Different assumed speeds (1.2 and 0.9 m/s) and mapped constraints both affect this difference. "
        f"Missing curb, slope and surface information must not be interpreted as a confirmed barrier.\n\n"
        f"I request an assessment of crossings, curb transitions and path conditions near this stop, "
        f"and publication or correction of accessibility records where appropriate.\n\n"
        f"My observations (edit before sending):\n[Describe only what you personally observed, with date.]\n\n"
        f"Prepared {datetime.now(timezone.utc).date().isoformat()} with TransitGap. "
        f"Sources: https://www.openstreetmap.org/copyright ; https://gtfs.vta.org/gtfs_vta.zip . "
        f"Method: https://github.com/TaxCollector23/transitgap/blob/main/docs/METHODOLOGY.md .\n"
        f"This draft has not been sent to any agency."
    )
