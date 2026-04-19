"""
preprocessing.py — Image preprocessing pipeline for handwritten text.
"""

import cv2
import numpy as np
from PIL import Image


def convert_to_grayscale(image):
    if len(image.shape) == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return image


def binarize(image, method="otsu"):
    if method == "otsu":
        _, binary = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    elif method == "adaptive":
        binary = cv2.adaptiveThreshold(image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 10)
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


def preprocess_image(image):
    gray = convert_to_grayscale(image)
    denoised = denoise(gray)
    binary = binarize(denoised, method="otsu")
    corrected = deskew(binary)
    return corrected


def pil_to_cv2(pil_image):
    return np.array(pil_image.convert("RGB"))[:, :, ::-1]


def cv2_to_pil(cv2_image):
    if len(cv2_image.shape) == 2:
        return Image.fromarray(cv2_image)
    return Image.fromarray(cv2.cvtColor(cv2_image, cv2.COLOR_BGR2RGB))
