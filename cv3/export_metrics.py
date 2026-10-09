from pathlib import Path

import pandas as pd

from cv3.db import get_connection


def main():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                r.run_id,
                r.station_code,
                r.channel_code,
                r.method,
                r.train_start,
                r.train_end,
                COUNT(f.time_utc) AS n_points,
                (r.metrics ->> 'rmse_change')::double precision AS rmse,
                (r.metrics ->> 'mae_change')::double precision AS mae,
                (r.metrics ->> 'diff_std_before')::double precision AS diff_std_before,
                (r.metrics ->> 'diff_std_after')::double precision AS diff_std_after,
                (r.metrics ->> 'correlation')::double precision AS correlation
            FROM analytics.model_run r
            JOIN analytics.filtered_series f
                ON f.run_id = r.run_id
            WHERE r.run_kind = 'filter'
              AND r.train_start = '2024-01-01T00:00:00Z'
              AND r.train_end >= '2024-01-31T23:59:00Z'
              AND r.train_end < '2024-02-01T00:00:00Z'
            GROUP BY
                r.run_id,
                r.station_code,
                r.channel_code,
                r.method,
                r.train_start,
                r.train_end,
                r.metrics
            ORDER BY
                r.channel_code,
                r.method;
            """
        ).fetchall()

    columns = [
        "run_id",
        "station_code",
        "channel_code",
        "method",
        "train_start",
        "train_end",
        "n_points",
        "rmse",
        "mae",
        "diff_std_before",
        "diff_std_after",
        "correlation",
    ]

    df = pd.DataFrame(
        rows,
        columns=columns
    )

    output_dir = Path("cv3/results")
    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    output_file = (
        output_dir
        / "filter_metrics.csv"
    )

    df.to_csv(
        output_file,
        index=False
    )

    print(df.to_string(index=False))
    print()
    print(
        f"Da luu ket qua: {output_file}"
    )


if __name__ == "__main__":
    main()