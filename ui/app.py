"""
app.py — Gradio web interface for ScribeCheck.
Launch: python ui/app.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import gradio as gr
import numpy as np
from PIL import Image
from src.ocr_engine import load_model, recognize_text
from src.similarity import compute_hybrid_score
from src.evaluation import compute_cer, compute_wer

print("Loading TrOCR model...")
processor, model, device = load_model("microsoft/trocr-base-handwritten")
print("Ready!\n")


def evaluate_handwriting(image, reference_text, w_lev, w_bleu, w_cos):
    if image is None:
        return "No image provided.", "", "", "", "", "", ""
    if not reference_text or not reference_text.strip():
        return "Please enter reference text.", "", "", "", "", "", ""

    pil_image = Image.fromarray(image) if isinstance(image, np.ndarray) else image
    pil_image = pil_image.convert("RGB")

    transcription = recognize_text(pil_image, processor, model, device)
    s_cer = compute_cer(transcription, reference_text)
    s_wer = compute_wer(transcription, reference_text)

    total_w = w_lev + w_bleu + w_cos
    if total_w == 0:
        total_w = 1.0
    weights = {"levenshtein": w_lev / total_w, "bleu": w_bleu / total_w, "cosine": w_cos / total_w}
    sim = compute_hybrid_score(transcription, reference_text, weights=weights, return_breakdown=True)

    return (
        transcription,
        f"{s_cer:.4f} ({s_cer * 100:.2f}%)",
        f"{s_wer:.4f} ({s_wer * 100:.2f}%)",
        f"{sim['levenshtein']:.4f}",
        f"{sim['bleu']:.4f}",
        f"{sim['cosine']:.4f}",
        f"{sim['combined_score']:.4f}",
    )


with gr.Blocks(title="ScribeCheck", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# ScribeCheck — Handwritten Text Evaluation\nUpload a handwritten image and enter reference text to evaluate.")
    with gr.Row():
        with gr.Column():
            gr.Markdown("### Input")
            image_input = gr.Image(type="pil", label="Upload Handwritten Image")
            reference_input = gr.Textbox(label="Reference Text", placeholder="Enter expected text...", lines=3)
            gr.Markdown("#### Metric Weights")
            with gr.Row():
                w_lev = gr.Slider(0, 1, value=0.35, step=0.05, label="Levenshtein")
                w_bleu = gr.Slider(0, 1, value=0.30, step=0.05, label="BLEU")
                w_cos = gr.Slider(0, 1, value=0.35, step=0.05, label="Cosine")
            run_btn = gr.Button("Run Evaluation", variant="primary")
        with gr.Column():
            gr.Markdown("### Results")
            transcription_out = gr.Textbox(label="OCR Transcription", interactive=False)
            with gr.Row():
                cer_out = gr.Textbox(label="CER", interactive=False)
                wer_out = gr.Textbox(label="WER", interactive=False)
            gr.Markdown("#### Similarity Breakdown")
            with gr.Row():
                lev_out = gr.Textbox(label="Levenshtein", interactive=False)
                bleu_out = gr.Textbox(label="BLEU", interactive=False)
                cos_out = gr.Textbox(label="Cosine", interactive=False)
            combined_out = gr.Textbox(label="Combined Score (0-1)", interactive=False)

    run_btn.click(
        fn=evaluate_handwriting,
        inputs=[image_input, reference_input, w_lev, w_bleu, w_cos],
        outputs=[transcription_out, cer_out, wer_out, lev_out, bleu_out, cos_out, combined_out],
    )

if __name__ == "__main__":
    demo.launch(share=False)
