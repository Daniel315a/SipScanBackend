from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional
import os, boto3

AWS_REGION = os.getenv("AWS_REGION", "us-east-2")

class OCRProvider(ABC):
    @abstractmethod
    def extract_text_from_s3(self, *, bucket: str, key: str) -> str: ...

_textract = None
def _textract_client():
    global _textract
    if _textract is None:
        _textract = boto3.client("textract", region_name=AWS_REGION)
    return _textract

class TextractProvider(OCRProvider):
    def __init__(self, mode: str = "detect_text"):
        self.mode = mode

    def extract_text_from_s3(self, *, bucket: str, key: str) -> str:
        if self.mode == "analyze_expense":
            resp = _textract_client().analyze_expense(
                Document={"S3Object": {"Bucket": bucket, "Name": key}}
            )
            lines: list[str] = []
            for doc in resp.get("ExpenseDocuments", []):
                lines.append("[Summary]")
                for sf in doc.get("SummaryFields", []):
                    key = (sf.get("Type", {}).get("Text")
                           or sf.get("LabelDetection", {}).get("Text") or "").strip()
                    val = (sf.get("ValueDetection", {}) or {}).get("Text") or ""
                    if key or val:
                        lines.append(f"{key}: {val}".strip(": "))
                for grp in doc.get("LineItemGroups", []):
                    lines.append("[Items]")
                    for item in grp.get("LineItems", []):
                        kv = {}
                        for ef in item.get("LineItemExpenseFields", []):
                            k = (ef.get("Type", {}).get("Text")
                                 or ef.get("LabelDetection", {}).get("Text") or "").strip()
                            v = (ef.get("ValueDetection", {}) or {}).get("Text") or ""
                            if k or v:
                                kv[k or "FIELD"] = v
                        if kv:
                            lines.append(", ".join(f"{k}={v}" for k, v in kv.items()))
            return "\n".join(lines).strip()
        else:
            resp = _textract_client().detect_document_text(
                Document={"S3Object": {"Bucket": bucket, "Name": key}}
            )
            lines = [b["Text"] for b in resp.get("Blocks", [])
                     if b.get("BlockType") == "LINE" and "Text" in b]
            return "\n".join(lines)

def get_ocr_provider(mode: Optional[str] = None) -> OCRProvider:
    selected = mode or os.getenv("OCR_MODE", "detect_text")
    return TextractProvider(mode=selected)