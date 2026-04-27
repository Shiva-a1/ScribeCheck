# ScribeCheck — Handwritten Text Evaluation System Using OCR

A deep learning pipeline that transcribes handwritten text using TrOCR and evaluates it against reference text using hybrid similarity scoring.

## Overview

ScribeCheck takes a handwritten text image, transcribes it using Microsoft's TrOCR model (pre-trained on the IAM Handwriting Database), and compares the transcription against reference text using a hybrid similarity system. The system combines three complementary metrics — Levenshtein distance (character-level accuracy), BLEU score (word/phrase overlap), and cosine similarity over sentence embeddings (semantic meaning) — into a single weighted evaluation score.

**Target applications:** Educational grading, document verification, handwritten form processing.

**Pipeline:** Image → Preprocessing (CLAHE + Adaptive Thresholding) → TrOCR OCR → CER/WER Evaluation → Hybrid Similarity Scoring → Combined Score (0–1) → Gradio UI

## Performance Results

| Metric | Value (200 samples) |
|--------|:---:|
| Mean CER | 0.70% |
| Mean WER | 2.49% |
| Perfect transcriptions | 175 / 200 (87.5%) |
| Mean Combined Similarity | 0.9738 |
| Published Baseline CER | ~4.4% |

## Repository Structure

```
ScribeCheck/
├── notebooks/
│   └── train_and_evaluate.ipynb   # Master notebook — runs entire pipeline
├── src/
│   ├── preprocessing.py           # Image preprocessing (CLAHE, adaptive thresh)
│   ├── ocr_engine.py              # TrOCR inference (CUDA/MPS/CPU)
│   ├── similarity.py              # Hybrid similarity scoring
│   ├── evaluation.py              # CER, WER, cascade analysis
│   └── train.py                   # Fine-tuning script (CUDA only)
├── ui/
│   └── app.py                     # Gradio web interface
├── results/                       # Generated plots and metrics
├── docs/                          # Diagrams, screenshots, report
├── data/
├── requirements.txt
└── README.md
```

## Installation

```bash
git clone https://github.com/YOUR_USERNAME/ScribeCheck.git
cd ScribeCheck
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -c "import nltk; nltk.download('punkt'); nltk.download('punkt_tab')"
```

## How to Run

### Master Notebook (runs the complete pipeline)
```bash
jupyter notebook notebooks/train_and_evaluate.ipynb
```
Runs end-to-end: dataset loading → data exploration → OCR inference → CER/WER evaluation → hybrid similarity scoring → cascade failure analysis → weight sensitivity analysis → difficulty stratification → saves all results → launches Gradio UI.

### Standalone Gradio UI
```bash
python ui/app.py
```

### Fine-Tuning (CUDA or Colab only)
```bash
python src/train.py
```

## Hardware Compatibility

| Feature | CUDA (NVIDIA) | MPS (Apple Silicon) | CPU |
|---------|:---:|:---:|:---:|
| Inference | ✅ | ✅ | ✅ |
| Fine-tuning | ✅ | ❌ | ✅ (slow) |
| Gradio UI | ✅ | ✅ | ✅ |

**MPS Note:** TrOCR fine-tuning is incompatible with Apple Silicon MPS due to a PyTorch backward-pass limitation (non-contiguous tensor `view` operations in attention layers during gradient computation). Inference works perfectly on MPS. The pre-trained model is already fine-tuned on IAM by Microsoft (~4.4% CER baseline).

## Known Issues

- MPS incompatible with TrOCR training backward pass
- Model does not generalize well to non-IAM handwriting (different styles, lined paper, etc.)
- Similarity weights use defaults (0.35/0.30/0.35); labeled test set for tuning is future work
- Very cursive or low-contrast handwriting produces higher CER
- Short texts (<20 chars) have disproportionately higher CER due to denominator effect

## Dataset

**IAM Handwriting Database** via HuggingFace Datasets (`Teklia/IAM-line`) — line-level handwritten English text images from 650+ writers. No manual download required.

## Author

**Shivanshu Ade**
Deep Learning — Semester Project, Spring 2026
