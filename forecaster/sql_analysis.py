"""Small SQL checks over the cleaned weather database."""

import sqlite3
import pandas as pd

DB_PATH = "weather.db"


def run(conn, title, sql):
    print(f"\n{title}")
    print("sql:")
    for line in sql.strip().split("\n"):
        print(f"  {line}")
    df = pd.read_sql(sql, conn)
    print(f"\nresult ({len(df)} rows):")
    print(df.to_string(index=False))
    return df


def main():
    conn = sqlite3.connect(DB_PATH)

    run(conn, "top 10 hottest hours ever recorded",
        """
        SELECT timestamp, temp_f, humidity, wind_speed_mph
        FROM weather
        WHERE temp_f IS NOT NULL
        ORDER BY temp_f DESC
        LIMIT 10;
        """)

    run(conn, "coldest hour each year",
        """
        SELECT
          strftime('%Y', timestamp) AS year,
          MIN(temp_f)               AS min_temp_f
        FROM weather
        WHERE temp_f IS NOT NULL
        GROUP BY year
        ORDER BY year;
        """)

    run(conn, "monthly weather profile (avg temp, humidity, rain days)",
        """
        SELECT
          strftime('%m', timestamp)         AS month,
          ROUND(AVG(temp_f), 1)             AS avg_temp,
          ROUND(AVG(humidity), 1)           AS avg_humidity,
          ROUND(SUM(precip_mm), 1)          AS total_precip_mm,
          SUM(CASE WHEN precip_mm > 0 THEN 1 ELSE 0 END) AS rainy_hours,
          COUNT(*)                          AS total_hours
        FROM weather
        GROUP BY month
        ORDER BY month;
        """)

    run(conn, "years where it rained more than 400mm total",
        """
        SELECT
          strftime('%Y', timestamp) AS year,
          ROUND(SUM(precip_mm), 1)  AS total_precip_mm,
          COUNT(*)                  AS hours_recorded
        FROM weather
        WHERE precip_mm IS NOT NULL
        GROUP BY year
        HAVING SUM(precip_mm) > 400
        ORDER BY total_precip_mm DESC;
        """)

    run(conn, "hottest day in each year (using ROW_NUMBER)",
        """
        WITH daily_max AS (
          SELECT
            DATE(timestamp)            AS day,
            strftime('%Y', timestamp)  AS year,
            MAX(temp_f)                AS daily_high
          FROM weather
          WHERE temp_f IS NOT NULL
          GROUP BY day
        ),
        ranked AS (
          SELECT
            year, day, daily_high,
            ROW_NUMBER() OVER (PARTITION BY year ORDER BY daily_high DESC) AS rk
          FROM daily_max
        )
        SELECT year, day, ROUND(daily_high, 1) AS daily_high_f
        FROM ranked
        WHERE rk = 1
        ORDER BY year;
        """)

    run(conn, "day-over-day temp change (using LAG)",
        """
        WITH daily AS (
          SELECT
            DATE(timestamp)            AS day,
            ROUND(AVG(temp_f), 2)      AS avg_temp
          FROM weather
          WHERE temp_f IS NOT NULL
          GROUP BY day
        )
        SELECT
          day,
          avg_temp,
          LAG(avg_temp, 1) OVER (ORDER BY day) AS prev_day_temp,
          ROUND(avg_temp - LAG(avg_temp, 1) OVER (ORDER BY day), 2) AS change
        FROM daily
        ORDER BY ABS(avg_temp - LAG(avg_temp, 1) OVER (ORDER BY day)) DESC
        LIMIT 10;
        """)

    run(conn, "7-day rolling avg temperature",
        """
        WITH daily AS (
          SELECT DATE(timestamp) AS day, AVG(temp_f) AS avg_temp
          FROM weather WHERE temp_f IS NOT NULL
          GROUP BY day
        )
        SELECT
          day,
          ROUND(avg_temp, 2) AS daily_avg,
          ROUND(AVG(avg_temp) OVER (
            ORDER BY day
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
          ), 2) AS rolling_7d_avg
        FROM daily
        ORDER BY day
        LIMIT 15;
        """)

    run(conn, "same calendar day year-over-year comparison",
        """
        SELECT
          strftime('%m-%d', a.timestamp) AS month_day,
          ROUND(AVG(CASE WHEN strftime('%Y', a.timestamp)='2023' THEN a.temp_f END), 1) AS temp_2023,
          ROUND(AVG(CASE WHEN strftime('%Y', a.timestamp)='2024' THEN a.temp_f END), 1) AS temp_2024,
          ROUND(AVG(CASE WHEN strftime('%Y', a.timestamp)='2025' THEN a.temp_f END), 1) AS temp_2025
        FROM weather a
        WHERE strftime('%Y', a.timestamp) IN ('2023','2024','2025')
          AND a.temp_f IS NOT NULL
        GROUP BY month_day
        ORDER BY month_day
        LIMIT 12;
        """)

    run(conn, "data completeness audit by year",
        """
        SELECT
          strftime('%Y', timestamp) AS year,
          COUNT(*)                                                    AS total_rows,
          SUM(CASE WHEN temp_f       IS NULL THEN 1 ELSE 0 END)       AS null_temp,
          SUM(CASE WHEN humidity     IS NULL THEN 1 ELSE 0 END)       AS null_humidity,
          SUM(CASE WHEN pressure_hpa IS NULL THEN 1 ELSE 0 END)       AS null_pressure,
          SUM(CASE WHEN wind_dir     IS NULL THEN 1 ELSE 0 END)       AS null_wind_dir,
          ROUND(100.0 * SUM(CASE WHEN temp_f IS NULL THEN 1 ELSE 0 END)
                      / COUNT(*), 2)                                  AS pct_null_temp
        FROM weather
        GROUP BY year
        ORDER BY year;
        """)

    run(conn, "summer (jun-aug) average temp by year",
        """
        SELECT
          strftime('%Y', timestamp)        AS year,
          ROUND(AVG(temp_f), 2)            AS avg_summer_temp_f,
          ROUND(MAX(temp_f), 1)            AS max_summer_temp_f,
          COUNT(DISTINCT DATE(timestamp))  AS days_recorded
        FROM weather
        WHERE strftime('%m', timestamp) IN ('06', '07', '08')
          AND temp_f IS NOT NULL
        GROUP BY year
        HAVING COUNT(DISTINCT DATE(timestamp)) > 80
        ORDER BY year;
        """)

    conn.close()
    print("\ndone.")


if __name__ == "__main__":
    main()
