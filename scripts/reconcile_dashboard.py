"""Compare the canonical ClickHouse SQL with the live dashboard metric (lab 11)."""

from datetime import datetime, timedelta, timezone
import json
import os
import sys

from metabase import Metabase, ROOT

sys.path.insert(0, str(ROOT / "etl"))
from load_clickhouse import ClickHouse


def main():
    api = Metabase().login()
    manifest = json.loads((ROOT / "data/metabase_dashboard.json").read_text(encoding="utf-8"))
    dashboard = api.request("GET", f"/dashboard/{manifest['dashboard_id']}")
    metric_id = manifest["cards"]["completed_bookings"]
    placement = next(d for d in dashboard["dashcards"] if d["card_id"] == metric_id)
    mapping = next(p for p in placement["parameter_mappings"] if p["parameter_id"] == "arrival_period")
    parameter = next(p for p in dashboard["parameters"] if p["id"] == "arrival_period")
    database_id = placement["card"]["dataset_query"]["database"]
    database = api.request("GET", f"/database/{database_id}")
    if database["engine"] != "clickhouse" or database["details"]["dbname"] != "booking_dw":
        raise RuntimeError("The dashboard metric must use ClickHouse booking_dw")
    saved_sql = placement["card"]["dataset_query"]["native"]["query"]
    if saved_sql.strip() != (ROOT / "dashboards/completed_bookings.sql").read_text(encoding="utf-8").strip():
        raise RuntimeError("The live metric SQL differs from dashboards/completed_bookings.sql")
    clickhouse = ClickHouse(os.environ.get("CLICKHOUSE_URL", "http://localhost:8123"), "booking_dw")
    canonical = (ROOT / "sql/canonical_metric.sql").read_text(encoding="utf-8").strip().rstrip(";")
    lines = [
        "# З11. Сверка SQL и карточки Metabase", "",
        "Проверено: " + datetime.now(timezone(timedelta(hours=3))).isoformat(timespec="seconds") + ".", "",
        "Источник — ClickHouse `booking_dw`. Метрика — число строк `fact_booking`",
        "с `reservation_status = 'Check-Out'`. Период относится к дате заезда;",
        "ограничений по отелю, стране, сегменту и каналу нет.", "",
        "| Условия | Эталонный SQL | Карточка Metabase | Разница | Вывод |",
        "|---|---:|---:|---:|---|",
    ]
    passed = True
    for label, period, extra_sql in (
        ("Весь доступный период, фильтр отключён", None, ""),
        ("01.09.2016–30.09.2016 включительно", "2016-09-01~2016-09-30",
         "\nAND arrival_date_id >= 20160901 AND arrival_date_id < 20161001"),
    ):
        expected = int(clickhouse.scalar(canonical + extra_sql))
        parameters = [] if period is None else [{
            "type": parameter["type"], "id": parameter["id"],
            "target": mapping["target"], "value": period,
        }]
        result = api.request(
            "POST", f"/dashboard/{dashboard['id']}/dashcard/{placement['id']}/card/{metric_id}/query",
            {"parameters": parameters, "ignore_cache": True},
        )
        if result.get("status") != "completed":
            raise RuntimeError(result.get("error", "Dashboard query did not complete"))
        actual = int(result["data"]["rows"][0][0])
        ok = actual == expected
        passed = passed and ok
        lines.append(f"| {label} | {expected} | {actual} | {actual - expected} | {'Совпало' if ok else 'НЕ СОВПАЛО'} |")
    lines += [
        "", "Запрос A выполняется напрямую в ClickHouse из `sql/canonical_metric.sql`.",
        "Для контрольного месяца к нему добавляются границы `arrival_date_id >= 20160901`",
        "и `arrival_date_id < 20161001`. Запрос B выполняется через API карточки",
        "на сохранённом дашборде с его фактическим сопоставлением общего фильтра.",
        "Текст SQL виджета проверяется против `dashboards/completed_bookings.sql`.", "",
        "Сохранённые скриншоты проверки в браузере: без фильтра — 75 166,",
        "за сентябрь 2016 — 3 372. Файлы: `dashboards/z10_dashboard.png`",
        "и `dashboards/z10_dashboard_september.png`.", "",
        "Повторить: `python scripts/reconcile_dashboard.py`.", "",
        "Вывод: числа совпали при одинаковых фильтрах; расхождений нет." if passed else
        "Вывод: обнаружено расхождение, сверка не пройдена.",
    ]
    (ROOT / "notes/z11.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
