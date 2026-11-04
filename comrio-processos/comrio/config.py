"""Configuração lida do arquivo .env (o token nunca fica no código)."""
import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")


def _float_ou_none(nome):
    valor = (os.environ.get(nome) or "").strip().replace(",", ".")
    return float(valor) if valor else None


@dataclass
class Config:
    token: str
    cnpj: str
    max_req_por_min: int
    itens_por_pagina: int
    dias_alerta: int
    custo_pagina: float | None
    custo_movimentacoes: float | None
    custo_resumo: float | None
    caminho_db: Path
    pasta_logs: Path
    pasta_saida: Path


def carregar(exigir_token=True) -> Config:
    token = (os.environ.get("ESCAVADOR_API_TOKEN") or "").strip()
    if exigir_token and not token:
        raise SystemExit(
            "ERRO: ESCAVADOR_API_TOKEN não definido. Copie .env.example para .env e preencha o token."
        )
    cnpj = re.sub(r"\D", "", os.environ.get("COMRIO_CNPJ") or "")
    return Config(
        token=token,
        cnpj=cnpj,
        max_req_por_min=int(os.environ.get("ESCAVADOR_MAX_REQ_POR_MIN") or 60),
        itens_por_pagina=int(os.environ.get("ESCAVADOR_ITENS_POR_PAGINA") or 100),
        dias_alerta=int(os.environ.get("DIAS_ALERTA_PARADO") or 90),
        custo_pagina=_float_ou_none("CUSTO_PAGINA_ENVOLVIDO"),
        custo_movimentacoes=_float_ou_none("CUSTO_MOVIMENTACOES"),
        custo_resumo=_float_ou_none("CUSTO_RESUMO_ENVOLVIDO"),
        caminho_db=RAIZ / "comrio.db",
        pasta_logs=RAIZ / "logs",
        pasta_saida=RAIZ / "saida",
    )


def formatar_cnpj(cnpj: str) -> str:
    c = re.sub(r"\D", "", cnpj)
    if len(c) != 14:
        return cnpj
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"
