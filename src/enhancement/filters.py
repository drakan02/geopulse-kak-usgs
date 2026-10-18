import numpy as np
import pywt

from scipy.ndimage import median_filter as scipy_median_filter
from scipy.signal import butter, sosfiltfilt


def prepare(values):
    data = np.asarray(values, dtype=np.float64)

    if data.ndim != 1:
        raise ValueError("Input must be one-dimensional")

    if np.isnan(data).any():
        raise ValueError("Input contains NaN")

    return data


def median_filter(values, window=5):
    data = prepare(values)

    if window % 2 == 0:
        raise ValueError("Median window must be odd")

    result = scipy_median_filter(
        data,
        size=window,
        mode="nearest"
    )

    return result, {
        "window": window
    }


def butter_lowpass(
    values,
    cutoff_cpm=1 / 30,
    sample_rate_cpm=1.0,
    order=4
):
    data = prepare(values)

    sos = butter(
        order,
        cutoff_cpm,
        btype="lowpass",
        fs=sample_rate_cpm,
        output="sos"
    )

    result = sosfiltfilt(sos, data)

    return result, {
        "type": "lowpass",
        "order": order,
        "cutoff_cpm": cutoff_cpm,
        "sample_rate_cpm": sample_rate_cpm
    }


def butter_bandpass(
    values,
    lowcut_cpm=1 / 120,
    highcut_cpm=1 / 5,
    sample_rate_cpm=1.0,
    order=4
):
    data = prepare(values)

    sos = butter(
        order,
        [lowcut_cpm, highcut_cpm],
        btype="bandpass",
        fs=sample_rate_cpm,
        output="sos"
    )

    result = sosfiltfilt(sos, data)

    return result, {
        "type": "bandpass",
        "order": order,
        "lowcut_cpm": lowcut_cpm,
        "highcut_cpm": highcut_cpm,
        "sample_rate_cpm": sample_rate_cpm
    }


def wavelet_denoise(values, wavelet="db4"):
    data = prepare(values)

    coeffs = pywt.wavedec(
        data,
        wavelet,
        mode="symmetric"
    )

    detail = coeffs[-1]

    sigma = np.median(np.abs(detail)) / 0.67448975

    threshold = sigma * np.sqrt(
        2 * np.log(len(data))
    )

    new_coeffs = [coeffs[0]]

    for coeff in coeffs[1:]:
        new_coeffs.append(
            pywt.threshold(
                coeff,
                threshold,
                mode="soft"
            )
        )

    result = pywt.waverec(
        new_coeffs,
        wavelet,
        mode="symmetric"
    )

    result = result[:len(data)]

    return result, {
        "wavelet": wavelet,
        "threshold": float(threshold),
        "level": len(coeffs) - 1
    }


def kalman_smooth(values):
    data = prepare(values)

    diff_variance = max(
        float(np.var(np.diff(data))),
        1e-6
    )

    measurement_variance = max(
        diff_variance / 2,
        1e-6
    )

    process_variance = max(
        measurement_variance * 0.05,
        1e-8
    )

    estimate = data[0]
    error_covariance = 1.0

    result = np.empty_like(data)
    result[0] = estimate

    for i in range(1, len(data)):

        predicted_estimate = estimate

        predicted_covariance = (
            error_covariance
            + process_variance
        )

        kalman_gain = (
            predicted_covariance
            / (
                predicted_covariance
                + measurement_variance
            )
        )

        estimate = (
            predicted_estimate
            + kalman_gain
            * (
                data[i]
                - predicted_estimate
            )
        )

        error_covariance = (
            (1 - kalman_gain)
            * predicted_covariance
        )

        result[i] = estimate

    return result, {
        "process_variance": process_variance,
        "measurement_variance": measurement_variance
    }


def apply_filter(method, values):

    if method == "median":
        return median_filter(values)

    if method == "butter_lowpass":
        return butter_lowpass(values)

    if method == "butter_bandpass":
        return butter_bandpass(values)

    if method == "wavelet":
        return wavelet_denoise(values)

    if method == "kalman":
        return kalman_smooth(values)

    raise ValueError(
        f"Unknown method: {method}"
    )