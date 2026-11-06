"""Heurísticas: que TIPO de erro foi cometido?

O Stockfish diz *quanto* um lance custou. Este módulo tenta dizer *por quê*: deixou uma peça
de graça? Permitiu um mate? Deixou passar uma tática?

Como é usado
------------
Na hora de montar o relatório, para cada lance seu classificado como "erro" ou "blunder",
o `report.py` cria um `MistakeContext` e chama `classify_mistake(ctx)`. Os detectores em
`DETECTORS` são testados em ordem; o primeiro que responder `True` dá nome ao erro. Se nenhum
reconhecer, o erro entra como "Outros erros".

Como a classificação é feita sobre dados já salvos no banco, basta salvar este arquivo e
recarregar o relatório para ver o efeito. Não é preciso analisar de novo com o Stockfish.

Seus exercícios
---------------
`allowed_mate`, `missed_mate` e `hanging_piece` estão prontos e servem de exemplo.
`missed_tactic` é seu: enquanto levantar `NotImplementedError`, é simplesmente pulado.

    python -m pytest tests/test_heuristics.py -v

Os testes dele começam como "xfail" (falha esperada). Quando sua implementação estiver
certa, eles passam a aparecer como "XPASS"; aí remova o marcador `@exercicio` do teste.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import chess

# Valor das peças em "peões". O rei vale 0 porque nunca é capturado de fato.
PIECE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}

CATEGORY_LABELS = {
    "allowed_mate": "Permitiu mate",
    "missed_mate": "Deixou passar um mate",
    "hanging_piece": "Peça deixada de graça",
    "missed_tactic": "Tática não aproveitada",
    "other": "Outros erros",
}


@dataclass(frozen=True)
class MistakeContext:
    """Tudo o que se sabe sobre um lance errado. "Você" = quem fez o lance."""

    board: chess.Board  # posição ANTES do seu lance (é a sua vez)
    played: chess.Move  # o lance que você jogou
    best: chess.Move | None  # o melhor lance segundo o Stockfish
    reply: chess.Move | None  # melhor resposta do adversário DEPOIS do seu lance (Stockfish)
    eval_before: int | None  # avaliação antes do lance, do SEU ponto de vista, em centipeões (±1000 no máximo)
    eval_after: int | None  # avaliação depois do lance, do seu ponto de vista
    mate_before: int | None  # mate em N antes do lance: positivo = você dá mate, negativo = você leva
    mate_after: int | None  # o mesmo, depois do lance
    phase: str  # "opening" | "middlegame" | "endgame"
    time_pressure: bool  # se você estava com pouco tempo no relógio

    @property
    def me(self) -> chess.Color:
        return self.board.turn

    def board_after(self) -> chess.Board:
        """Cópia da posição depois do seu lance (é a vez do adversário)."""
        after = self.board.copy(stack=False)
        after.push(self.played)
        return after


def piece_value(piece: chess.Piece | None) -> int:
    return PIECE_VALUES[piece.piece_type] if piece else 0


# --------------------------------------------------------------------------------------------
# Exemplos prontos
# --------------------------------------------------------------------------------------------

def allowed_mate(ctx: MistakeContext) -> bool:
    """Depois do seu lance o adversário passou a ter mate forçado (e antes não tinha)."""
    being_mated_after = ctx.mate_after is not None and ctx.mate_after < 0
    being_mated_before = ctx.mate_before is not None and ctx.mate_before < 0
    return being_mated_after and not being_mated_before


def missed_mate(ctx: MistakeContext) -> bool:
    """Você tinha mate forçado e, depois do lance jogado, não tem mais."""
    had_mate = ctx.mate_before is not None and ctx.mate_before > 0
    still_mating = ctx.mate_after is not None and ctx.mate_after > 0
    return had_mate and not still_mating


# --------------------------------------------------------------------------------------------
# Exercícios
# --------------------------------------------------------------------------------------------

HANGING_THRESHOLD = 2  # saldo mínimo (em peões) para considerar material "de graça"


def captured_value(board: chess.Board, move: chess.Move) -> int:
    """Valor da peça que `move` captura (0 se não for captura)."""
    if not board.is_capture(move):
        return 0
    if board.is_en_passant(move):
        return PIECE_VALUES[chess.PAWN]  # no en passant a casa de destino está vazia
    return piece_value(board.piece_at(move.to_square))


def material_gain(board: chess.Board, move: chess.Move) -> int:
    """Saldo de material, para quem joga `move`, depois de UMA rodada de troca.

    saldo = (o que `move` captura) − (a peça que se moveu, se o adversário puder recapturar)

    Exemplos (rodada única, sem olhar trocas mais longas):
      - Bispo toma cavalo indefeso:          3 − 0 = +3
      - Bispo toma cavalo defendido:         3 − 3 =  0 (troca)
      - Dama toma peão defendido:            1 − 9 = −8
    Limitação conhecida: não simula sequências de várias capturas na mesma casa
    (isso seria a "static exchange evaluation" completa, uma boa melhoria futura).
    """
    gained = captured_value(board, move)
    if gained == 0:
        return 0
    mover = board.piece_at(move.from_square)
    after = board.copy(stack=False)
    after.push(move)
    # Depois do lance é a vez do adversário (`after.turn`): ele ataca a casa de destino?
    recapture_possible = after.is_attacked_by(after.turn, move.to_square)
    lost = piece_value(mover) if recapture_possible else 0
    return gained - lost


def hanging_piece(ctx: MistakeContext) -> bool:
    """O seu lance deixou material de graça para o adversário.

    saldo do adversário = material_gain(da resposta dele) − o que você capturou no seu lance
    Se esse saldo for de HANGING_THRESHOLD peões ou mais, a peça ficou pendurada.

    Por que descontar a sua captura: em 1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Bxc6 dxc6 o adversário
    "ganha" o bispo, mas você já tinha levado o cavalo: é troca, não peça de graça.
    """
    if ctx.reply is None:
        return False
    after = ctx.board_after()
    if not after.is_capture(ctx.reply):
        return False
    opponent_gain = material_gain(after, ctx.reply)
    my_gain = captured_value(ctx.board, ctx.played)
    return opponent_gain - my_gain >= HANGING_THRESHOLD


def missed_tactic(ctx: MistakeContext) -> bool:
    """EXERCÍCIO 2: havia um golpe tático e você jogou outra coisa.

    Ideia: o melhor lance (`ctx.best`) ganhava material de forma imediata e você não o jogou.
    Uma primeira definição razoável, se `ctx.best` existir e for diferente de `ctx.played`:
      a) `ctx.best` é uma captura que ganha 2 peões ou mais (mesmo raciocínio do exercício 1,
         considerando a recaptura); OU
      b) `ctx.best` é um garfo: depois dele, a peça que se moveu ataca 2 ou mais peças
         adversárias que valem 3 ou mais (ou o rei). Dica: `board.attacks(casa)`.

    Para (a), `material_gain(ctx.board, ctx.best)` já calcula o saldo com recaptura.
    Para (b), jogue `ctx.best` numa cópia do tabuleiro e olhe `copia.attacks(ctx.best.to_square)`.

    Os casos de teste estão em tests/test_heuristics.py (procure por "tactic").
    """
    raise NotImplementedError


# Ordem importa: o primeiro detector que reconhecer o erro dá o nome.
DETECTORS: list[tuple[str, Callable[[MistakeContext], bool]]] = [
    ("allowed_mate", allowed_mate),
    ("missed_mate", missed_mate),
    ("hanging_piece", hanging_piece),
    ("missed_tactic", missed_tactic),
]


def classify_mistake(ctx: MistakeContext) -> str:
    """Devolve a categoria do erro (uma chave de CATEGORY_LABELS)."""
    for key, detector in DETECTORS:
        try:
            if detector(ctx):
                return key
        except NotImplementedError:
            continue  # exercício ainda não feito: pula
    return "other"
