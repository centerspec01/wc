"""Testes com uma API simulada (dados FICTÍCIOS, só para validar o código).

Rodar:  python -m unittest discover -s tests -v
"""
import json
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from comrio import coleta, db, exportar, painel  # noqa: E402
from comrio.api import Escavador  # noqa: E402
from comrio.config import Config  # noqa: E402
from comrio.transformar import calcular, eh_trabalhista, mapear  # noqa: E402

CNPJ = "00000000000191"  # fictício


def item(n, data_mov, tribunal="TRT-1", segmento="5", qtd_mov=10, valor=25000.0):
    cnj = f"{n:07d}-11.2023.{segmento}.01.0001"
    return {
        "numero_cnj": cnj, "quantidade_movimentacoes": qtd_mov, "data_ultima_movimentacao": data_mov,
        "data_ultima_verificacao": "2026-11-01T10:00:00", "fontes_tribunais_estao_arquivadas": False,
        "titulo_polo_ativo": f"Reclamante Fictício {n}", "titulo_polo_passivo": "ComRio",
        "data_inicio": "2023-02-10", "ano_inicio": 2023,
        "unidade_origem": {"nome": "1ª Vara do Trabalho do Rio de Janeiro", "cidade": "Rio de Janeiro",
                           "estado": {"nome": "Rio de Janeiro", "sigla": "RJ"}, "tribunal_sigla": tribunal},
        "fontes": [{
            "id": n, "processo_fonte_id": n, "descricao": f"{tribunal} - 1º grau", "nome": "TRT", "sigla": tribunal,
            "tipo": "TRIBUNAL", "grau": 1, "grau_formatado": "Primeiro Grau", "data_inicio": "2023-02-10",
            "data_ultima_movimentacao": data_mov, "fisico": False, "sistema": "PJE", "quantidade_movimentacoes": qtd_mov,
            "quantidade_envolvidos": 3, "status_predito": "ATIVO", "url": "https://exemplo.invalid/p",
            "tribunal": {"id": 1, "nome": "TRT 1ª Região", "sigla": tribunal},
            "tipos_envolvido_pesquisado": [{"id": 1, "tipo": "Reclamado", "tipo_normalizado": "Reclamado", "polo": "PASSIVO"}],
            "capa": {"classe": "Ação Trabalhista - Rito Ordinário", "assunto": "Horas Extras", "area": "Trabalhista",
                     "orgao_julgador": "1ª Vara do Trabalho do Rio de Janeiro", "data_distribuicao": "2023-02-10",
                     "data_arquivamento": None, "assunto_principal_normalizado": None,
                     "valor_causa": {"valor": valor, "moeda": "R$", "valor_formatado": ""}},
            "envolvidos": [
                {"nome": f"Reclamante Fictício {n}", "tipo": "Reclamante", "tipo_normalizado": "Reclamante",
                 "tipo_pessoa": "FISICA", "polo": "ATIVO", "quantidade_processos": 1,
                 "advogados": [{"nome": "Advogada Fictícia", "tipo": "Advogado", "tipo_normalizado": "Advogado",
                                "tipo_pessoa": "FISICA", "polo": "ADVOGADO", "quantidade_processos": 9,
                                "oabs": [{"numero": 123, "uf": "RJ", "tipo": "ADVOGADO"}]}]},
                {"nome": "COMRIO", "tipo": "Reclamado", "tipo_normalizado": "Reclamado", "tipo_pessoa": "JURIDICA",
                 "polo": "PASSIVO", "cnpj": "00.000.000/0001-91", "quantidade_processos": 1200, "advogados": []},
            ],
        }],
    }


class Resp:
    def __init__(self, status, corpo, headers=None):
        self.status_code, self._corpo = status, corpo
        self.headers = headers or {}
        self.text = json.dumps(corpo)

    def json(self):
        return self._corpo


class SessaoFalsa:
    """Imita a API: 3 páginas de envolvido/processos, movimentações e saldo. Primeira chamada devolve 429."""

    def __init__(self, paginas, movs):
        self.headers, self.paginas, self.movs = {}, paginas, movs
        self.chamadas, self.saldo, self.deu_429 = [], 1000.0, False

    def request(self, metodo, url, timeout=None, params=None, json=None):
        self.chamadas.append((metodo, url, params))
        u = urlparse(url)
        if u.path.endswith("quantidade-creditos"):
            return Resp(200, {"quantidade_creditos": self.saldo})
        if not self.deu_429:
            self.deu_429 = True
            return Resp(429, {"error": "Too Many Requests"}, {"Retry-After": "0"})
        self.saldo -= 1
        if u.path.endswith("envolvido/processos"):
            pag = int(parse_qs(u.query).get("cursor", ["0"])[0])
            nxt = f"https://api.escavador.com/api/v2/envolvido/processos?cursor={pag + 1}" if pag + 1 < len(self.paginas) else None
            return Resp(200, {"envolvido_encontrado": {"nome": "COMRIO", "quantidade_processos": 6},
                              "items": self.paginas[pag], "links": {"next": nxt}})
        if u.path.endswith("/movimentacoes"):
            cnj = u.path.split("/")[-2]
            return Resp(200, {"items": self.movs.get(cnj, []), "links": {"next": None}})
        return Resp(404, {"error": "não encontrado"})


