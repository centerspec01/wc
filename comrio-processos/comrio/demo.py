"""Dados FICTÍCIOS para ver o painel sem usar a API (nenhum crédito é gasto)."""
import random
from datetime import date, timedelta

from . import db
from .transformar import mapear

CNPJ_FICTICIO = "00000000000191"
NOMES = ["Ana Souza", "Bruno Lima", "Carla Mendes", "Diego Rocha", "Elisa Prado", "Fábio Nunes",
         "Gabriela Reis", "Hugo Martins", "Isabel Costa", "João Pereira", "Karina Alves", "Lucas Teixeira"]
ASSUNTOS = ["Horas Extras", "Adicional de Insalubridade", "Verbas Rescisórias", "Dano Moral",
            "Adicional Noturno", "Intervalo Intrajornada", "Equiparação Salarial"]
MOVS = ["Audiência de instrução designada", "Juntada de petição", "Conclusos para sentença",
        "Sentença publicada", "Recurso ordinário interposto", "Expedido alvará", "Despacho: manifeste-se a reclamada"]


def _item(n, hoje, rnd):
    tribunal = rnd.choice(["TRT-1"] * 7 + ["TRT-2", "TRT-3", "TST"])
    grau = 3 if tribunal == "TST" else rnd.choice([1, 1, 1, 2])
    dist = hoje - timedelta(days=rnd.randint(60, 2200))
    ult = max(dist, hoje - timedelta(days=int(rnd.expovariate(1 / 80))))
    valor = rnd.choice([None, 8_000, 25_000, 48_000, 72_000, 150_000, 320_000, 650_000])
    classe = rnd.choice(["Ação Trabalhista - Rito Ordinário"] * 4 + ["Ação Trabalhista - Rito Sumaríssimo",
                                                                   "Cumprimento de Sentença"])
    vara = f"{rnd.randint(1, 82)}ª Vara do Trabalho do Rio de Janeiro"
    nome = f"{rnd.choice(NOMES)} (fictício)"
    cnj = f"{1000000 + n:07d}-{rnd.randint(10, 99)}.{dist.year}.5.01.{rnd.randint(1, 82):04d}"
    return cnj, ult, {
        "numero_cnj": cnj, "quantidade_movimentacoes": rnd.randint(5, 120),
        "data_ultima_movimentacao": ult.isoformat(), "data_ultima_verificacao": hoje.isoformat(),
        "fontes_tribunais_estao_arquivadas": rnd.random() < 0.08, "data_inicio": dist.isoformat(),
        "unidade_origem": {"nome": vara, "cidade": "Rio de Janeiro", "estado": {"sigla": "RJ"}, "tribunal_sigla": tribunal},
        "fontes": [{
            "tipo": "TRIBUNAL", "grau": grau, "grau_formatado": f"{grau}º grau", "sigla": tribunal,
            "data_ultima_movimentacao": ult.isoformat(), "status_predito": "ATIVO", "arquivado": False,
            "tribunal": {"sigla": tribunal},
            "tipos_envolvido_pesquisado": [{"polo": "PASSIVO"}],
            "capa": {"classe": classe, "assunto": rnd.choice(ASSUNTOS), "orgao_julgador": vara,
                     "data_distribuicao": dist.isoformat(),
                     "valor_causa": {"valor": valor} if valor else None},
            "envolvidos": [
                {"nome": nome, "polo": "ATIVO", "tipo_normalizado": "Reclamante",
                 "advogados": [{"nome": "Advogado(a) Fictício(a)", "oabs": [{"numero": rnd.randint(10000, 99999), "uf": "RJ"}]}]},
                {"nome": "COMRIO", "polo": "PASSIVO", "cnpj": CNPJ_FICTICIO, "tipo_normalizado": "Reclamado", "advogados": []},
            ],
        }],
    }


def popular(con, quantidade=150, semente=42):
    rnd = random.Random(semente)
    hoje = date.today()
    con.execute("DELETE FROM processos")
    con.execute("DELETE FROM movimentacoes")
    for n in range(quantidade):
        cnj, ult, it = _item(n, hoje, rnd)
        db.gravar_processo(con, mapear(it, CNPJ_FICTICIO), (hoje - timedelta(days=30)).isoformat())
        db.gravar_movimentacoes(con, cnj, [{"id": n * 10, "data": ult.isoformat(), "conteudo": rnd.choice(MOVS)}],
                                (hoje - timedelta(days=30)).isoformat(), 1)
        if rnd.random() < 0.1:  # simula movimentação nova detectada pela atualização de ontem
            db.gravar_movimentacoes(con, cnj, [{"id": n * 10 + 1, "data": hoje.isoformat(),
                                                "conteudo": rnd.choice(MOVS) + " (nova)"}],
                                    (hoje - timedelta(days=1)).isoformat(), 2)
    con.commit()
