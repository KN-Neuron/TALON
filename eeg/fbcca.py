"""FBCCA classifier migrated from the supplied TaaLON project.

The mathematical pipeline intentionally preserves the source implementation:
- DC removal per channel
- five Chebyshev-I filter-bank subbands
- five harmonics
- sine + cosine reference signals
- sklearn CCA(n_components=1, max_iter=1000, scale=True)
- squared canonical correlation
- filter-bank weights w(n) = n^-2 + 0.25
- argmax classification

Only project-specific imports were removed so this module can be used by the
KNeuron SSVEP sidecar independently of BrainAccess hardware.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from scipy.signal import cheb1ord, cheby1, sosfiltfilt
from sklearn.cross_decomposition import CCA

N_HARMONICS = 5

FILTER_BANK = [
    (6, 90, 4, 100),
    (14, 90, 10, 100),
    (22, 90, 16, 100),
    (30, 90, 24, 100),
    (38, 90, 32, 100),
]


def make_reference(
    frequency: float,
    n_samples: int,
    fs: float,
    n_harmonics: int = N_HARMONICS,
) -> np.ndarray:
    t = np.arange(n_samples) / fs

    references: list[np.ndarray] = []

    for harmonic in range(1, n_harmonics + 1):
        phase = 2 * np.pi * harmonic * frequency * t
        references.append(np.sin(phase))
        references.append(np.cos(phase))

    return np.column_stack(references)


def make_filter(
    pass_low: float,
    pass_high: float,
    stop_low: float,
    stop_high: float,
    fs: float,
):
    nyquist = fs / 2

    wp = [
        pass_low / nyquist,
        pass_high / nyquist,
    ]

    ws = [
        stop_low / nyquist,
        stop_high / nyquist,
    ]

    order, wn = cheb1ord(
        wp=wp,
        ws=ws,
        gpass=3,
        gstop=40,
    )

    return cheby1(
        N=order,
        rp=0.5,
        Wn=wn,
        btype="bandpass",
        output="sos",
    )


@lru_cache(maxsize=8)
def filters_for_fs(fs: float):
    if fs <= 200:
        raise ValueError(
            "Zestaw filtrów TaaLON/Zhu2021 wymaga fs > 200 Hz "
            "(pasmo stop do 100 Hz)."
        )

    return tuple(
        make_filter(*band, fs=fs)
        for band in FILTER_BANK
    )


def cca_score(
    eeg: np.ndarray,
    reference: np.ndarray,
) -> float:
    x = eeg.T
    y = reference

    cca = CCA(
        n_components=1,
        max_iter=1000,
        scale=True,
    )

    x_c, y_c = cca.fit_transform(
        x,
        y,
    )

    correlation = np.corrcoef(
        x_c[:, 0],
        y_c[:, 0],
    )[0, 1]

    if not np.isfinite(correlation):
        return 0.0

    return abs(float(correlation))


def fbcca_scores(
    eeg,
    target_frequencies,
    fs: float,
) -> np.ndarray:
    eeg = np.asarray(
        eeg,
        dtype=np.float64,
    )

    target_frequencies = np.asarray(
        target_frequencies,
        dtype=float,
    )

    if eeg.ndim != 2:
        raise ValueError(
            "EEG musi mieć shape (channels, samples)."
        )

    n_channels, n_samples = eeg.shape

    if n_channels < 1:
        raise ValueError(
            "Brak kanałów EEG."
        )

    if n_samples < 100:
        raise ValueError(
            "Za mało próbek EEG."
        )

    if not np.isfinite(eeg).all():
        raise ValueError(
            "EEG zawiera NaN lub Inf."
        )

    if any(
        np.std(channel) < 1e-12
        for channel in eeg
    ):
        raise ValueError(
            "Płaski kanał EEG; sprawdź kontakt elektrody."
        )

    filters = filters_for_fs(float(fs))

    # Preserve the source project's per-channel DC removal.
    eeg = (
        eeg
        - np.mean(
            eeg,
            axis=1,
            keepdims=True,
        )
    )

    references = {
        float(freq): make_reference(
            frequency=float(freq),
            n_samples=n_samples,
            fs=fs,
        )
        for freq in target_frequencies
    }

    rho_squared = np.zeros(
        (
            len(filters),
            len(target_frequencies),
        ),
        dtype=float,
    )

    for band_index, sos in enumerate(filters):
        filtered = sosfiltfilt(
            sos,
            eeg,
            axis=1,
        )

        for freq_index, freq in enumerate(
            target_frequencies
        ):
            rho = cca_score(
                filtered,
                references[float(freq)],
            )

            rho_squared[
                band_index,
                freq_index,
            ] = rho**2

    n = np.arange(
        1,
        len(filters) + 1,
        dtype=float,
    )

    weights = (
        n**-2.0
        + 0.25
    )

    return np.dot(
        weights,
        rho_squared,
    )


def fbcca_predict(
    eeg,
    target_frequencies,
    fs: float,
):
    scores = fbcca_scores(
        eeg=eeg,
        target_frequencies=target_frequencies,
        fs=fs,
    )

    best_index = int(
        np.argmax(scores)
    )

    predicted_frequency = float(
        target_frequencies[best_index]
    )

    return (
        predicted_frequency,
        scores,
    )
