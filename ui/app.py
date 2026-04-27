"""
app.py — ScribeCheck Gradio Web Interface.

Features:
  - Upload handwritten image and enter reference text
  - Preprocessed image display with CLAHE + adaptive thresholding
  - Image quality assessment (contrast, sharpness, intensity)
  - OCR transcription via TrOCR
  - CER and WER metrics
  - Hybrid similarity scoring (Levenshtein + BLEU + Cosine)
  - Confidence label (High / Medium / Low / Very Low)
  - Adjustable metric weight sliders
  - Error handling with informative messages

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
from src.preprocessing import pil_to_cv2, cv2_to_pil, preprocess_image, assess_image_quality

print("Loading TrOCR model...")
processor, model, device = load_model("microsoft/trocr-base-handwritten")
print("Ready!\n")


def get_confidence_label(score):
    if score >= 0.90: return "High Confidence"
    elif score >= 0.70: return "Medium Confidence"
    elif score >= 0.50: return "Low Confidence"
    else: return "Very Low Confidence"


def evaluate_handwriting(image, reference_text, w_lev, w_bleu, w_cos):
    if image is None:
        return None, "No image uploaded.", "", "", "", "", "", "", ""
    if not reference_text or not reference_text.strip():
        return None, "Please enter reference text.", "", "", "", "", "", "", ""
    try:
        pil_image = Image.fromarray(image) if isinstance(image, np.ndarray) else image
        pil_image = pil_image.convert("RGB")

        cv2_img = pil_to_cv2(pil_image)
        quality = assess_image_quality(cv2_img)
        preprocessed_pil = cv2_to_pil(preprocess_image(cv2_img))
        quality_str = f"Contrast: {quality['contrast']} | Sharpness: {quality['sharpness']} | Intensity: {quality['mean_intensity']}"

        transcription = recognize_text(pil_image, processor, model, device)
        s_cer = compute_cer(transcription, reference_text)
        s_wer = compute_wer(transcription, reference_text)

        total_w = w_lev + w_bleu + w_cos
        if total_w == 0: total_w = 1.0
        weights = {"levenshtein": w_lev / total_w, "bleu": w_bleu / total_w, "cosine": w_cos / total_w}
        sim = compute_hybrid_score(transcription, reference_text, weights=weights, return_breakdown=True)
        confidence = get_confidence_label(sim['combined_score'])

        return (
            preprocessed_pil, transcription,
            f"{s_cer:.4f} ({s_cer * 100:.2f}%)", f"{s_wer:.4f} ({s_wer * 100:.2f}%)",
            f"{sim['levenshtein']:.4f}", f"{sim['bleu']:.4f}", f"{sim['cosine']:.4f}",
            f"{sim['combined_score']:.4f} — {confidence}", quality_str,
        )
    except Exception as e:
        return None, f"Error: {str(e)}", "", "", "", "", "", "", ""


with gr.Blocks(title="ScribeCheck", theme=gr.themes.Soft()) as demo:
    gr.Markdown(
        "# ScribeCheck — Handwritten Text Evaluation System\n"
        "Upload a handwritten text image and enter the expected reference text. "
        "The system transcribes the handwriting using TrOCR and evaluates similarity "
        "using a hybrid scoring system (Levenshtein + BLEU + Cosine)."
    )
    with gr.Row():
        with gr.Column():
            gr.Markdown("### Input")
            image_input = gr.Image(type="pil", label="Upload Handwritten Image")
            reference_input = gr.Textbox(label="Reference Text", placeholder="Enter the expected text here...", lines=3)
            gr.Markdown("#### Similarity Metric Weights")
            gr.Markdown("Adjust how much each metric contributes to the combined score.")
            with gr.Row():
                w_lev = gr.Slider(0, 1, value=0.35, step=0.05, label="Levenshtein (character)")
                w_bleu = gr.Slider(0, 1, value=0.30, step=0.05, label="BLEU (word/phrase)")
                w_cos = gr.Slider(0, 1, value=0.35, step=0.05, label="Cosine (semantic)")
            run_btn = gr.Button("Run Evaluation", variant="primary", size="lg")
        with gr.Column():
            gr.Markdown("### Results")
            preprocessed_output = gr.Image(label="Preprocessed Image", type="pil")
            quality_output = gr.Textbox(label="Image Quality Assessment", interactive=False)
            transcription_out = gr.Textbox(label="OCR Transcription", interactive=False)
            gr.Markdown("#### OCR Quality")
            with gr.Row():
                cer_out = gr.Textbox(label="CER (Character Error Rate)", interactive=False)
                wer_out = gr.Textbox(label="WER (Word Error Rate)", interactive=False)
            gr.Markdown("#### Similarity Breakdown")
            with gr.Row():
                lev_out = gr.Textbox(label="Levenshtein", interactive=False)
                bleu_out = gr.Textbox(label="BLEU", interactive=False)
                cos_out = gr.Textbox(label="Cosine", interactive=False)
            combined_out = gr.Textbox(label="Combined Score & Confidence", interactive=False)
    run_btn.click(
        fn=evaluate_handwriting,
        inputs=[image_input, reference_input, w_lev, w_bleu, w_cos],
        outputs=[preprocessed_output, transcription_out, cer_out, wer_out,
                 lev_out, bleu_out, cos_out, combined_out, quality_output],
    )
    gr.Markdown(
        "---\n**Note:** This model is trained on the IAM Handwriting Database (English, clean backgrounds). "
        "Performance may vary on handwriting with different styles, languages, or backgrounds."
    )

if __name__ == "__main__":
    demo.launch(share=False)
