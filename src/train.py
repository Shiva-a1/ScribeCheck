"""
train.py — Fine-tune TrOCR on the IAM Handwriting Dataset.

Usage: python src/train.py
"""

import os, json, torch
import numpy as np
import matplotlib.pyplot as plt
from torch.utils.data import Dataset, DataLoader
from transformers import TrOCRProcessor, VisionEncoderDecoderModel
from datasets import load_dataset
from tqdm import tqdm


class IAMDataset(Dataset):
    def __init__(self, hf_dataset, processor, max_target_length=128):
        self.dataset = hf_dataset
        self.processor = processor
        self.max_target_length = max_target_length
    def __len__(self):
        return len(self.dataset)
    def __getitem__(self, idx):
        sample = self.dataset[idx]
        image = sample["image"].convert("RGB")
        text = sample["text"]
        pixel_values = self.processor(images=image, return_tensors="pt").pixel_values.squeeze()
        labels = self.processor.tokenizer(
            text, padding="max_length", max_length=self.max_target_length, truncation=True
        ).input_ids
        labels = [l if l != self.processor.tokenizer.pad_token_id else -100 for l in labels]
        return {"pixel_values": pixel_values, "labels": torch.tensor(labels)}


def train_model(num_train=500, num_val=100, epochs=3, batch_size=4, lr=5e-5,
                output_dir="models/trocr-finetuned", results_dir="results"):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(results_dir, exist_ok=True)
    print(f"Training device: {device}")

    dataset = load_dataset("Teklia/IAM-line", split="train").shuffle(seed=42)
    train_data = dataset.select(range(num_train))
    val_data = dataset.select(range(num_train, num_train + num_val))

    processor = TrOCRProcessor.from_pretrained("microsoft/trocr-base-handwritten")
    model = VisionEncoderDecoderModel.from_pretrained("microsoft/trocr-base-handwritten").to(device)
    model.config.decoder_start_token_id = processor.tokenizer.cls_token_id
    model.config.pad_token_id = processor.tokenizer.pad_token_id

    train_loader = DataLoader(IAMDataset(train_data, processor), batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(IAMDataset(val_data, processor), batch_size=batch_size)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr)

    train_losses, val_losses = [], []
    for epoch in range(epochs):
        model.train()
        el, nb = 0.0, 0
        for batch in tqdm(train_loader, desc=f"Epoch {epoch+1}/{epochs}"):
            outputs = model(pixel_values=batch["pixel_values"].to(device), labels=batch["labels"].to(device))
            outputs.loss.backward(); optimizer.step(); optimizer.zero_grad()
            el += outputs.loss.item(); nb += 1
        train_losses.append(el / nb)
        model.eval()
        vl, vb = 0.0, 0
        with torch.no_grad():
            for batch in val_loader:
                outputs = model(pixel_values=batch["pixel_values"].to(device), labels=batch["labels"].to(device))
                vl += outputs.loss.item(); vb += 1
        val_losses.append(vl / vb)
        print(f"  Epoch {epoch+1}: Train={train_losses[-1]:.4f}, Val={val_losses[-1]:.4f}")

    model.save_pretrained(output_dir)
    processor.save_pretrained(output_dir)
    with open(os.path.join(results_dir, "training_metrics.json"), "w") as f:
        json.dump({"train_losses": train_losses, "val_losses": val_losses, "epochs": epochs}, f, indent=2)
    print(f"Model saved to {output_dir}")


if __name__ == "__main__":
    train_model()
