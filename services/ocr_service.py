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
            txt = []
            for doc in resp.get("ExpenseDocuments", []):
                for sf in doc.get("SummaryFields", []):
                    if (v := sf.get("ValueDetection", {}).get("Text")):
                        txt.append(v)
                for li in doc.get("LineItemGroups", []):
                    for item in li.get("LineItems", []):
                        for ef in item.get("LineItemExpenseFields", []):
                            if (v := ef.get("ValueDetection", {}).get("Text")):
                                txt.append(v)
            return "\n".join(txt)
        else:
            resp = _textract_client().detect_document_text(
                Document={"S3Object": {"Bucket": bucket, "Name": key}}
            )
            lines = [b["Text"] for b in resp.get("Blocks", [])
                     if b.get("BlockType") == "LINE" and "Text" in b]
            return "\n".join(lines)

def get_ocr_provider() -> OCRProvider:
    mode = os.getenv("OCR_MODE", "detect_text")
    return TextractProvider(mode=mode)
