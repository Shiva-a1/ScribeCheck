# ScribeCheck — Handwritten Text Evaluation System Using OCR

A deep learning pipeline that transcribes handwritten text using TrOCR and evaluates it against reference text using hybrid similarity scoring.

## Project Overview

ScribeCheck takes a handwritten text image, transcribes it using Microsoft's TrOCR (pre-trained on IAM Handwriting Database), and compares the transcription against reference text using a hybrid similarity system combining Levenshtein distance, BLEU score, and cosine similarity over sentence embeddings. Designed for educational grading, document verification, and form processing.

**Pipeline:** Image → Preprocessing (CLAHE + Adaptive Thresholding) -> TrOCR OCR -> CER/WER Evaluation -> Hybrid Similarity -> Combined Score -> Gradio UI

## Current Results

**Note** - D2 refers to the work I had done for Deliverable 2 of this project and D3 is further improvments which I had submitted during Deliverable 3

| Metric | D2 (50 samples) | D3 (200 samples) |
|--------|:---:|:---:|
| Mean CER | 0.72% | See results/final_results_d3.json |
| Mean WER | 2.44% | See results/final_results_d3.json |
| Mean Combined Similarity | 0.968 | See results/final_results_d3.json |
| Published Baseline CER | ~4.4% | ~4.4% |

### D3 Improvements over D2
- Evaluation expanded from 50 → 200 samples for more robust metrics
- Enhanced preprocessing with CLAHE contrast enhancement and adaptive thresholding
- Weight sensitivity analysis across 6 weight configurations
- Difficulty-stratified evaluation by text length
- Improved Gradio UI with preprocessed image display, quality assessment, and confidence labels
- Better error handling throughout the pipeline

## Repository Structure

```
ScribeCheck/
├── notebooks/
│   └── train_and_evaluate.ipynb   # Master notebook — runs entire pipeline
├── src/
│   ├── preprocessing.py           # Enhanced preprocessing (CLAHE, adaptive thresh)
│   ├── ocr_engine.py              # TrOCR inference (CUDA/MPS/CPU)
│   ├── similarity.py              # Hybrid similarity scoring
│   ├── evaluation.py              # CER, WER, cascade analysis
│   └── train.py                   # Fine-tuning script (CUDA only)
├── ui/
│   └── app.py                     # Improved Gradio interface (v2)
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
source venv/bin/activate
pip install -r requirements.txt
python -c "import nltk; nltk.download('punkt'); nltk.download('punkt_tab')"
```

## How to Run

### Master Notebook (recommended)
```bash
jupyter notebook notebooks/train_and_evaluate.ipynb
```

### Standalone Gradio UI
```bash
python ui/app.py
```

## Hardware Compatibility

| Feature | CUDA | MPS (Apple Silicon) | CPU |
|---------|:---:|:---:|:---:|
| Inference | ✅ | ✅ | ✅ |
| Fine-tuning | ✅ | ❌ | ✅ (slow) |
| Gradio UI | ✅ | ✅ | ✅ |

**MPS Note:** TrOCR fine-tuning fails on MPS due to a PyTorch backward-pass limitation. Inference works perfectly. The pre-trained model is already fine-tuned on IAM by Microsoft.

## Known Issues
- MPS (Apple Silicon) incompatible with TrOCR training backward pass
- Model does not generalize well to non-IAM handwriting (different styles, lined paper, etc.)
- Similarity weights use defaults (0.35/0.30/0.35); labeled test set for optimization is future work
- Very cursive or low-contrast handwriting produces higher CER

## Dataset

**IAM Handwriting Database** via HuggingFace (`Teklia/IAM-line`) — 10,373 line images, 650+ writers.

## Author

**Shivanshu Ade**
- Email: shivansh.ade@ufl.edu
- Applied Deep Learning, Semester Project, Spring 2026
