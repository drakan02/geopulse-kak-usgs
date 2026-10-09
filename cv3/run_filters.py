import argparse
import uuid

import numpy as np
import pandas as pd

from psycopg.types.json import Jsonb

from cv3.db import get_connection
from cv3.filters import apply_filter


METHODS = [
    "median",
    "butter_lowpass",
    "butter_bandpass",
    "wavelet",
    "kalman",
]


def load_signal(
    conn,
    station,
    channel,
    start,
    end
):
    query = """
        SELECT
            time_utc,
            original_value,
            quality_flag
        FROM analytics.vw_signal
        WHERE station_code = %s
          AND channel_code = %s
          AND time_utc >= %s
          AND time_utc < %s
        ORDER BY time_utc
    """

    rows = conn.execute(
        query,
        (
            station,
            channel,
            start,
            end,
        )
    ).fetchall()

    df = pd.DataFrame(
        rows,
        columns=[
            "time_utc",
            "original_value",
            "quality_flag",
        ]
    )

    if df.empty:
        raise ValueError(
            "Khong tim thay du lieu."
        )

    if df["original_value"].isna().any():
        raise ValueError(
            "Du lieu co NULL, chua the filter truc tiep."
        )

    return df


def calculate_metrics(
    original,
    filtered
):
    residual = original - filtered

    rmse = np.sqrt(
        np.mean(
            residual ** 2
        )
    )

    mae = np.mean(
        np.abs(residual)
    )

    roughness_before = np.std(
        np.diff(original)
    )

    roughness_after = np.std(
        np.diff(filtered)
    )

    correlation = np.corrcoef(
        original,
        filtered
    )[0, 1]

    return {
        "rmse_change": float(rmse),
        "mae_change": float(mae),
        "diff_std_before": float(
            roughness_before
        ),
        "diff_std_after": float(
            roughness_after
        ),
        "correlation": float(
            correlation
        ),
    }


def save_filter_result(
    conn,
    df,
    station,
    channel,
    method,
    filtered,
    parameters
):
    run_id = uuid.uuid4()

    original = (
        df["original_value"]
        .to_numpy(dtype=float)
    )

    metrics = calculate_metrics(
        original,
        filtered
    )

    conn.execute(
        """
        INSERT INTO analytics.model_run
        (
            run_id,
            station_code,
            channel_code,
            run_kind,
            method,
            input_series,
            parameters,
            metrics,
            train_start,
            train_end
        )
        VALUES
        (
            %s,
            %s,
            %s,
            'filter',
            %s,
            'analytics.vw_signal',
            %s,
            %s,
            %s,
            %s
        )
        """,
        (
            run_id,
            station,
            channel,
            method,
            Jsonb(parameters),
            Jsonb(metrics),
            df["time_utc"].iloc[0],
            df["time_utc"].iloc[-1],
        )
    )

    with conn.cursor().copy(
        """
        COPY analytics.filtered_series
        (
            time_utc,
            run_id,
            station_code,
            channel_code,
            filtered_value,
            quality_flag
        )
        FROM STDIN
        """
    ) as copy:

        for time_utc, value, quality_flag in zip(
            df["time_utc"],
            filtered,
            df["quality_flag"]
        ):
            copy.write_row(
                (
                    time_utc,
                    run_id,
                    station,
                    channel,
                    float(value),
                    int(quality_flag),
                )
            )

    return run_id, metrics


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--station",
        default="KAK"
    )

    parser.add_argument(
        "--channel",
        default="X"
    )

    parser.add_argument(
        "--start",
        default="2024-01-01"
    )

    parser.add_argument(
        "--end",
        default="2024-01-02"
    )

    parser.add_argument(
        "--method",
        choices=METHODS + ["all"],
        default="median"
    )

    args = parser.parse_args()

    if args.method == "all":
        methods = METHODS
    else:
        methods = [
            args.method
        ]

    with get_connection() as conn:

        df = load_signal(
            conn,
            args.station,
            args.channel,
            args.start,
            args.end
        )

        print(
            f"Loaded {len(df)} samples "
            f"from {args.station}/{args.channel}"
        )

        original = (
            df["original_value"]
            .to_numpy(dtype=float)
        )

        for method in methods:

            print(
                f"\nRunning: {method}"
            )

            filtered, parameters = apply_filter(
                method,
                original
            )

            run_id, metrics = save_filter_result(
                conn,
                df,
                args.station,
                args.channel,
                method,
                filtered,
                parameters
            )

            print(
                f"Saved run_id: {run_id}"
            )

            print(
                f"Parameters: {parameters}"
            )

            print(
                f"Metrics: {metrics}"
            )

        conn.commit()

    print(
        "\nCompleted successfully."
    )


if __name__ == "__main__":
    main()