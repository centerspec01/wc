#!/usr/bin/env python3
"""Sistema de processos trabalhistas da ComRio — linha de comando.

Uso:  python comrio.py <comando> [opções]      (python comrio.py -h para ajuda)
"""
import argparse
import sys
from datetime import datetime

from comrio import coleta, config, db, exportar, painel
from comrio.api import ErroAPI, Escavador


def _exigir_cnpj(cfg):
    if len(cfg.cnpj) != 14:
        sys.exit("ERRO: COMRIO_CNPJ não definido (ou inválido) no .env.")


def _confirmar(msg, sim):
    if sim:
        return True
    try:
        return input(f"{msg} Digite SIM para continuar: ").strip().upper() == "SIM"
    except EOFError:
        return False


def _gerar_painel(con, cfg):
    destino, n = painel.gerar(con, cfg, cfg.pasta_saida / "painel.html")
    print(f"Painel gerado: {destino} ({n} processos)")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Processos trabalhistas da ComRio via API v2 do Escavador")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("saldo", help="mostra o saldo de créditos da conta")
    sub.add_parser("estimar", help="estima o custo em créditos da busca completa (não busca processos)")
    t = sub.add_parser("teste", help="busca só N processos (padrão 5) e mede o custo real")
    t.add_argument("-n", type=int, default=5)
    b = sub.add_parser("buscar", help="busca completa: percorre todas as páginas")
    b.add_argument("--sem-movimentacoes", action="store_true", help="não busca o texto da última movimentação")
    b.add_argument("--sim", action="store_true", help="não pedir confirmação")
    a = sub.add_parser("atualizar", help="atualização incremental (para rodar agendada)")
    a.add_argument("--completa", action="store_true", help="varre todas as páginas mesmo sem novidades")
    m = sub.add_parser("monitorar", help="cadastra os processos no monitoramento do Escavador")
    m.add_argument("--frequencia", choices=["DIARIA", "SEMANAL"], default="SEMANAL")
    m.add_argument("--limite", type=int, help="cadastrar só os N primeiros (para testar)")
    m.add_argument("--sim", action="store_true")
    sub.add_parser("listar-monitoramentos", help="lista monitoramentos de tribunal da conta")
    sub.add_parser("painel", help="gera saida/painel.html a partir do banco local")
    sub.add_parser("demo", help="gera um painel com dados FICTÍCIOS, sem API e sem gastar créditos")
    e = sub.add_parser("exportar", help="exporta todos os processos do banco")
    e.add_argument("--formato", choices=["xlsx", "csv", "ambos"], default="ambos")
    args = ap.parse_args(argv)

    offline = args.cmd in ("painel", "exportar", "demo")
    cfg = config.carregar(exigir_token=not offline)
    if args.cmd == "demo":
        from comrio import demo
        cfg.caminho_db = cfg.caminho_db.with_name("demo.db")  # banco separado: não mistura com o real
        cfg.cnpj = demo.CNPJ_FICTICIO
        con = db.conectar(cfg.caminho_db)
        demo.popular(con)
        destino, n = painel.gerar(con, cfg, cfg.pasta_saida / "painel_demo.html")
        print(f"Painel de DEMONSTRAÇÃO (dados fictícios) gerado: {destino} ({n} processos)")
        return
    con = db.conectar(cfg.caminho_db)

    if args.cmd == "painel":
        return _gerar_painel(con, cfg)
    if args.cmd == "exportar":
        cfg.pasta_saida.mkdir(exist_ok=True)
        dados = exportar.linhas(con, cfg.dias_alerta)
        base = cfg.pasta_saida / f"processos_comrio_{datetime.now():%Y%m%d}"
        if args.formato in ("xlsx", "ambos"):
            exportar.para_xlsx(dados, base.with_suffix(".xlsx")); print(f"Gerado {base.with_suffix('.xlsx')}")
        if args.formato in ("csv", "ambos"):
            exportar.para_csv(dados, base.with_suffix(".csv")); print(f"Gerado {base.with_suffix('.csv')}")
        return

    cliente = Escavador(cfg.token, cfg.max_req_por_min)
    try:
        if args.cmd == "saldo":
            saldo, bruto = cliente.saldo_creditos()
            print(f"Saldo: {saldo if saldo is not None else bruto}")
            return
        if args.cmd == "listar-monitoramentos":
            print(cliente.listar_monitoramentos())
            return

        _exigir_cnpj(cfg)
        if args.cmd == "estimar":
            coleta.configurar_log(cfg, "estimar")
            coleta.estimar(con, cfg, cliente)
            return

        arquivo = coleta.configurar_log(cfg, args.cmd)
        if args.cmd == "teste":
            with coleta.execucao(con, cliente, "teste", arquivo) as est:
                coleta.teste(con, cfg, cliente, est, n=args.n)
            _gerar_painel(con, cfg)
            print("\nAgora rode `python comrio.py estimar` para ver o custo da busca completa com o custo medido.")
        elif args.cmd == "buscar":
            if not _confirmar("Isto vai percorrer TODAS as páginas e gastar créditos "
                              "(rode `estimar` antes para ver o custo).", args.sim):
                sys.exit("Cancelado.")
            with coleta.execucao(con, cliente, "busca_completa", arquivo) as est:
                coleta.varrer(con, cfg, cliente, est, incremental=False,
                              com_movimentacoes=not args.sem_movimentacoes)
            _gerar_painel(con, cfg)
        elif args.cmd == "atualizar":
            with coleta.execucao(con, cliente, "atualizacao", arquivo) as est:
                coleta.varrer(con, cfg, cliente, est, incremental=not args.completa)
            _gerar_painel(con, cfg)
        elif args.cmd == "monitorar":
            n = con.execute("SELECT COUNT(*) FROM processos WHERE monitoramento_id IS NULL "
                            "AND COALESCE(fase,'')<>'Arquivado'").fetchone()[0]
            n = min(n, args.limite) if args.limite else n
            if not _confirmar(f"Vai cadastrar {n} processo(s) no monitoramento do Escavador, que é cobrado "
                              "por processo monitorado. Confira o preço no seu contrato.", args.sim):
                sys.exit("Cancelado.")
            with coleta.execucao(con, cliente, "monitoramento", arquivo):
                coleta.cadastrar_monitoramentos(con, cliente, args.frequencia, args.limite)
    except ErroAPI as e:
        sys.exit(f"ERRO da API do Escavador: {e}")


if __name__ == "__main__":
    main()
