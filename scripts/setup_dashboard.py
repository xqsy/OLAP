"""Create or update the three SQL widgets and period filter required by lab 10."""

import json
import time

from metabase import Metabase, ROOT


DASHBOARD_NAME = "OLAP · Бронирования H1/H2"
PARAMETER_ID = "arrival_period"
WIDGETS = (
    ("completed_bookings", "OLAP · Состоявшиеся бронирования", "scalar", {}, 0, 0, 6, 4),
    ("monthly_bookings", "OLAP · Бронирования по месяцам и отелям", "line",
     {"graph.dimensions": ["arrival_month", "hotel_code"],
      "graph.metrics": ["completed_booking_count"]}, 0, 6, 18, 8),
    ("top_channels", "OLAP · Топ-10 сегментов и каналов", "row",
     {"graph.dimensions": ["channel"], "graph.metrics": ["completed_booking_count"]}, 8, 0, 24, 8),
)


def main():
    api = Metabase().login(allow_setup=True)
    databases = api.request("GET", "/database")["data"]
    database = next((d for d in databases if d["name"] == "booking_dw" and d["engine"] == "clickhouse"), None)
    if database is None:
        database = api.request("POST", "/database", {
            "name": "booking_dw", "engine": "clickhouse",
            "details": {"host": "clickhouse", "port": 8123, "dbname": "booking_dw",
                        "user": "default", "password": "", "ssl": False},
        })
    database_id = database["id"]
    api.request("POST", f"/database/{database_id}/sync_schema")
    field = None
    for _ in range(30):
        metadata = api.request("GET", f"/database/{database_id}/metadata")
        field = next((f for t in metadata["tables"] if t["name"] == "dim_date"
                      for f in t["fields"] if f["name"] == "full_date"), None)
        if field:
            break
        time.sleep(2)
    if field is None:
        raise RuntimeError("Metabase has not discovered dim_date.full_date; check ClickHouse and retry")

    cards = api.request("GET", "/card")
    card_ids = {}
    for key, name, display, settings, *_ in WIDGETS:
        payload = {
            "name": name, "display": display, "visualization_settings": settings,
            "dataset_query": {
                "database": database_id, "type": "native",
                "native": {
                    "query": (ROOT / "dashboards" / f"{key}.sql").read_text(encoding="utf-8"),
                    "template-tags": {PARAMETER_ID: {
                        "id": PARAMETER_ID, "name": PARAMETER_ID, "display-name": "Период заезда",
                        "type": "dimension", "dimension": ["field", field["id"], None],
                        "widget-type": "date/all-options", "required": False,
                    }},
                },
            },
        }
        old = next((c for c in cards if c["name"] == name), None)
        card = api.request("PUT", f"/card/{old['id']}", payload) if old else api.request("POST", "/card", payload)
        card_ids[key] = card["id"]

    dashboards = api.request("GET", "/dashboard")
    dashboard = next((d for d in dashboards if d["name"] == DASHBOARD_NAME), None)
    if dashboard is None:
        dashboard = api.request("POST", "/dashboard", {"name": DASHBOARD_NAME})
    dashboard = api.request("GET", f"/dashboard/{dashboard['id']}")
    existing = {d["card_id"]: d for d in dashboard["dashcards"]}
    placements = []
    for index, (key, _, _, _, row, col, width, height) in enumerate(WIDGETS, 1):
        card_id = card_ids[key]
        placements.append({
            "id": existing.get(card_id, {}).get("id", -index), "card_id": card_id,
            "row": row, "col": col, "size_x": width, "size_y": height,
            "series": [], "visualization_settings": {},
            "parameter_mappings": [{
                "parameter_id": PARAMETER_ID, "card_id": card_id,
                "target": ["dimension", ["template-tag", PARAMETER_ID]],
            }],
        })
    dashboard = api.request("PUT", f"/dashboard/{dashboard['id']}", {
        "description": "Состоявшиеся бронирования по дате заезда. Источник: ClickHouse booking_dw.",
        "parameters": [{"id": PARAMETER_ID, "name": "Период заезда", "slug": PARAMETER_ID,
                        "type": "date/all-options"}],
        "dashcards": placements,
    })
    manifest = {"database_id": database_id, "dashboard_id": dashboard["id"],
                "cards": card_ids, "url": f"{api.url}/dashboard/{dashboard['id']}"}
    (ROOT / "data/metabase_dashboard.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(manifest["url"])
    print("Three SQL widgets; arrival_period is mapped to all three.")
    print("Local first-run credentials: data/metabase_local.json (excluded from Git)")


if __name__ == "__main__":
    main()
