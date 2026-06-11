from datetime import date

from sfo_kalshi_quant.ensemble import parse_open_meteo_ensemble_payload


def test_open_meteo_parser_keeps_control_plus_30_members():
    target = date(2026, 6, 3)
    daily = {
        "time": [target.isoformat()],
        "temperature_2m_max": [62.9],
    }
    for member in range(1, 31):
        daily[f"temperature_2m_max_member{member:02d}"] = [60.0 + member / 10.0]
    payload = {
        "latitude": 37.5,
        "longitude": -122.5,
        "elevation": 5.0,
        "daily": daily,
    }

    snapshot = parse_open_meteo_ensemble_payload(
        payload,
        target,
        67.0,
        cell_selection="nearest",
    )

    assert snapshot.member_count == 31
    assert snapshot.raw_member_highs_f[0] == 62.9
    assert round(snapshot.station_mean_high_f, 6) == 67.0
