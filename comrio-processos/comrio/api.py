"""Cliente HTTP da API do Escavador (v2, com as chamadas de v1 que ainda são necessárias).

Endpoints usados (conferidos no SDK oficial escavador-python 0.11.2):
  v2  GET  envolvido/processos?cpf_cnpj=...&tribunais[]=...&ordena_por=...&ordem=...&limit=...
  v2  GET  envolvido/resumo?cpf_cnpj=...
  v2  GET  processos/numero_cnj/{cnj}
  v2  GET  processos/numero_cnj/{cnj}/movimentacoes
  v2  POST processos/numero_cnj/{cnj}/solicitar-atualizacao
  v2  GET  processos/numero_cnj/{cnj}/status-atualizacao
  v1  GET  quantidade-creditos
  v1  POST monitoramento-tribunal          {tipo: UNICO, valor: <CNJ>, frequencia: DIARIA|SEMANAL}
  v1  GET  monitoramentos-tribunal
  v1  DELETE monitoramentos-tribunal/{id}

Paginação v2: a resposta traz "items" e "links.next" (URL de cursor). Segue-se o cursor até acabar.
Autenticação: cabeçalho "Authorization: Bearer <token>" + "X-Requested-With: XMLHttpRequest".
"""
import logging
import random
import time
from collections import deque

import requests

BASE = "https://api.escavador.com/api/"
log = logging.getLogger("comrio")

# Todos os tribunais da Justiça do Trabalho (siglas no formato aceito pela API v2)
TRIBUNAIS_TRABALHO = ["TST"] + [f"TRT-{i}" for i in range(1, 25)]


class ErroAPI(Exception):
    def __init__(self, status, mensagem, corpo=None):
        super().__init__(f"HTTP {status}: {mensagem}")
        self.status = status
        self.corpo = corpo


class LimitadorTaxa:
    """Janela deslizante de 60 s: garante no máximo N requisições por minuto."""

    def __init__(self, por_minuto):
        self.por_minuto = max(1, por_minuto)
        self.instantes = deque()

    def aguardar(self):
        agora = time.monotonic()
        while self.instantes and agora - self.instantes[0] >= 60:
            self.instantes.popleft()
        if len(self.instantes) >= self.por_minuto:
            espera = 60 - (agora - self.instantes[0]) + 0.05
            log.info("Limite local de %s req/min atingido; aguardando %.1fs", self.por_minuto, espera)
            time.sleep(espera)
        self.instantes.append(time.monotonic())


