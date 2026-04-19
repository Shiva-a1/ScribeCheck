# ScribeCheck — Handwritten Text Evaluation System Using OCR

A deep learning pipeline that transcribes handwritten text using TrOCR and evaluates it against reference text using hybrid similarity scoring.

## Project Overview

ScribeCheck takes a handwritten text image as input, transcribes it using Microsoft's TrOCR (pre-trained on the IAM Handwriting Database), and compares the transcription against reference text to produce an evaluation score. Designed for educational grading, document verification, and handwritten form processing.

**Pipeline:** Image → Preprocessing (OpenCV) → TrOCR OCR → CER/WER Evaluation → Hybrid Similarity (Levenshtein + BLEU + Cosine) → Combined Score → Gradio UI

## Repository Structure

```
ScribeCheck/
├── notebooks/
│   └── train_and_evaluate.ipynb   # Master notebook — runs entire pipeline
├── src/
│   ├── preprocessing.py           # Image preprocessing (OpenCV)
│   ├── ocr_engine.py              # TrOCR inference
│   ├── similarity.py              # Hybrid similarity scoring
│   ├── evaluation.py              # CER, WER, cascade analysis
│   └── train.py                   # Standalone training script (CUDA only)
├── ui/
│   └── app.py                     # Gradio web interface
├── results/                       # Generated plots and metrics
├── docs/                          # Architecture diagrams, report, screenshots
├── data/                          # Dataset cache
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

### Option 1: Master Notebook (recommended)
```bash
jupyter notebook notebooks/train_and_evaluate.ipynb
```
Runs everything top to bottom: data loading → model inference → CER/WER evaluation → similarity scoring → cascade analysis → saves results → launches Gradio UI.

### Option 2: Standalone Gradio UI
```bash
python ui/app.py
```

### Option 3: Training (CUDA / Colab only)
```bash
python src/train.py
```

## Hardware Compatibility

| Feature | CUDA (NVIDIA) | MPS (Apple Silicon) | CPU |
|---------|:---:|:---:|:---:|
| Inference | ✅ | ✅ | ✅ |
| Fine-tuning | ✅ | ❌ | ✅ (slow) |
| Gradio UI | ✅ | ✅ | ✅ |

**MPS Note:** TrOCR fine-tuning is incompatible with Apple Silicon MPS due to a PyTorch backward-pass limitation (non-contiguous tensor `view` operations in the attention layers). Inference works perfectly on MPS. The pre-trained `trocr-base-handwritten` is already fine-tuned on IAM by Microsoft (~4.4% CER), so the full evaluation pipeline runs without additional training. For custom fine-tuning, use Google Colab (free T4 GPU).

## Current Results

After running the notebook, results are saved to `results/`:
- `sample_images.png` — dataset samples
- `text_length_distributions.png` — text statistics
- `cer_wer_distributions.png` — CER and WER histograms
- `test_predictions_visual.png` — predictions vs ground truth
- `metrics_correlation.png` — correlation heatmap
- `cer_vs_similarity.png` — CER vs combined score scatter
- `cascade_analysis.png` — similarity stratified by OCR quality
- `final_results.json` — all metrics
- `test_results.csv` — per-sample results

## Dataset

**IAM Handwriting Database** via HuggingFace (`Teklia/IAM-line`) — 10,373 line images, 650+ writers. No manual download needed.

## Author

**Shivanshu Ade**
Email - shivansh.ade@ufl.edu
Deep Learning — Semester Project, Spring 2026
