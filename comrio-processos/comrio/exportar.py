"""Linhas prontas para painel/exportação e exportação para Excel e CSV."""
import csv
from datetime import date, timedelta

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .transformar import calcular

COLUNAS = [
    ("numero_cnj", "Número CNJ"), ("tribunal", "Tribunal"), ("orgao_julgador", "Vara / Órgão julgador"),
    ("comarca", "Comarca"), ("uf", "UF"), ("classe", "Classe"), ("assunto", "Assunto"), ("polo", "Polo da ComRio"),
    ("reclamante", "Reclamante"), ("advogados", "Advogados"), ("fase", "Fase"), ("status_predito", "Status"),
    ("valor_causa", "Valor da causa (R$)"), ("faixa_valor", "Faixa de valor"),
    ("data_distribuicao", "Distribuição"), ("data_ultima_movimentacao", "Última movimentação"),
    ("texto_ultima_movimentacao", "Texto da última movimentação"),
    ("data_ultima_verificacao", "Última atualização no Escavador"),
    ("dias_desde_distribuicao", "Dias desde a distribuição"), ("dias_sem_movimentacao", "Dias sem movimentação"),
    ("alerta_parado", "Alerta: parado"), ("movs_novas", "Movimentações novas (7 dias)"),
]


def linhas(con, dias_alerta=90, hoje=None):
    hoje = hoje or date.today()
    limite_novas = (hoje - timedelta(days=7)).isoformat()
    novas = dict(con.execute(
        "SELECT numero_cnj, COUNT(*) FROM movimentacoes WHERE visto_em >= ? "
        "AND execucao_id <> (SELECT MIN(execucao_id) FROM movimentacoes m2 WHERE m2.numero_cnj = movimentacoes.numero_cnj) "
        "GROUP BY numero_cnj", (limite_novas,)).fetchall())
    saida = []
    for r in con.execute("SELECT * FROM processos ORDER BY data_ultima_movimentacao DESC"):
        p = {k: r[k] for k in r.keys() if k != "json_bruto"}
        p.update(calcular(p, hoje, dias_alerta))
        p["movs_novas"] = novas.get(p["numero_cnj"], 0)
        for k in ("data_distribuicao", "data_ultima_movimentacao", "data_ultima_verificacao"):
            p[k] = (p[k] or "")[:10] or None
        saida.append(p)
    return saida


def _valor_celula(k, v):
    if k == "alerta_parado":
        return "SIM" if v else "não"
    return v


def para_csv(dados, caminho):
    with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow([t for _, t in COLUNAS])
        for p in dados:
            linha = []
            for k, _ in COLUNAS:
                v = _valor_celula(k, p.get(k))
                if isinstance(v, float):
                    v = f"{v:.2f}".replace(".", ",")
                linha.append("" if v is None else v)
            w.writerow(linha)


def para_xlsx(dados, caminho):
    wb = Workbook()
    ws = wb.active
    ws.title = "Processos"
    ws.append([t for _, t in COLUNAS])
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F3A5F")
        c.alignment = Alignment(vertical="center", wrap_text=True)
    for p in dados:
        ws.append([_valor_celula(k, p.get(k)) for k, _ in COLUNAS])
    col_valor = [k for k, _ in COLUNAS].index("valor_causa") + 1
    for row in ws.iter_rows(min_row=2, min_col=col_valor, max_col=col_valor):
        row[0].number_format = '"R$" #,##0.00'
    larguras = {"numero_cnj": 27, "orgao_julgador": 34, "reclamante": 30, "advogados": 40,
                "texto_ultima_movimentacao": 60, "assunto": 30, "classe": 26}
    for i, (k, _) in enumerate(COLUNAS, 1):
        ws.column_dimensions[get_column_letter(i)].width = larguras.get(k, 15)
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = ws.dimensions
    wb.save(caminho)
