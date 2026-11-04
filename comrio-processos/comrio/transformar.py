"""Converte o JSON do Escavador v2 nos campos do sistema e calcula os campos derivados."""
import json
import re
from datetime import date, datetime

# CNJ: NNNNNNN-DD.AAAA.J.TR.OOOO  ->  J = 5 é a Justiça do Trabalho
RE_CNJ = re.compile(r"^\d{7}-\d{2}\.\d{4}\.(\d)\.(\d{2})\.\d{4}$")


def eh_trabalhista(item) -> bool:
    m = RE_CNJ.match(item.get("numero_cnj") or "")
    if m:
        return m.group(1) == "5"
    siglas = [((f.get("tribunal") or {}).get("sigla") or f.get("sigla") or "") for f in item.get("fontes") or []]
    return any(s.startswith(("TRT", "TST")) for s in siglas)


def _so_digitos(s):
    return re.sub(r"\D", "", s or "")


def _fontes_tribunal(item):
    fontes = [f for f in item.get("fontes") or [] if (f.get("tipo") or "").upper() == "TRIBUNAL"]
    return fontes or list(item.get("fontes") or [])


def _fonte_principal(item):
    """Fonte de tribunal com a movimentação mais recente (reflete a instância atual)."""
    fontes = _fontes_tribunal(item)
    if not fontes:
        return {}
    return max(fontes, key=lambda f: (f.get("data_ultima_movimentacao") or "", f.get("grau") or 0))


def _fonte_primeiro_grau(item):
    fontes = _fontes_tribunal(item)
    pg = [f for f in fontes if f.get("grau") == 1]
    return (pg or fontes or [{}])[0]


def _polo_comrio(item, cnpj):
    for f in item.get("fontes") or []:
        for t in f.get("tipos_envolvido_pesquisado") or []:
            polo = (t.get("polo") or "").upper()
            if polo in ("ATIVO", "PASSIVO"):
                return polo.capitalize()
    for f in item.get("fontes") or []:
        for e in f.get("envolvidos") or []:
            if cnpj and _so_digitos(e.get("cnpj")) == cnpj:
                return (e.get("polo") or "").capitalize() or None
    return None


def _eh_advogado(e):
    return "ADVOGADO" in (e.get("tipo_normalizado") or e.get("tipo") or "").upper() or e.get("oabs")


def _partes(item, cnpj, polo_comrio):
    """Nome do reclamante (parte contrária) e advogados (todos, com indicação do lado)."""
    lado_contrario = "PASSIVO" if (polo_comrio or "").upper() == "ATIVO" else "ATIVO"
    reclamantes, advogados = [], []
    for f in _fontes_tribunal(item):
        for e in f.get("envolvidos") or []:
            if _eh_advogado(e):
                continue
            polo = (e.get("polo") or "").upper()
            eh_comrio = cnpj and _so_digitos(e.get("cnpj")) == cnpj
            if polo == lado_contrario and not eh_comrio and e.get("nome") and e["nome"] not in reclamantes:
                reclamantes.append(e["nome"])
            lado = "ComRio" if eh_comrio else ("Reclamante" if polo == lado_contrario else polo.capitalize() or "?")
            for a in e.get("advogados") or []:
                oab = ", ".join(f"OAB {o.get('numero')}/{o.get('uf')}" for o in a.get("oabs") or [])
                rot = f"{a.get('nome')}{' (' + oab + ')' if oab else ''} — {lado}"
                if a.get("nome") and rot not in advogados:
                    advogados.append(rot)
    if not reclamantes:
        titulo = item.get("titulo_polo_ativo") if lado_contrario == "ATIVO" else item.get("titulo_polo_passivo")
        if titulo:
            reclamantes.append(titulo)
    return "; ".join(reclamantes) or None, "; ".join(advogados) or None


