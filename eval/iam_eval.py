import argparse
from pathlib import Path

import jiwer

from eval import common, metrics
from shared import config, llm

parser = argparse.ArgumentParser(description="Compare Claude's handwriting reading with TrOCR on IAM line images.")
parser.add_argument("folder", help="Folder of IAM line images.")
parser.add_argument("labels", help="Tab-separated file: image file name, then the true transcription.")
parser.add_argument("--limit", type=int, default=200)
parser.add_argument("--trocr", action="store_true", help="Also run microsoft/trocr-base-handwritten (needs transformers and torch).")
args = parser.parse_args()

lines = [line.rstrip("\n").split("\t", 1) for line in open(args.labels, encoding="utf-8") if "\t" in line][: args.limit]


def claude_read(path):
    def compute():
        media = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        response = llm.claude().messages.create(
            model=config.required("CLAUDE_VISION_MODEL"), max_tokens=300, temperature=0,
            messages=[{"role": "user", "content": [
                llm.file_block(path.read_bytes(), media),
                {"type": "text", "text": "Transcribe this handwritten line exactly. Reply with the text only."},
            ]}],
        )
        return response.content[0].text.strip()
    return common.cached("iam", [path.name], compute)


truth = [text for _, text in lines]
claude = [claude_read(Path(args.folder) / name) for name, _ in lines]
claude_cer = [jiwer.cer(t, h) for t, h in zip(truth, claude)]
print("Claude CER %.3f [%.3f, %.3f]" % metrics.rate_ci(claude_cer))

if args.trocr:
    from PIL import Image
    from transformers import pipeline

    reader = pipeline("image-to-text", model="microsoft/trocr-base-handwritten")
    trocr = [reader(Image.open(Path(args.folder) / name).convert("RGB"))[0]["generated_text"] for name, _ in lines]
    trocr_cer = [jiwer.cer(t, h) for t, h in zip(truth, trocr)]
    print("TrOCR  CER %.3f [%.3f, %.3f]" % metrics.rate_ci(trocr_cer))
    gaps = [c - t for c, t in zip(claude_cer, trocr_cer)]
    print("Claude minus TrOCR %+.3f [%+.3f, %+.3f] (below zero means Claude reads better)" % metrics.rate_ci(gaps))
