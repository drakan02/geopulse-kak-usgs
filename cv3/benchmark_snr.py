from pathlib import Path

import numpy as np
import pandas as pd

from cv3.db import get_connection
from cv3.filters import apply_filter


METHODS = [
    "median",
    "butter_lowpass",
    "butter_bandpass",
    "wavelet",
    "kalman",
]


def snr_db(reference, signal):
    signal_power = np.mean(reference ** 2)
    noise_power = np.mean((signal - reference) ** 2)

    if noise_power == 0:
        return float("inf")

    return 10 * np.log10(
        signal_power / noise_power
    )


def load_signal(
    station="KAK",
    channel="X",
    start="2024-01-01",
    end="2024-01-02"
):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                time_utc,
                original_value
            FROM analytics.vw_signal
            WHERE station_code = %s
              AND channel_code = %s
              AND quality_flag = 0
              AND time_utc >= %s
              AND time_utc < %s
            ORDER BY time_utc
            """,
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
            "value"
        ]
    )

    if df.empty:
        raise ValueError(
            "Khong tim thay du lieu"
        )

    return df


def main():
    df = load_signal()

    original = df["value"].to_numpy(
        dtype=float
    )

    reference = (
        original
        - np.mean(original)
    )

    rng = np.random.default_rng(42)

    noise_std = 2.0

    noise = rng.normal(
        0,
        noise_std,
        size=len(reference)
    )

    noisy = reference + noise

    snr_before = snr_db(
        reference,
        noisy
    )

    results = []

    for method in METHODS:
        filtered, parameters = apply_filter(
            method,
            noisy
        )

        snr_after = snr_db(
            reference,
            filtered
        )

        improvement = (
            snr_after
            - snr_before
        )

        results.append({
            "method": method,
            "snr_before_db": snr_before,
            "snr_after_db": snr_after,
            "improvement_db": improvement,
        })

    result_df = pd.DataFrame(
        results
    )

    print()
    print(result_df.to_string(
        index=False
    ))

    output_dir = Path(
        "cv3/results"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    output_file = (
        output_dir
        / "snr_comparison.csv"
    )

    result_df.to_csv(
        output_file,
        index=False
    )

    print()
    print(
        f"Da luu ket qua: {output_file}"
    )


if __name__ == "__main__":
    main()