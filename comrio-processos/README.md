# Processos Trabalhistas — ComRio

Sistema para buscar, listar e monitorar os processos trabalhistas da **ComRio (Comissária Aérea Rio de Janeiro Ltda)** usando a API v2 do Escavador. Os dados ficam num banco SQLite local (`comrio.db`) e o painel é um único arquivo HTML (`saida/painel.html`) que funciona offline e no celular.

## Instalação

```bash
cd comrio-processos
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Configurar o token

```bash
cp .env.example .env
```

Edite o `.env` e preencha:

- `ESCAVADOR_API_TOKEN`: o token gerado no painel do Escavador (seção API). O `.env` está no `.gitignore` e o token nunca aparece no código.
- `COMRIO_CNPJ`: o CNPJ da ComRio.

## Como rodar (nesta ordem)

```bash
python comrio.py saldo        # confere se o token funciona e mostra o saldo de créditos
python comrio.py teste        # busca só 5 processos e mede o custo real de cada chamada pelo saldo
python comrio.py estimar      # mostra quantos processos existem e a estimativa de créditos da busca completa
python comrio.py buscar       # busca completa (pede confirmação "SIM")
```

Depois disso abra o arquivo `saida/painel.html` no navegador.

| Comando | O que faz |
|---|---|
| `atualizar` | Atualização incremental. Use em agendamentos. |
| `atualizar --completa` | Varre todas as páginas, mesmo sem novidades. |
| `monitorar [--frequencia DIARIA\|SEMANAL] [--limite N]` | Cadastra os processos não arquivados no monitoramento do Escavador. É cobrado por processo, então teste antes com `--limite 5`. |
| `listar-monitoramentos` | Lista os monitoramentos da conta. |
| `painel` | Gera o painel de novo a partir do banco, sem gastar créditos. |
| `exportar [--formato xlsx\|csv\|ambos]` | Exporta todos os processos para a pasta `saida/`. O painel também exporta a lista filtrada. |

## Atualização agendada

Linux/macOS (`crontab -e`), todo dia às 7h:

```
0 7 * * * cd /caminho/comrio-processos && .venv/bin/python comrio.py atualizar
```

No Windows, use o Agendador de Tarefas com `python comrio.py atualizar`.

## Como economizar créditos

- A busca já filtra na API só os tribunais do Trabalho (TST e TRT-1 a TRT-24). Depois, o programa confere o segmento do número CNJ (o dígito `5` indica Justiça do Trabalho).
- A lista vem ordenada pela última movimentação, da mais recente para a mais antiga. O comando `atualizar` para assim que encontra uma página inteira sem novidades.
- As movimentações só são buscadas para processos novos ou cuja data ou quantidade de movimentações mudou.
- Quando aparece uma movimentação nova, ela fica destacada no painel por 7 dias.

## Regras dos campos calculados

- **Fase**: deduzida da classe processual, do grau e do tribunal. Os valores são Conhecimento, Recursal (2º grau), Recursal (TST), Execução e Arquivado.
- **Alerta**: processo sem movimentação há mais de `DIAS_ALERTA_PARADO` dias (padrão 90). Processos arquivados não entram no alerta.
- **Faixas de valor**: até 10 mil, 10 a 50 mil, 50 a 100 mil, 100 a 500 mil, acima de 500 mil e sem valor informado.

## Logs

Cada execução gera um arquivo em `logs/` e uma linha na tabela `execucoes` do banco. A linha registra as requisições por tipo, o saldo antes e depois, as páginas lidas e os processos e movimentações novos.

## Testes

```bash
python -m unittest discover -s tests -v
```

Os testes usam uma API simulada com dados fictícios. Eles não gastam créditos.
