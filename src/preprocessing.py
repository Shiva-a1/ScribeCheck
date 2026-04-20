"""
preprocessing.py — Enhanced image preprocessing pipeline for handwritten text.

"""

import cv2
import numpy as np
from PIL import Image


def convert_to_grayscale(image):
    if len(image.shape) == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return image


def apply_clahe(image, clip_limit=2.0, tile_size=8):
    """Apply CLAHE for contrast enhancement — new in D3."""
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(tile_size, tile_size))
    return clahe.apply(image)


def binarize(image, method="adaptive"):
    """Binarize image. Default changed to 'adaptive' in D3 (was 'otsu' in D2)."""
    if method == "otsu":
        _, binary = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    elif method == "adaptive":
        binary = cv2.adaptiveThreshold(
            image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 10
        )
    else:
        raise ValueError(f"Unknown method: {method}")
    return binary


def denoise(image, strength=10):
    return cv2.fastNlMeansDenoising(image, h=strength)


def deskew(image):
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
    """Assess image quality metrics — new in D3."""
    gray = convert_to_grayscale(image) if len(image.shape) == 3 else image
    contrast = gray.std()
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()  # sharpness
    mean_intensity = gray.mean()
    return {
        "contrast": round(float(contrast), 2),
        "sharpness": round(float(laplacian_var), 2),
        "mean_intensity": round(float(mean_intensity), 2),
    }


def preprocess_image(image, use_clahe=True, binarize_method="adaptive"):
    """
    Full preprocessing pipeline.
    D3 changes: CLAHE enabled by default, adaptive thresholding default.
    """
    gray = convert_to_grayscale(image)
    if use_clahe:
        gray = apply_clahe(gray)
    denoised = denoise(gray)
    binary = binarize(denoised, method=binarize_method)
    corrected = deskew(binary)
    return corrected


def preprocess_comparison(image):
    """Generate side-by-side comparison of D2 vs D3 preprocessing — new in D3."""
    gray = convert_to_grayscale(image)

    # D2 pipeline: denoise -> otsu
    d2_denoised = denoise(gray)
    d2_result = binarize(d2_denoised, method="otsu")
    d2_result = deskew(d2_result)

    # D3 pipeline: CLAHE -> denoise -> adaptive
    d3_clahe = apply_clahe(gray)
    d3_denoised = denoise(d3_clahe)
    d3_result = binarize(d3_denoised, method="adaptive")
    d3_result = deskew(d3_result)

    return {
        "original": gray,
        "d2_preprocessed": d2_result,
        "d3_preprocessed": d3_result,
    }


def pil_to_cv2(pil_image):
    return np.array(pil_image.convert("RGB"))[:, :, ::-1]


def cv2_to_pil(cv2_image):
    if len(cv2_image.shape) == 2:
        return Image.fromarray(cv2_image)
    return Image.fromarray(cv2.cvtColor(cv2_image, cv2.COLOR_BGR2RGB))