def cfg_teste(pasta):
    return Config(token="x", cnpj=CNPJ, max_req_por_min=1000, itens_por_pagina=2, dias_alerta=90,
                  custo_pagina=None, custo_movimentacoes=None, custo_resumo=None,
                  caminho_db=pasta / "t.db", pasta_logs=pasta / "logs", pasta_saida=pasta / "saida")


class TestSistema(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = cfg_teste(self.tmp)
        self.con = db.conectar(self.cfg.caminho_db)
        self.paginas = [
            [item(1, "2026-11-03"), item(2, "2026-10-30")],
            [item(3, "2026-06-01"), item(9, "2026-05-01", tribunal="TJRJ", segmento="8")],
            [item(4, "2025-01-15", valor=800000.0), item(5, "2024-12-01")],
        ]
        cnj1 = self.paginas[0][0]["numero_cnj"]
        self.movs = {cnj1: [{"id": 10, "data": "2026-11-03", "tipo": "ANDAMENTO", "conteudo": "Audiência designada"},
                            {"id": 9, "data": "2026-10-01", "conteudo": "Juntada de petição"}]}
        self.sessao = SessaoFalsa(self.paginas, self.movs)
        self.cliente = Escavador("x", 1000, sessao=self.sessao, dormir=lambda s: None)
        coleta.configurar_log(self.cfg, "teste")

    def test_mapeamento_e_calculados(self):
        p = mapear(item(1, "2026-07-01", valor=60000.0), CNPJ)
        self.assertEqual(p["tribunal"], "TRT-1")
        self.assertEqual(p["polo"], "Passivo")
        self.assertEqual(p["reclamante"], "Reclamante Fictício 1")
        self.assertIn("OAB 123/RJ", p["advogados"])
        self.assertEqual(p["fase"], "Conhecimento")
        c = calcular(p, date(2026, 11, 4))
        self.assertEqual(c["faixa_valor"], "R$ 50 mil a 100 mil")
        self.assertTrue(c["alerta_parado"])
        self.assertFalse(eh_trabalhista(item(9, "2026-01-01", segmento="8")))

    def test_busca_completa_incremental_painel_exportacao(self):
        with coleta.execucao(self.con, self.cliente, "busca_completa", "x.log") as est:
            coleta.varrer(self.con, self.cfg, self.cliente, est, incremental=False)
        self.assertEqual(est["paginas"], 3)
        self.assertEqual(est["lidos"], 5)  # o processo da Justiça Estadual foi descartado
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM processos").fetchone()[0], 5)
        cnj1 = self.paginas[0][0]["numero_cnj"]
        self.assertEqual(db.obter(self.con, cnj1)["texto_ultima_movimentacao"], "Audiência designada")
        _, _, params = [c for c in self.sessao.chamadas if "envolvido/processos" in c[1]][0]
        self.assertIn("TRT-1", params["tribunais[]"])
        ex = self.con.execute("SELECT * FROM execucoes").fetchone()
        self.assertEqual(ex["status"], "ok")
        self.assertGreater(ex["creditos_antes"], ex["creditos_depois"])

        # segunda rodada: só o processo 1 mudou -> para na 1ª página e só busca 1 movimentação
        self.paginas[0][0] = item(1, "2026-11-04", qtd_mov=11)
        self.movs[cnj1].insert(0, {"id": 11, "data": "2026-11-04", "conteudo": "Sentença publicada"})
        self.paginas[0][1] = item(2, "2026-10-30")
        antes = len(self.sessao.chamadas)
        with coleta.execucao(self.con, self.cliente, "atualizacao", "x.log") as est2:
            coleta.varrer(self.con, self.cfg, self.cliente, est2, incremental=True)
        self.assertEqual(est2["alterados"], 1)
        self.assertEqual(est2["movs_novas"], 1)
        novas = [c for c in self.sessao.chamadas[antes:] if "quantidade-creditos" not in c[1]]
        self.assertEqual(len(novas), 3, novas)  # 2 páginas (a 2ª sem novidade encerra) + 1 movimentações
        # nova rodada sem mudanças: 1 página, nenhuma movimentação
        with coleta.execucao(self.con, self.cliente, "atualizacao", "x.log") as est3:
            coleta.varrer(self.con, self.cfg, self.cliente, est3, incremental=True)
        self.assertEqual((est3["paginas"], est3["alterados"]), (1, 0))

        dados = exportar.linhas(self.con, 90, hoje=date(2026, 11, 4))
        p1 = next(d for d in dados if d["numero_cnj"] == cnj1)
        self.assertEqual(p1["movs_novas"], 1)
        self.assertEqual(p1["texto_ultima_movimentacao"], "Sentença publicada")
        destino, n = painel.gerar(self.con, self.cfg, self.cfg.pasta_saida / "painel.html")
        html = destino.read_text(encoding="utf-8")
        self.assertEqual(n, 5)
        self.assertNotIn("__DADOS__", html)
        self.assertNotRegex(html, r'<script[^>]+src=|<link[^>]+href=')  # sem dependências externas
        exportar.para_xlsx(dados, self.tmp / "a.xlsx")
        exportar.para_csv(dados, self.tmp / "a.csv")
        self.assertTrue((self.tmp / "a.csv").read_text(encoding="utf-8-sig").startswith("Número CNJ;"))


if __name__ == "__main__":
    unittest.main()
