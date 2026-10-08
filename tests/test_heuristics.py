"""Testes das heurísticas de tipo de erro.

Os testes marcados com `exercicio` testam funções que você vai implementar em heuristics.py.
Enquanto elas levantam NotImplementedError, aparecem como "xfail". Quando você implementar
corretamente, passam a aparecer como "XPASS"; então apague a linha `@exercicio` daquele teste.

    python -m pytest tests/test_heuristics.py -v
"""

import chess
import pytest

from heuristics import (
    MistakeContext,
    allowed_mate,
    classify_mistake,
    hanging_piece,
    missed_mate,
    missed_tactic,
)

exercicio = pytest.mark.xfail(raises=NotImplementedError, reason="exercício ainda não implementado")


def ctx_from(
    position: str,
    played: str,
    best: str | None = None,
    reply: str | None = None,
    mate_before: int | None = None,
    mate_after: int | None = None,
) -> MistakeContext:
    """`position` é uma FEN ou uma sequência de lances a partir da posição inicial ("e4 d6").

    `played`, `best` e `reply` são lances em notação SAN.
    """
    if "/" in position:
        board = chess.Board(position)
    else:
        board = chess.Board()
        for san in position.split():
            board.push_san(san)
    played_move = board.parse_san(played)
    best_move = board.parse_san(best) if best else None
    reply_move = None
    if reply:
        after = board.copy()
        after.push(played_move)
        reply_move = after.parse_san(reply)
    return MistakeContext(
        board=board,
        played=played_move,
        best=best_move,
        reply=reply_move,
        eval_before=0,
        eval_after=-300,
        mate_before=mate_before,
        mate_after=mate_after,
        phase="opening",
        time_pressure=False,
    )


# ------------------------------------------------------------------ exemplos prontos

def test_allowed_mate_fools_mate():
    # 1.f3 e5 2.g4?? e as pretas têm Qh4#
    ctx = ctx_from("f3 e5", "g4", best="Nc3", reply="Qh4#", mate_after=-1)
    assert allowed_mate(ctx)
    assert classify_mistake(ctx) == "allowed_mate"


def test_allowed_mate_requires_that_you_were_not_already_lost():
    ctx = ctx_from("f3 e5", "g4", mate_before=-3, mate_after=-1)
    assert not allowed_mate(ctx)


def test_missed_mate():
    ctx = ctx_from("e4 e5 Bc4 Nc6 Qh5 Nf6", "Qf3", best="Qxf7#", mate_before=1, mate_after=None)
    assert missed_mate(ctx)
    still_mating = ctx_from("e4 e5 Bc4 Nc6 Qh5 Nf6", "Qf3", best="Qxf7#", mate_before=1, mate_after=3)
    assert not missed_mate(still_mating)


def test_unknown_error_is_other():
    assert classify_mistake(ctx_from("e4 e5", "Nf3")) == "other"


# ------------------------------------------------------------------ exercício 1: hanging_piece

@exercicio
def test_hanging_queen():
    # 1.e4 d6 2.Qg4?? e o bispo de c8 captura a dama de graça
    assert hanging_piece(ctx_from("e4 d6", "Qg4", best="Nf3", reply="Bxg4"))


@exercicio
def test_quiet_reply_is_not_hanging():
    assert not hanging_piece(ctx_from("e4 d6", "Nf3", best="d4", reply="Bg4"))


@exercicio
def test_won_a_pawn_but_lost_the_knight():
    # 3.Nxe5?? ganha um peão, mas o cavalo em e5 não tem defensor: Nxe5
    assert hanging_piece(ctx_from("e4 e5 Nf3 Nc6", "Nxe5", best="Bb5", reply="Nxe5"))


@exercicio
def test_even_trade_is_not_hanging():
    # 4.Bxc6 dxc6: bispo por cavalo é troca, não peça de graça
    assert not hanging_piece(ctx_from("e4 e5 Nf3 Nc6 Bb5 a6", "Bxc6", best="Ba4", reply="dxc6"))


@exercicio
def test_defended_piece_is_not_hanging():
    # Cavalo em d5 defendido pelo peão e4: se o cavalo preto em f6 tomar, e4xd5 recaptura
    assert not hanging_piece(ctx_from("e4 e5 Nc3 Nf6", "Nd5", best="Nf3", reply="Nxd5"))


# ------------------------------------------------------------------ exercício 2: missed_tactic

@exercicio
def test_missed_free_queen():
    # A torre em d2 podia capturar a dama indefesa em d5
    assert missed_tactic(ctx_from("4k3/8/8/3q4/8/8/3R4/4K3 w - - 0 1", "Ke2", best="Rxd5"))


@exercicio
def test_missed_knight_fork():
    # Nc7+ ataca o rei em e8 e a torre em a8 ao mesmo tempo
    assert missed_tactic(ctx_from("r3k3/8/8/1N6/8/8/8/4K3 w - - 0 1", "Ke2", best="Nc7+"))


@exercicio
def test_capture_of_defended_piece_is_not_a_tactic():
    # Rxd6 ganharia um cavalo mas perderia a torre (exd6): não é golpe
    assert not missed_tactic(ctx_from("4k3/4p3/3n4/8/8/8/3R4/4K3 w - - 0 1", "Ke2", best="Rxd6"))


@exercicio
def test_quiet_best_move_is_not_a_tactic():
    assert not missed_tactic(ctx_from("4k3/8/8/8/8/8/3R4/4K3 w - - 0 1", "Kf2", best="Ke2"))


def test_playing_the_best_move_is_never_a_missed_tactic():
    # Funciona mesmo antes do exercício: se você jogou o melhor lance, não perdeu nada.
    ctx = ctx_from("4k3/8/8/3q4/8/8/3R4/4K3 w - - 0 1", "Rxd5", best="Rxd5")
    try:
        assert not missed_tactic(ctx)
    except NotImplementedError:
        pytest.skip("exercício ainda não implementado")
