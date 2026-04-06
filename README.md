# ScribeCheck — Handwritten Text Evaluation System Using OCR

A deep learning pipeline that transcribes handwritten text using TrOCR and evaluates it against reference text using hybrid similarity scoring.

## Project Overview

ScribeCheck is an end-to-end system that takes a handwritten text image as input, transcribes it using Microsoft's TrOCR model, and compares the transcription against a reference text to produce a similarity score. The system is designed for use cases like automated exam grading, document verification, and handwritten form processing.

The pipeline has three stages:
1. **Preprocessing** — Image cleaning, binarization, and deskewing using OpenCV
2. **OCR Recognition** — Handwritten text transcription using TrOCR fine-tuned on the IAM dataset
3. **Hybrid Similarity Scoring** — Combining Levenshtein distance, BLEU score, and cosine similarity over sentence embeddings into a single weighted evaluation score

## Repository Structure (Planned)

```
ScribeCheck/
├── data/                  # Raw and processed data
├── notebooks/
│   └── setup.ipynb        # Environment setup, data loading, and exploration
├── src/                   # Source code modules
├── ui/                    # Gradio interface (upcoming)
├── results/               # Output visualizations and evaluation results
├── docs/                  # Architecture diagrams and project documentation
├── requirements.txt       # Python dependencies
└── README.md
```

## Installation and Setup

### Prerequisites
- Python 3.9 or higher
- pip package manager
- (Recommended) NVIDIA GPU with CUDA for model fine-tuning

### Steps

1. **Clone the repository**
   ```bash
   git clone https://github.com/Shiva-a1/ScribeCheck.git
   cd ScribeCheck
   ```

2. **Create a virtual environment (recommended)**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Download NLTK data (required for BLEU scoring)**
   ```python
   import nltk
   nltk.download('punkt')
   nltk.download('punkt_tab')
   ```

## How to Run the Notebook

```bash
jupyter notebook notebooks/setup.ipynb
```

The `setup.ipynb` notebook walks through:
- Verifying that the environment and all dependencies are correctly installed
- Loading the IAM Handwriting Dataset from HuggingFace
- Exploratory data analysis with summary statistics and visualizations
- Running TrOCR inference on sample handwritten images
- Computing CER (Character Error Rate) and WER (Word Error Rate) metrics
- Demonstrating the hybrid similarity scoring system
- Previewing cascade failure analysis

## Dataset

- **IAM Handwriting Database** — accessed via HuggingFace Datasets (`Teklia/IAM-line`)
- Contains handwritten English text from 650+ writers with word-level and line-level annotations
- Pre-segmented line images are used for initial development
- No manual download required cause the dataset is loaded programmatically in the notebook

## Author

**Shivanshu Ade**  
Deep Learning — Semester Project, Spring 2026  
Contact: [shivansh.ade@ufl.edu]