class Escavador:
    MAX_TENTATIVAS = 6
    RETENTAVEIS = {408, 425, 429, 500, 502, 503, 504}

    def __init__(self, token, max_req_por_min=60, sessao=None, dormir=time.sleep):
        self.sessao = sessao or requests.Session()
        self.sessao.headers.update({
            "Authorization": f"Bearer {token}",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json",
            "User-Agent": "comrio-processos/1.0",
        })
        self.limitador = LimitadorTaxa(max_req_por_min)
        self.dormir = dormir
        self.contagem = {}  # nome lógico da chamada -> quantidade feita
        self.total_requisicoes = 0

    # ---------------------------------------------------------------- núcleo
    def _req(self, metodo, url, rotulo, **kw):
        if not url.startswith("http"):
            url = BASE + url
        ultimo_erro = None
        for tentativa in range(1, self.MAX_TENTATIVAS + 1):
            self.limitador.aguardar()
            try:
                resp = self.sessao.request(metodo, url, timeout=60, **kw)
            except (requests.ConnectionError, requests.Timeout) as e:
                ultimo_erro = e
                espera = self._backoff(tentativa)
                log.warning("[%s] falha de rede (%s). Tentativa %d/%d, nova tentativa em %.1fs",
                            rotulo, e.__class__.__name__, tentativa, self.MAX_TENTATIVAS, espera)
                self.dormir(espera)
                continue

            self.total_requisicoes += 1
            self.contagem[rotulo] = self.contagem.get(rotulo, 0) + 1
            cab_cred = {k: v for k, v in resp.headers.items() if "credit" in k.lower()}
            log.debug("[%s] %s %s -> %s %s", rotulo, metodo, url, resp.status_code, cab_cred or "")

            if resp.status_code < 400:
                try:
                    return resp.json()
                except ValueError:
                    raise ErroAPI(resp.status_code, "resposta não é JSON", resp.text[:500])

            corpo = _json_ou_texto(resp)
            if resp.status_code in self.RETENTAVEIS and tentativa < self.MAX_TENTATIVAS:
                espera = _retry_after(resp) or self._backoff(tentativa)
                log.warning("[%s] HTTP %s (%s). Tentativa %d/%d, aguardando %.1fs",
                            rotulo, resp.status_code, _msg(corpo), tentativa, self.MAX_TENTATIVAS, espera)
                self.dormir(espera)
                ultimo_erro = ErroAPI(resp.status_code, _msg(corpo), corpo)
                continue
            if resp.status_code == 401:
                raise ErroAPI(401, "token inválido ou expirado (verifique ESCAVADOR_API_TOKEN)", corpo)
            if resp.status_code == 402:
                raise ErroAPI(402, "créditos insuficientes na conta do Escavador", corpo)
            raise ErroAPI(resp.status_code, _msg(corpo), corpo)
        raise ultimo_erro if isinstance(ultimo_erro, ErroAPI) else ErroAPI(0, f"falha de rede: {ultimo_erro}")

    @staticmethod
    def _backoff(tentativa):
        return min(60, 2 ** tentativa) + random.uniform(0, 1)

    # ---------------------------------------------------------------- v2
    def resumo_envolvido(self, cnpj):
        return self._req("GET", "v2/envolvido/resumo", "resumo_envolvido", params={"cpf_cnpj": cnpj})

    def paginas_processos_envolvido(self, cnpj, limite=100, tribunais=TRIBUNAIS_TRABALHO,
                                    ordena_por="data_ultima_movimentacao", ordem="desc"):
        """Gera uma página por vez: (envolvido_encontrado, items). Segue links.next."""
        params = {"cpf_cnpj": cnpj, "limit": limite, "ordena_por": ordena_por, "ordem": ordem}
        if tribunais:
            params["tribunais[]"] = list(tribunais)
        dados = self._req("GET", "v2/envolvido/processos", "pagina_envolvido", params=params)
        while True:
            yield dados.get("envolvido_encontrado"), dados.get("items") or []
            proximo = (dados.get("links") or {}).get("next")
            if not proximo:
                return
            dados = self._req("GET", proximo, "pagina_envolvido")

    def processo(self, cnj):
        return self._req("GET", f"v2/processos/numero_cnj/{cnj}", "processo")

    def movimentacoes(self, cnj):
        """Primeira página de movimentações (as mais recentes)."""
        dados = self._req("GET", f"v2/processos/numero_cnj/{cnj}/movimentacoes", "movimentacoes")
        return dados.get("items") or []

    def solicitar_atualizacao(self, cnj):
        return self._req("POST", f"v2/processos/numero_cnj/{cnj}/solicitar-atualizacao",
                         "solicitar_atualizacao", json={"enviar_callback": 0, "documentos_publicos": 0})

    # ---------------------------------------------------------------- v1
    def saldo_creditos(self):
        dados = self._req("GET", "v1/quantidade-creditos", "saldo")
        return extrair_saldo(dados), dados

    def criar_monitoramento(self, cnj, frequencia="DIARIA"):
        return self._req("POST", "v1/monitoramento-tribunal", "criar_monitoramento",
                         json={"tipo": "UNICO", "valor": cnj, "frequencia": frequencia})

    def listar_monitoramentos(self):
        return self._req("GET", "v1/monitoramentos-tribunal", "listar_monitoramentos")

    def remover_monitoramento(self, id_monitoramento):
        return self._req("DELETE", f"v1/monitoramentos-tribunal/{id_monitoramento}", "remover_monitoramento")


def extrair_saldo(dados):
    """O formato exato da resposta de saldo não está no SDK; procura o 1º número em chave de crédito/saldo."""
    if isinstance(dados, (int, float)):
        return float(dados)
    if isinstance(dados, dict):
        for k, v in dados.items():
            if any(p in k.lower() for p in ("credito", "saldo", "quantidade")):
                try:
                    return float(str(v).replace(",", "."))
                except ValueError:
                    pass
        for v in dados.values():
            r = extrair_saldo(v) if isinstance(v, dict) else None
            if r is not None:
                return r
    return None


def _json_ou_texto(resp):
    try:
        return resp.json()
    except ValueError:
        return resp.text[:500]


def _msg(corpo):
    if isinstance(corpo, dict):
        return corpo.get("error") or corpo.get("message") or corpo.get("mensagem") or str(corpo)[:200]
    return str(corpo)[:200]


def _retry_after(resp):
    valor = resp.headers.get("Retry-After")
    try:
        return min(300, float(valor)) if valor else None
    except ValueError:
        return None
