"""Busca, atualização incremental, estimativa de custo e monitoramento."""
import json
import logging
import math
from contextlib import contextmanager
from datetime import datetime

from . import db
from .api import ErroAPI, Escavador
from .config import formatar_cnpj
from .transformar import eh_trabalhista, mapear

log = logging.getLogger("comrio")


def agora():
    return datetime.now().isoformat(timespec="seconds")


def configurar_log(cfg, tipo):
    cfg.pasta_logs.mkdir(exist_ok=True)
    arquivo = cfg.pasta_logs / f"{datetime.now():%Y%m%d_%H%M%S}_{tipo}.log"
    log.setLevel(logging.DEBUG)
    for h in list(log.handlers):
        h.close()
        log.removeHandler(h)
    fh = logging.FileHandler(arquivo, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(fh)
    log.addHandler(ch)
    return arquivo


@contextmanager
def execucao(con, cliente: Escavador, tipo, arquivo_log, medir_saldo=True):
    """Registra a execução na tabela `execucoes` (com saldo antes/depois) e no log."""
    est = {"paginas": 0, "lidos": 0, "novos": 0, "alterados": 0, "movs_novas": 0, "status": "ok", "erro": None}
    antes = _saldo_seguro(cliente) if medir_saldo else None
    cur = con.execute("INSERT INTO execucoes (tipo, inicio, status, creditos_antes, arquivo_log) VALUES (?,?,?,?,?)",
                      (tipo, agora(), "rodando", antes, str(arquivo_log)))
    est["id"] = cur.lastrowid
    con.commit()
    log.info("== Execução #%s (%s) iniciada. Saldo inicial: %s", est["id"], tipo, _fmt(antes))
    try:
        yield est
    except KeyboardInterrupt:
        est["status"], est["erro"] = "interrompida", "interrompida pelo usuário"
        raise
    except Exception as e:  # registra e propaga
        est["status"], est["erro"] = "erro", str(e)
        log.exception("Execução falhou: %s", e)
        raise
    finally:
        depois = _saldo_seguro(cliente) if medir_saldo else None
        con.execute(
            "UPDATE execucoes SET fim=?, status=?, requisicoes=?, detalhe_requisicoes=?, creditos_depois=?, paginas=?,"
            " processos_lidos=?, processos_novos=?, processos_alterados=?, movimentacoes_novas=?, erro=? WHERE id=?",
            (agora(), est["status"], cliente.total_requisicoes, json.dumps(cliente.contagem), depois, est["paginas"],
             est["lidos"], est["novos"], est["alterados"], est["movs_novas"], est["erro"], est["id"]),
        )
        con.commit()
        gasto = (antes - depois) if antes is not None and depois is not None else None
        log.info("== Execução #%s finalizada (%s). Requisições: %s %s | Páginas: %s | Lidos: %s | Novos: %s |"
                 " Alterados: %s | Movimentações novas: %s | Créditos gastos: %s",
                 est["id"], est["status"], cliente.total_requisicoes, cliente.contagem, est["paginas"], est["lidos"],
                 est["novos"], est["alterados"], est["movs_novas"], _fmt(gasto))


def _saldo_seguro(cliente):
    try:
        saldo, bruto = cliente.saldo_creditos()
        if saldo is None:
            log.warning("Não reconheci o formato da resposta de saldo: %s", bruto)
        return saldo
    except ErroAPI as e:
        log.warning("Não foi possível consultar o saldo de créditos: %s", e)
        return None


def _fmt(v):
    return "desconhecido" if v is None else f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _mudou(atual, novo):
    if atual is None:
        return True
    return (atual["data_ultima_movimentacao"] != novo["data_ultima_movimentacao"]
            or atual["quantidade_movimentacoes"] != novo["quantidade_movimentacoes"]
            or atual["movimentacoes_buscadas_em"] is None)


def processar_pagina(con, cfg, items, est, momento):
    """Grava os itens trabalhistas da página. Retorna lista de CNJs novos/alterados."""
    alterados = []
    for item in items:
        if not eh_trabalhista(item):
            log.debug("Ignorado (não trabalhista): %s", item.get("numero_cnj"))
            continue
        est["lidos"] += 1
        dados = mapear(item, cfg.cnpj)
        atual = db.obter(con, dados["numero_cnj"])
        mudou = _mudou(atual, dados)
        db.gravar_processo(con, dados, momento)
        if atual is None:
            est["novos"] += 1
        elif mudou:
            est["alterados"] += 1
        if mudou:
            alterados.append(dados["numero_cnj"])
    con.commit()
    return alterados


def buscar_movimentacoes(con, cliente, cnjs, est, momento):
    for i, cnj in enumerate(cnjs, 1):
        try:
            movs = cliente.movimentacoes(cnj)
        except ErroAPI as e:
            if e.status in (401, 402):
                raise
            log.error("Movimentações de %s falharam: %s (seguindo para o próximo)", cnj, e)
            continue
        novas = db.gravar_movimentacoes(con, cnj, movs, momento, est["id"])
        est["movs_novas"] += novas
        if novas:
            log.info("  %s: %d movimentação(ões) nova(s)", cnj, novas)
        if i % 25 == 0:
            con.commit()
            log.info("  movimentações: %d/%d processos", i, len(cnjs))
    con.commit()


def varrer(con, cfg, cliente, est, *, incremental, limite_processos=None, itens_por_pagina=None,
           com_movimentacoes=True):
    momento = agora()
    por_pagina = itens_por_pagina or cfg.itens_por_pagina
    pendentes = []
    for envolvido, items in cliente.paginas_processos_envolvido(cfg.cnpj, limite=por_pagina):
        est["paginas"] += 1
        if est["paginas"] == 1 and envolvido:
            log.info("Envolvido encontrado: %s — %s processos no total (todas as justiças)",
                     envolvido.get("nome"), envolvido.get("quantidade_processos"))
        if limite_processos:
            items = items[: max(0, limite_processos - est["lidos"])]
        alterados = processar_pagina(con, cfg, items, est, momento)
        pendentes += alterados
        log.info("Página %d: %d itens, %d trabalhistas acumulados, %d novos/alterados nesta página",
                 est["paginas"], len(items), est["lidos"], len(alterados))
        if limite_processos and est["lidos"] >= limite_processos:
            break
        if incremental and items and not alterados:
            log.info("Página sem novidades (lista ordenada pela última movimentação): parando a varredura.")
            break
    if com_movimentacoes and pendentes:
        log.info("Buscando movimentações de %d processo(s) novo(s)/alterado(s)...", len(pendentes))
        buscar_movimentacoes(con, cliente, pendentes, est, momento)
    return pendentes


# ------------------------------------------------------------------ teste com 5 processos
def teste(con, cfg, cliente, est, n=5):
    """Busca n processos e mede o custo real de cada tipo de chamada pelo saldo."""
    momento = agora()
    s0 = _saldo_seguro(cliente)
    try:
        paginas = cliente.paginas_processos_envolvido(cfg.cnpj, limite=n)
        envolvido, items = next(paginas)
    except ErroAPI as e:
        if e.status not in (400, 422):
            raise
        log.warning("A API recusou limit=%d (%s). Usando limit=%d e aproveitando só %d itens.",
                    n, e, cfg.itens_por_pagina, n)
        envolvido, items = next(cliente.paginas_processos_envolvido(cfg.cnpj, limite=cfg.itens_por_pagina))
    est["paginas"] = 1
    if envolvido:
        log.info("Envolvido: %s | quantidade_processos: %s", envolvido.get("nome"), envolvido.get("quantidade_processos"))
    s1 = _saldo_seguro(cliente)
    trab = [i for i in items if eh_trabalhista(i)][:n]
    log.info("Página trouxe %d itens; %d trabalhistas usados no teste", len(items), len(trab))
    pend = processar_pagina(con, cfg, trab, est, momento)
    buscar_movimentacoes(con, cliente, pend, est, momento)
    s2 = _saldo_seguro(cliente)
    medido = {"data": momento}
    if None not in (s0, s1):
        medido["custo_pagina"] = round(s0 - s1, 4)
    if None not in (s1, s2) and pend:
        medido["custo_movimentacoes"] = round((s1 - s2) / len(pend), 4)
    con.execute("CREATE TABLE IF NOT EXISTS custos_medidos (data TEXT, json TEXT)")
    con.execute("INSERT INTO custos_medidos VALUES (?,?)", (momento, json.dumps(medido)))
    con.commit()
    log.info("Custo medido: %s", medido)
    for cnj in pend:
        p = db.obter(con, cnj)
        log.info("  %s | %s | %s | %s | valor %s | últ. mov. %s",
                 p["numero_cnj"], p["tribunal"], p["orgao_julgador"], p["fase"], p["valor_causa"],
                 p["data_ultima_movimentacao"])
    return medido


def custos_medidos(con):
    try:
        row = con.execute("SELECT json FROM custos_medidos ORDER BY data DESC LIMIT 1").fetchone()
    except Exception:
        return {}
    return json.loads(row[0]) if row else {}


# ------------------------------------------------------------------ estimativa
def estimar(con, cfg, cliente):
    medido = custos_medidos(con)
    custo_pag = medido.get("custo_pagina", cfg.custo_pagina)
    custo_mov = medido.get("custo_movimentacoes", cfg.custo_movimentacoes)
    origem = "medido no teste" if medido else ("arquivo .env" if cfg.custo_pagina is not None else None)

    resumo = cliente.resumo_envolvido(cfg.cnpj)
    total = resumo.get("quantidade_processos") or 0
    print(f"\nEnvolvido: {resumo.get('nome')} — CNPJ {formatar_cnpj(cfg.cnpj)}")
    print(f"Processos no Escavador (todas as justiças): {total}")
    print("Obs.: a busca filtra os tribunais do Trabalho (TST e TRT-1 a TRT-24) na própria API,\n"
          "      então o número real de páginas tende a ser menor que o calculado abaixo.\n")
    paginas = math.ceil(total / cfg.itens_por_pagina) if total else 0
    linhas = [("Páginas de envolvido/processos", paginas, custo_pag),
              ("Movimentações (1 chamada por processo)", total, custo_mov)]
    soma = 0.0
    desconhecido = False
    print(f"{'Chamada':45} {'Qtd':>6} {'Custo unit.':>12} {'Subtotal':>12}")
    for nome, qtd, unit in linhas:
        if unit is None:
            desconhecido = True
            print(f"{nome:45} {qtd:>6} {'?':>12} {'?':>12}")
        else:
            soma += qtd * unit
            print(f"{nome:45} {qtd:>6} {unit:>12.4f} {qtd * unit:>12.2f}")
    print("-" * 78)
    if desconhecido:
        print("Custo unitário desconhecido para alguma chamada. Rode `python comrio.py teste` para medir\n"
              "o custo real pelo saldo, ou preencha CUSTO_* no .env com os valores do seu contrato.")
    print(f"Total estimado da busca completa: {soma:,.2f} créditos" + (" (parcial)" if desconhecido else "")
          + (f"  [custos: {origem}]" if origem else ""))
    print("Atualizações incrementais seguintes custam bem menos: só páginas com novidade + movimentações\n"
          "dos processos que mudaram.\n")
    saldo, _ = cliente.saldo_creditos()
    print(f"Saldo atual: {_fmt(saldo)} créditos")
    return {"total": total, "paginas": paginas, "estimativa": soma, "parcial": desconhecido}


# ------------------------------------------------------------------ monitoramento
def cadastrar_monitoramentos(con, cliente, frequencia="SEMANAL", limite=None):
    sql = "SELECT numero_cnj FROM processos WHERE monitoramento_id IS NULL AND COALESCE(fase,'') <> 'Arquivado'"
    cnjs = [r[0] for r in con.execute(sql)]
    if limite:
        cnjs = cnjs[:limite]
    log.info("Cadastrando %d processo(s) no monitoramento do Escavador (frequência %s)", len(cnjs), frequencia)
    ok = 0
    for cnj in cnjs:
        try:
            r = cliente.criar_monitoramento(cnj, frequencia)
        except ErroAPI as e:
            if e.status in (401, 402):
                raise
            log.error("  %s: não cadastrado (%s)", cnj, e)
            continue
        mid = (r or {}).get("id") or ((r or {}).get("monitoramento") or {}).get("id")
        con.execute("UPDATE processos SET monitoramento_id=? WHERE numero_cnj=?", (mid or -1, cnj))
        con.commit()
        ok += 1
    log.info("Monitoramentos cadastrados: %d/%d", ok, len(cnjs))
    return ok
