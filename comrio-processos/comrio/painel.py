"""Gera o painel HTML (arquivo único, sem dependências externas)."""
import json
from datetime import date, datetime
from pathlib import Path

from .config import formatar_cnpj
from .exportar import COLUNAS, linhas
from .transformar import ORDEM_FAIXAS

MODELO = Path(__file__).with_name("painel_modelo.html")


def gerar(con, cfg, destino: Path, hoje=None):
    hoje = hoje or date.today()
    dados = {
        "empresa": "ComRio — Comissária Aérea Rio de Janeiro Ltda",
        "cnpj": formatar_cnpj(cfg.cnpj) if cfg.cnpj else "não informado",
        "gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "hoje": hoje.isoformat(),
        "dias_alerta": cfg.dias_alerta,
        "ordem_faixas": ORDEM_FAIXAS,
        "colunas_exportacao": COLUNAS,
        "processos": linhas(con, cfg.dias_alerta, hoje),
    }
    js = json.dumps(dados, ensure_ascii=False).replace("</", "<\\/")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(MODELO.read_text(encoding="utf-8").replace("__DADOS__", js), encoding="utf-8")
    return destino, len(dados["processos"])
