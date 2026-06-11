"""Quick inspection of the cleaned 2016-2026 weather dataset."""

import pandas as pd

CSV_PATH = "combined_weather.csv"
SFO_STATION_ID = "USW00023234"


def load_data(path):
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="ISO8601", utc=True)
    df = df[df["station_id"] == SFO_STATION_ID].copy()
    return df


def main():
    df = load_data(CSV_PATH)

    print("shape")
    print(df.shape)

    print("\nstations")
    print(df.groupby(["station_id", "station_name"]).size().rename("rows"))

    print("\nfirst 5 rows")
    print(df[["timestamp", "temp_f", "humidity", "wind_speed_mph",
              "pressure_hpa", "sky_condition"]].head())

    print("\nbasic stats")
    print(df[["temp_f", "dew_point_f", "humidity", "wind_speed_mph",
              "wind_gust_mph", "pressure_hpa", "precip_mm",
              "visibility_km"]].describe().round(2))

    print("\nmissing values per column")
    missing = df.isnull().sum()
    missing = missing[missing > 0].sort_values(ascending=False)
    if len(missing) == 0:
        print("(none)")
    else:
        pct = (missing / len(df) * 100).round(1)
        print(pd.DataFrame({"missing": missing, "pct": pct}).to_string())

    print("\ndate coverage")
    start, end = df["timestamp"].min(), df["timestamp"].max()
    span_hours = int((end - start).total_seconds() / 3600) + 1
    print(f"start:    {start}")
    print(f"end:      {end}")
    print(f"span:     {end - start}")
    print(f"expected: {span_hours:,} hourly rows")
    print(f"actual:   {len(df):,} rows")

    print("\nrows per year")
    yearly = df.groupby(df["timestamp"].dt.year).size().rename("rows")
    expected_per_year = {
        y: (366 if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0) else 365) * 24
        for y in yearly.index
    }
    yearly_pct = (yearly / pd.Series(expected_per_year) * 100).round(1)
    print(pd.DataFrame({"rows": yearly, "pct_of_full_year": yearly_pct}).to_string())

    print("\nhourly gaps (>1h)")
    for sid, sub in df.groupby("station_id"):
        ts = sub["timestamp"].sort_values().reset_index(drop=True)
        gaps = ts.diff().dt.total_seconds() / 3600
        gap_rows = gaps[gaps > 1].sort_values(ascending=False)
        name = sub["station_name"].iloc[0]
        print(f"\n  {sid} - {name}")
        if len(gap_rows) == 0:
            print("    (none - fully continuous)")
        else:
            print(f"    {len(gap_rows)} gaps, total missing approx "
                  f"{int((gap_rows - 1).sum()):,} hours. largest 5:")
            for idx, hours in gap_rows.head(5).items():
                print(f"      {ts[idx]}   gap = {hours:.0f}h")

    print("\nduplicate timestamps")
    dupes = df.groupby("station_id").apply(
        lambda g: g["timestamp"].duplicated().sum(), include_groups=False
    )
    dupes = dupes[dupes > 0]
    print("(none)" if len(dupes) == 0 else dupes.rename("duplicates").to_string())

    print("\nsky condition values")
    print(df["sky_condition"].value_counts().head(10))

    print("\nall columns")
    print(list(df.columns))


if __name__ == "__main__":
    main()
