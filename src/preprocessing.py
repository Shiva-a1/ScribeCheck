"""
preprocessing.py — Image preprocessing pipeline for handwritten text evaluation.

Provides binarization (Otsu and adaptive), CLAHE contrast enhancement,
denoising, deskewing, quality assessment, and pipeline comparison utilities.
"""

import cv2
import numpy as np
from PIL import Image


def convert_to_grayscale(image):
    """Convert BGR image to grayscale. Returns unchanged if already single-channel."""
    if len(image.shape) == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return image


def apply_clahe(image, clip_limit=2.0, tile_size=8):
    """Apply Contrast Limited Adaptive Histogram Equalization for local contrast enhancement."""
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(tile_size, tile_size))
    return clahe.apply(image)


def binarize(image, method="adaptive"):
    """
    Binarize a grayscale image.
    Methods: 'otsu' (global threshold) or 'adaptive' (per-region Gaussian threshold).
    """
    if method == "otsu":
        _, binary = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    elif method == "adaptive":
        binary = cv2.adaptiveThreshold(
            image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 10
        )
    else:
        raise ValueError(f"Unknown binarization method: {method}")
    return binary


def denoise(image, strength=10):
    """Apply non-local means denoising to reduce noise while preserving edges."""
    return cv2.fastNlMeansDenoising(image, h=strength)


def deskew(image):
    """Correct rotational skew using minimum area rectangle on dark pixel coordinates."""
    coords = np.column_stack(np.where(image < 128))
    if len(coords) < 10:
        return image
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    if abs(angle) > 15:
        return image
    h, w = image.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    return cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def assess_image_quality(image):
    """
    Compute image quality metrics: contrast (std dev), sharpness (Laplacian variance),
    and mean pixel intensity.
    """
    gray = convert_to_grayscale(image) if len(image.shape) == 3 else image
    return {
        "contrast": round(float(gray.std()), 2),
        "sharpness": round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 2),
        "mean_intensity": round(float(gray.mean()), 2),
    }


def preprocess_image(image, use_clahe=True, binarize_method="adaptive"):
    """
    Full preprocessing pipeline:
    Grayscale -> (optional CLAHE) -> Denoise -> Binarize -> Deskew.
    """
    gray = convert_to_grayscale(image)
    if use_clahe:
        gray = apply_clahe(gray)
    denoised = denoise(gray)
    binary = binarize(denoised, method=binarize_method)
    corrected = deskew(binary)
    return corrected


def preprocess_comparison(image):
    """
    Run both the basic pipeline (Otsu) and enhanced pipeline (CLAHE + Adaptive)
    and return all stages for visual comparison.
    """
    gray = convert_to_grayscale(image)

    # Basic pipeline
    basic_denoised = denoise(gray)
    basic_result = deskew(binarize(basic_denoised, method="otsu"))

    # Enhanced pipeline
    enhanced_clahe = apply_clahe(gray)
    enhanced_denoised = denoise(enhanced_clahe)
    enhanced_result = deskew(binarize(enhanced_denoised, method="adaptive"))

    return {"original": gray, "basic_preprocessed": basic_result, "enhanced_preprocessed": enhanced_result}


def pil_to_cv2(pil_image):
    """Convert PIL Image to OpenCV BGR numpy array."""
    return np.array(pil_image.convert("RGB"))[:, :, ::-1]


def cv2_to_pil(cv2_image):
    """Convert OpenCV numpy array to PIL Image."""
    if len(cv2_image.shape) == 2:
        return Image.fromarray(cv2_image)
    return Image.fromarray(cv2.cvtColor(cv2_image, cv2.COLOR_BGR2RGB))
