# services/erp_service.py
import os, httpx
from typing import List, Dict, Any

_ERP_DOCUMENTOS_HOST = os.getenv("ERP_DOCUMENTOS_HOST", "").rstrip("/")
_ERP_TERCEROS_HOST = os.getenv("ERP_TERCEROS_HOST", "").rstrip("/")

class ERPService:
    def __init__(self, base: str | None = None, terceros_base: str | None = None):
        if not (_host := base or _ERP_DOCUMENTOS_HOST):
            raise RuntimeError("ERP_DOCUMENTOS_HOST is required")
        if not (_t_host := terceros_base or _ERP_TERCEROS_HOST):
            raise RuntimeError("ERP_TERCEROS_HOST is required")
        self.base = _host
        self.t_base = _t_host

    def _headers(self, app) -> dict:
        token = getattr(app.state, "erp_api_token", None)
        if not token:
            raise RuntimeError("ERP API token not set")
        return {"X-Api-Token": token}

    async def get_pucs(self, app) -> list[dict]:
        url = f"{self.base}/pucs"
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url, headers=self._headers(app))
            r.raise_for_status()
            return r.json()

    async def get_cuentas(self, app, puc_id: int | str) -> list[dict]:
        url = f"{self.base}/cuentas/{puc_id}"
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url, headers=self._headers(app))
            r.raise_for_status()
            return r.json()

    async def get_terceros(self, app) -> list[dict]:
        url = f"{self.t_base}/personas"
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url, headers=self._headers(app))
            r.raise_for_status()
            return r.json()

    @staticmethod
    def _pick_puc_nif(pucs: List[Dict[str, Any]]) -> Dict[str, Any]:
        # NIF = es_local == "0"
        for p in pucs:
            if str(p.get("es_local")) == "0":
                return p
        raise ValueError("PUC NIF not found")

erp_service = ERPService()
