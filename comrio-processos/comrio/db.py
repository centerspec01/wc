"""Banco SQLite local."""
import sqlite3

ESQUEMA = """
CREATE TABLE IF NOT EXISTS processos (
    numero_cnj TEXT PRIMARY KEY,
    tribunal TEXT,
    orgao_julgador TEXT,
    comarca TEXT,
    uf TEXT,
    classe TEXT,
    assunto TEXT,
    polo TEXT,
    reclamante TEXT,
    advogados TEXT,
    fase TEXT,
    status_predito TEXT,
    grau TEXT,
    arquivado INTEGER,
    valor_causa REAL,
    data_distribuicao TEXT,
    data_ultima_movimentacao TEXT,
    texto_ultima_movimentacao TEXT,
    data_ultima_verificacao TEXT,
    quantidade_movimentacoes INTEGER,
    url TEXT,
    json_bruto TEXT,
    movimentacoes_buscadas_em TEXT,
    monitoramento_id INTEGER,
    criado_em TEXT,
    atualizado_em TEXT
);
CREATE TABLE IF NOT EXISTS movimentacoes (
    id INTEGER PRIMARY KEY,
    numero_cnj TEXT NOT NULL,
    data TEXT,
    tipo TEXT,
    conteudo TEXT,
    fonte TEXT,
    visto_em TEXT,
    execucao_id INTEGER
);
CREATE INDEX IF NOT EXISTS ix_mov_cnj ON movimentacoes(numero_cnj, data);
CREATE TABLE IF NOT EXISTS execucoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT,
    inicio TEXT,
    fim TEXT,
    status TEXT,
    requisicoes INTEGER,
    detalhe_requisicoes TEXT,
    creditos_antes REAL,
    creditos_depois REAL,
    paginas INTEGER,
    processos_lidos INTEGER,
    processos_novos INTEGER,
    processos_alterados INTEGER,
    movimentacoes_novas INTEGER,
    arquivo_log TEXT,
    erro TEXT
);
"""

CAMPOS_PROCESSO = [
    "numero_cnj", "tribunal", "orgao_julgador", "comarca", "uf", "classe", "assunto", "polo",
    "reclamante", "advogados", "fase", "status_predito", "grau", "arquivado", "valor_causa",
    "data_distribuicao", "data_ultima_movimentacao", "data_ultima_verificacao",
    "quantidade_movimentacoes", "url", "json_bruto",
]


def conectar(caminho):
    con = sqlite3.connect(caminho)
    con.row_factory = sqlite3.Row
    con.executescript(ESQUEMA)
    return con


def obter(con, cnj):
    return con.execute("SELECT * FROM processos WHERE numero_cnj=?", (cnj,)).fetchone()


def gravar_processo(con, dados, agora):
    """Insere ou atualiza (mantém texto da última movimentação, monitoramento e criado_em)."""
    cols = CAMPOS_PROCESSO
    valores = [dados.get(c) for c in cols]
    atual = obter(con, dados["numero_cnj"])
    if atual is None:
        con.execute(
            f"INSERT INTO processos ({','.join(cols)}, criado_em, atualizado_em) VALUES ({','.join('?' * len(cols))},?,?)",
            valores + [agora, agora],
        )
        return "novo"
    con.execute(
        f"UPDATE processos SET {','.join(c + '=?' for c in cols[1:])}, atualizado_em=? WHERE numero_cnj=?",
        valores[1:] + [agora, dados["numero_cnj"]],
    )
    return "existente"


def gravar_movimentacoes(con, cnj, movs, agora, execucao_id):
    novas = 0
    for m in movs:
        fonte = m.get("fonte") or {}
        cur = con.execute(
            "INSERT OR IGNORE INTO movimentacoes (id, numero_cnj, data, tipo, conteudo, fonte, visto_em, execucao_id)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (m.get("id"), cnj, m.get("data"), m.get("tipo"), m.get("conteudo"),
             fonte.get("sigla") or fonte.get("nome"), agora, execucao_id),
        )
        novas += cur.rowcount
    ultima = con.execute(
        "SELECT conteudo, data FROM movimentacoes WHERE numero_cnj=? ORDER BY data DESC, id DESC LIMIT 1", (cnj,)
    ).fetchone()
    con.execute(
        "UPDATE processos SET texto_ultima_movimentacao=?, movimentacoes_buscadas_em=? WHERE numero_cnj=?",
        (ultima["conteudo"] if ultima else None, agora, cnj),
    )
    return novas
