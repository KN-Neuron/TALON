# SSVEP EEG Analysis and Classification

A small collection of notebooks for exploratory analysis and classification of **Steady-State Visual Evoked Potential (SSVEP)** EEG signals.

The repository progresses from a compact calibration-free Lee2019 baseline, through advanced calibration-dependent methods, to a larger held-out participant evaluation on the Zhu2021 wearable dry-electrode dataset.

## Repository structure

```text
EDA/
├── Lee2019_SSVEP.ipynb
├── Lee2019_SSVEP_Advanced_Methods.ipynb
├── Zhu2021_SSVEP_EDA.ipynb
├── README.md
└── requirements.txt
```

## Notebooks

### `Lee2019_SSVEP.ipynb`

Primary calibration-free baseline based on `MOABB Lee2019_SSVEP`.

The notebook includes:

- dataset loading through MOABB,
- posterior-channel selection,
- time-domain EEG inspection,
- Welch PSD,
- local spectral SNR,
- standard CCA,
- FBCCA,
- per-class and confusion-matrix evaluation.

The four target frequencies are:

```text
5.45 Hz
6.67 Hz
8.57 Hz
12.00 Hz
```

Saved results from the notebook:

| Method | Accuracy | Balanced accuracy |
|---|---:|---:|
| SNR baseline | 61.90% | 61.90% |
| CCA | 95.10% | 95.10% |
| FBCCA | **97.60%** | **97.60%** |

The FBCCA result is the main calibration-free Lee2019 baseline in this repository.

---

### `Lee2019_SSVEP_Advanced_Methods.ipynb`

Advanced extensions of the Lee2019 analysis.

The notebook investigates methods that go beyond the basic calibration-free CCA/FBCCA pipeline, including:

- narrow-band CCA,
- IT-CCA,
- simplified eCCA,
- MsetCCA-inspired classification,
- TRCA,
- ensemble TRCA,
- filter-bank TRCA variants,
- subject-dependent cross-validation,
- subject-level robustness analysis,
- predefined channel-set studies,
- onset-trimming studies,
- FBCCA sensitivity analysis,
- trial-quality diagnostics.

Calibration-dependent methods are evaluated separately from the calibration-free baseline because they require participant-specific training data and answer a different methodological question.

Exploratory channel, trimming, frequency-set, and hyperparameter studies are treated as design analyses rather than independent held-out benchmarks.

---

### `Zhu2021_SSVEP_EDA.ipynb`

Generalization-oriented analysis of the **dry-electrode** portion of the Zhu et al. (2021) wearable SSVEP dataset.

Dataset characteristics used in the notebook:

| Property | Value |
|---|---:|
| Participants | 102 |
| Posterior EEG channels | 8 |
| Target frequencies | 12 |
| Released sampling rate | 250 Hz |
| Dry-electrode blocks per participant | 10 |
| Trials per block | 12 |
| Analysis window | 2.0 s |

The evaluation protocol is subject-wise:

```text
102 participants
      |
      +-- 82 development participants
      |      |
      |      +-- EDA and 12-class baselines
      |      +-- evaluate all C(12, 4) = 495 subsets
      |      +-- select four target frequencies
      |
      +-- 20 held-out participants
             |
             +-- evaluate the fixed four-class system
```

The held-out participants do not contribute to frequency selection.

The saved development run selected:

```text
10.25 Hz
13.75 Hz
14.25 Hz
14.75 Hz
```

Held-out four-class results:

| Method | Accuracy | Balanced accuracy |
|---|---:|---:|
| CCA | 82.12% | 82.12% |
| FBCCA | **83.00%** | **83.00%** |

For FBCCA, held-out participant accuracy ranges from **55% to 100%**, with a median of **86.25%**, showing substantial inter-subject variability.

## Methods

### Power spectral density

Welch PSD is used to inspect stimulation-frequency components and harmonics in the EEG spectrum.

### Local spectral SNR

A simple spectral baseline compares PSD at the candidate target frequency with neighbouring frequency bins.

### Canonical Correlation Analysis

CCA compares multichannel EEG with harmonic sine/cosine reference signals:

```text
sin(2πhft), cos(2πhft)
```

where `h` is the harmonic index.

### Filter-Bank CCA

FBCCA applies CCA in multiple subbands and combines the resulting canonical correlations using weighted scores.

For the Zhu2021 analysis, the score for candidate frequency `k` is:

```math
S_k = \sum_m w_m \rho_{k,m}^2
```

with five M3-style subbands and weights:

```math
w(m) = m^{-2} + 0.25
```

### Calibration-dependent methods

The advanced Lee2019 notebook additionally evaluates template-based and spatial-filter methods that learn participant-specific information from calibration trials. These are evaluated with subject-dependent cross-validation.

## Installation

Use Python 3.11 or newer.

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it.

Linux / macOS:

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements.txt
```

The notebooks can be opened in Jupyter Notebook, JupyterLab, or VS Code.

## Data

### Lee2019

Lee2019 is accessed through **MOABB**:

```python
from moabb.datasets import Lee2019_SSVEP
```

MOABB handles downloading and caching the dataset when required.

Documentation:

https://moabb.neurotechx.com/docs/generated/moabb.datasets.Lee2019_SSVEP.html

### Zhu2021

The Zhu2021 notebook loads the public `.mat` files directly.

Expected directory:

```text
EDA/
└── Zhu2021_Wearable_SSVEP/
    ├── S001.mat
    ├── S002.mat
    ├── ...
    └── S102.mat
```

The dataset directory should not be committed to Git.

Sources:

- Paper: https://doi.org/10.3390/s21041256
- Dataset: https://figshare.com/articles/dataset/An_Open_Dataset_for_Wearable_SSVEP-Based_Brain-Computer_Interfaces/13560281
- Dataset README: https://bci.med.tsinghua.edu.cn/upload/zhufangkun/Readme.pdf
- Stimulation mapping: https://bci.med.tsinghua.edu.cn/upload/zhufangkun/stimulation_information.pdf

## Reproducibility

For a clean run:

1. install the dependencies,
2. make the required dataset available,
3. restart the notebook kernel,
4. run all cells from top to bottom.

Some advanced analyses are computationally expensive, particularly subject-dependent TRCA-family cross-validation and large FBCCA experiments.

## Main references

1. Lin Z. et al. **Frequency recognition based on canonical correlation analysis for SSVEP-based BCIs.** *IEEE Transactions on Biomedical Engineering*.
   https://pubmed.ncbi.nlm.nih.gov/17549911/

2. Chen X. et al. **Filter bank canonical correlation analysis for implementing a high-speed SSVEP-based brain-computer interface.** *Journal of Neural Engineering*. 2015;12(4):046008.
   https://pubmed.ncbi.nlm.nih.gov/26035476/

3. Lee M.-H. et al. **EEG dataset and OpenBMI toolbox for three BCI paradigms.** *GigaScience*. 2019.
   https://doi.org/10.1093/gigascience/giz002

4. Nakanishi M. et al. **Enhancing detection of SSVEPs for a high-speed brain speller using task-related component analysis.**
   https://pubmed.ncbi.nlm.nih.gov/28436836/

5. Zhu F., Jiang L., Dong G., Gao X., Wang Y. **An Open Dataset for Wearable SSVEP-Based Brain-Computer Interfaces.** *Sensors*. 2021;21(4):1256.
   https://doi.org/10.3390/s21041256

## Notes

This repository contains offline EEG analyses and classification experiments. Reported offline classification accuracy should not be interpreted as direct evidence of real-time BCI control performance without online validation, artifact handling, confidence thresholds, and hardware testing.
