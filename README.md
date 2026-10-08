# ChessCoach

Analisa as últimas partidas de um jogador do **Chess.com** com o **Stockfish** e gera um
relatório com estatísticas, padrões de erro e as posições que mais vale a pena treinar.

- **Backend:** Python + FastAPI (`api.py`), análise com python-chess + Stockfish, banco SQLite.
- **Front-end:** Vue 3 + TypeScript + Vite (`chesscoach-web/`), tabuleiro com chessground.

## Como rodar (Windows 11, PowerShell)

Pré-requisitos: Python 3.11+, Node 20+ e o executável do [Stockfish](https://stockfishchess.org/download/) na pasta do projeto
(`stockfish.exe`; o nome `stockfish.exe.exe` também é aceito). Outra opção é definir a
variável de ambiente `STOCKFISH_PATH` com o caminho completo.

**1. Backend** (num terminal, na pasta `chesscoach`):

```powershell
.venv\Scripts\Activate.ps1          # ou crie antes: py -m venv .venv
pip install -r requirements.txt
uvicorn api:app --reload
```

**2. Front-end** (em outro terminal, na pasta `chesscoach-web`):

```powershell
npm install
npm run dev
```

Abra http://localhost:5173, digite o nick do Chess.com e aguarde: as 30 partidas mais recentes
são baixadas e analisadas em segundo plano (cerca de 1 a 3 minutos na primeira vez; depois fica
tudo em cache no banco). O relatório vai se completando sozinho.

## Como funciona

| Etapa | Onde |
|---|---|
| Baixa as partidas do Chess.com e grava no SQLite | `chesscoach/clients/chesscom.py`, `chesscoach/importer.py` |
| Avalia cada posição com o Stockfish (com cache por FEN) | `evaluator.py` |
| Classifica cada lance: perda, precisão, gravidade, fase, pressão de tempo | `analysis.py` |
| Roda a análise em segundo plano e informa o progresso | `jobs.py` |
| Classifica o *tipo* de cada erro (seus exercícios) | `heuristics.py` |
| Agrega as últimas N partidas e escreve o diagnóstico | `report.py` |
| Rotas HTTP | `api.py` |

**Critérios usados**

- **Gravidade:** queda nas chances de vitória de quem jogou (a mesma curva do Lichess):
  imprecisão ≥ 10, erro ≥ 20, blunder ≥ 30 pontos na escala de −100 a 100.
- **Precisão:** fórmula de precisão por lance do Lichess, com média simples por partida.
- **Fase:** final quando restam ≤ 20 pontos de material de peças (ou ≤ 26 sem damas);
  abertura até o lance 12; o resto é meio-jogo.
- **Pressão de tempo:** relógio abaixo de 10% do tempo inicial (mínimo de 10 s).
- **Vantagem desperdiçada:** chegou a +3 ou mais e não venceu.

A profundidade padrão do Stockfish é 12. Para mudar, defina `ANALYSIS_DEPTH` antes de subir a API.

## API

| Método | Rota | O que faz |
|---|---|---|
| GET | `/api/player/{nick}/profile` | perfil e ratings no Chess.com |
| POST | `/api/player/{nick}/sync?limit=30` | baixa as partidas e inicia a análise |
| GET | `/api/player/{nick}/job` | progresso da análise |
| GET | `/api/player/{nick}/report?limit=30` | relatório com as estatísticas |
| GET | `/api/game/{id}/analysis` | lances de uma partida com avaliação |

Documentação interativa: http://localhost:8000/docs

## Testes

```powershell
python -m pytest -q
```

Os testes não precisam de internet nem do Stockfish (usam um avaliador falso).

Os testes de `tests/test_heuristics.py` marcados como `xfail` são **exercícios**: implemente
`hanging_piece` e `missed_tactic` em `heuristics.py` até eles passarem. O roteiro completo de
heurísticas e machine learning está em [`docs/heuristicas-e-ml.md`](docs/heuristicas-e-ml.md).

## Linha de comando

```powershell
python -m chesscoach import chesscom SEU_USUARIO --max 100   # importa partidas
python -m chesscoach stats SEU_USUARIO                       # estatísticas simples
python evaluator.py ID_DA_PARTIDA                             # erros de uma partida
```