def _fase(fonte, capa):
    classe = (capa.get("classe") or "").lower()
    sigla = ((fonte.get("tribunal") or {}).get("sigla") or fonte.get("sigla") or "").upper()
    if fonte.get("arquivado") or capa.get("data_arquivamento"):
        return "Arquivado"
    if any(p in classe for p in ("execução", "execucao", "cumprimento de sentença", "liquidação", "liquidacao")):
        return "Execução"
    if sigla.startswith("TST") or (fonte.get("grau") or 1) >= 3:
        return "Recursal (TST)"
    if (fonte.get("grau") or 1) == 2 or "recurso" in classe or "agravo" in classe:
        return "Recursal (2º grau)"
    return "Conhecimento"


def mapear(item, cnpj) -> dict:
    principal = _fonte_principal(item)
    primeiro = _fonte_primeiro_grau(item)
    capa_p = principal.get("capa") or {}
    capa_1 = primeiro.get("capa") or {}
    unidade = item.get("unidade_origem") or {}
    estado = item.get("estado_origem") or (unidade.get("estado") or {})
    valor = (capa_1.get("valor_causa") or capa_p.get("valor_causa") or {}).get("valor")
    polo = _polo_comrio(item, cnpj)
    reclamante, advogados = _partes(item, cnpj, polo)
    assunto = capa_1.get("assunto") or (capa_1.get("assunto_principal_normalizado") or {}).get("nome") \
        or capa_p.get("assunto")
    tribunal = (principal.get("tribunal") or {}).get("sigla") or principal.get("sigla") \
        or unidade.get("tribunal_sigla")
    return {
        "numero_cnj": item.get("numero_cnj"),
        "tribunal": tribunal,
        "orgao_julgador": capa_1.get("orgao_julgador") or unidade.get("nome") or capa_p.get("orgao_julgador"),
        "comarca": unidade.get("cidade"),
        "uf": estado.get("sigla"),
        "classe": capa_p.get("classe") or capa_1.get("classe"),
        "assunto": assunto,
        "polo": polo,
        "reclamante": reclamante,
        "advogados": advogados,
        "fase": _fase(principal, capa_p),
        "status_predito": principal.get("status_predito"),
        "grau": principal.get("grau_formatado"),
        "arquivado": 1 if item.get("fontes_tribunais_estao_arquivadas") else 0,
        "valor_causa": float(valor) if valor not in (None, "") else None,
        "data_distribuicao": capa_1.get("data_distribuicao") or item.get("data_inicio") or primeiro.get("data_inicio"),
        "data_ultima_movimentacao": item.get("data_ultima_movimentacao"),
        "data_ultima_verificacao": item.get("data_ultima_verificacao") or principal.get("data_ultima_verificacao"),
        "quantidade_movimentacoes": item.get("quantidade_movimentacoes"),
        "url": principal.get("url"),
        "json_bruto": json.dumps(item, ensure_ascii=False),
    }


# ------------------------------------------------------------------ campos calculados
FAIXAS = [
    (10_000, "Até R$ 10 mil"),
    (50_000, "R$ 10 mil a 50 mil"),
    (100_000, "R$ 50 mil a 100 mil"),
    (500_000, "R$ 100 mil a 500 mil"),
    (float("inf"), "Acima de R$ 500 mil"),
]
ORDEM_FAIXAS = [f[1] for f in FAIXAS] + ["Sem valor informado"]


def faixa_valor(valor):
    if valor is None:
        return "Sem valor informado"
    for limite, nome in FAIXAS:
        if valor <= limite:
            return nome


def para_data(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")[:19]).date()
    except ValueError:
        try:
            return datetime.strptime(str(s)[:10], "%d/%m/%Y").date()
        except ValueError:
            return None


def calcular(p: dict, hoje: date, dias_alerta=90) -> dict:
    d_dist, d_mov = para_data(p.get("data_distribuicao")), para_data(p.get("data_ultima_movimentacao"))
    dias_dist = (hoje - d_dist).days if d_dist else None
    dias_parado = (hoje - d_mov).days if d_mov else None
    return {
        "dias_desde_distribuicao": dias_dist,
        "dias_sem_movimentacao": dias_parado,
        "faixa_valor": faixa_valor(p.get("valor_causa")),
        "alerta_parado": bool(dias_parado is not None and dias_parado > dias_alerta and p.get("fase") != "Arquivado"),
    }
