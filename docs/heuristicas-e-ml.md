# Heurísticas e Machine Learning: roteiro

Hoje o relatório já sabe *quanto* cada lance custou (Stockfish) e classifica alguns erros
(`heuristics.py`). A maior parte ainda cai em "Outros erros". Este roteiro leva o projeto
dessa base até um componente de ML que você consiga explicar numa entrevista.

A regra do jogo: **você implementa, eu reviso.** Cada fase tem um entregável que pode ir
para o README/portfólio.

---

## Fase 1: Heurísticas (agora)

**Objetivo:** reduzir a fatia de "Outros erros" com regras que você entende e testa.

1. **Exercício 1: `hanging_piece`** (peça deixada de graça). Testes em `tests/test_heuristics.py`.
2. **Exercício 2: `missed_tactic`** (golpe que você não viu: captura vantajosa ou garfo).
3. **Exercício 3 (livre), escolha um ou mais:**
   - *Vantagem jogada fora:* estava com +3 ou mais e o lance derrubou para menos de +1
     (`ctx.eval_before`, `ctx.eval_after`).
   - *Erro com pouco tempo:* o erro aconteceu com `ctx.time_pressure`. Vale como categoria
     própria, ou como "etiqueta" extra além do tipo?
   - *Troca ruim:* trocou uma peça ativa por uma passiva. Mais difícil: como medir "ativa"?
     (mobilidade = `len(list(board.legal_moves))` com aquela peça…)

**Como medir se ficou bom**

- *Cobertura:* % de erros que deixam de ser "Outros". Meta inicial: menos da metade.
- *Precisão:* sorteie 20 erros classificados e confira à mão. Você joga a 2000; seu
  julgamento é o "rótulo verdadeiro". Anote acertos e erros numa planilha.
- Para cada regra, escreva **um teste novo a partir de uma posição real** das suas partidas
  em que a regra errou. É assim que heurística melhora.

**Entregável:** tabela no README com cobertura e precisão de cada heurística.

---

## Fase 2: Montar o dataset

**Objetivo:** transformar lances em linhas de uma tabela (features + rótulo).

- Um lance = uma linha. **Rótulo:** foi erro grave? (`severity in ('mistake', 'blunder')`).
- **Features** possíveis (todas calculáveis com python-chess + as colunas que já existem):
  fase, relógio restante, fração do tempo usada no lance, avaliação antes, material de cada
  lado, número de lances legais, está em xeque?, peça movida, foi captura?, número de peças
  atacadas/penduradas na posição, rating do oponente…
- **Mais dados:** 30 partidas é pouco. Importe centenas das suas e de outros jogadores.
  O [banco aberto do Lichess](https://database.lichess.org/) tem milhões de partidas em PGN, e
  parte delas já vem com avaliações `[%eval]`: dá para treinar sem rodar o Stockfish em tudo.
- Ferramentas: `pandas`, um notebook (`notebooks/01_dataset.ipynb`).

**Entregável:** script `build_dataset.py` que gera um `dataset.parquet` reprodutível.

---

## Fase 3: Primeiro modelo: "chance de errar"

**Objetivo:** prever a probabilidade de um lance ser erro grave, dada a posição e o contexto.

1. **Baseline primeiro:** regressão logística (scikit-learn). Sempre compare contra ela.
2. Depois: gradient boosting (`HistGradientBoostingClassifier` do scikit-learn, ou LightGBM).
3. **Cuidado com vazamento de dados:** lances da mesma partida são parecidos. Separe treino e
   teste **por partida** (`GroupKFold` com `groups=game_id`), não por lance. Esse é um ponto
   clássico de entrevista.
4. **Métricas:** classes desbalanceadas (poucos erros). Use ROC-AUC e **PR-AUC**, não acurácia.
5. **Interpretação:** importância de features / SHAP. Isso vira insight no produto:
   *"suas chances de errar dobram quando restam menos de 20 s e há mais de 35 lances legais"*.

**Entregável:** notebook com baseline × modelo, curva PR e as 5 features mais importantes.

---

## Fase 4: Descobrir tipos de erro (não supervisionado)

**Objetivo:** deixar os dados sugerirem categorias que suas heurísticas não cobrem.

- Pegue só os erros graves, use as features da Fase 2 e agrupe (K-Means ou HDBSCAN).
- Olhe 5 posições de cada grupo e dê um nome. Algum grupo bate com suas heurísticas? Algum é
  novo? Novo grupo = nova heurística (volta para a Fase 1).

**Entregável:** seção "Tipos de erro descobertos" no README, com exemplos de cada grupo.

---

## Fase 5 (avançado, opcional)

- **Modelo de lance humano:** o projeto [Maia Chess](https://maiachess.com/) (McIlroy-Young et al.,
  2020) treina redes que preveem o lance que um humano de certo rating jogaria. Ideia: medir
  quanto os seus lances se parecem com os de jogadores mais fortes, por fase.
- **Plano de treino:** usar a "chance de errar" por tipo de posição para escolher quais
  posições mostrar no treino diário (repetição espaçada).

---

## Como trabalhar comigo em cada fase

1. Você me conta a ideia (ou o pseudocódigo) **antes** de codar; eu aponto furos.
2. Você implementa e roda os testes.
3. Você me manda o diff (ou eu leio o arquivo) e eu faço **code review**, como num PR.
4. Se travar, peça **dica nível 1** (direção), **nível 2** (qual função usar) ou **nível 3**
   (pseudocódigo). Código pronto só como último recurso.
