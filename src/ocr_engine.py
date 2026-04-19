"""
ocr_engine.py — TrOCR-based handwritten text recognition.
Supports CUDA, MPS (Apple Silicon), and CPU for inference.
"""

from transformers import TrOCRProcessor, VisionEncoderDecoderModel
from PIL import Image
import torch

DEFAULT_MODEL = "microsoft/trocr-base-handwritten"


def get_device():
    """Auto-detect best available device."""
    if torch.cuda.is_available():
        return "cuda"
    elif torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_model(model_name=DEFAULT_MODEL, device=None):
    if device is None:
        device = get_device()
    processor = TrOCRProcessor.from_pretrained(model_name)
    model = VisionEncoderDecoderModel.from_pretrained(model_name).to(device)
    model.eval()
    print(f"Loaded TrOCR '{model_name}' on {device}")
    return processor, model, device


def recognize_text(image, processor, model, device="cpu"):
    if image.mode != "RGB":
        image = image.convert("RGB")
    pixel_values = processor(images=image, return_tensors="pt").pixel_values.to(device)
    with torch.no_grad():
        generated_ids = model.generate(pixel_values, max_length=128)
    return processor.batch_decode(generated_ids, skip_special_tokens=True)[0]


def recognize_batch(images, processor, model, device="cpu", batch_size=8):
    predictions = []
    for i in range(0, len(images), batch_size):
        batch = [img.convert("RGB") if img.mode != "RGB" else img for img in images[i:i + batch_size]]
        pixel_values = processor(images=batch, return_tensors="pt").pixel_values.to(device)
        with torch.no_grad():
            generated_ids = model.generate(pixel_values, max_length=128)
        predictions.extend(processor.batch_decode(generated_ids, skip_special_tokens=True))
    return predictions
