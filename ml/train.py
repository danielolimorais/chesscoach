"""Treina e avalia o modelo de "chance de errar" (o lance vai ser erro grave?).

Uso:
    python -m ml.train SEU_NICK                # validação cruzada + teste temporal + relatório
    python -m ml.train SEU_NICK --no-behavior  # sem time_spent (modelo estritamente preditivo)
    python -m ml.train SEU_NICK --equilibradas # só posições com |avaliação| <= 3 peões

O que ele faz:
  1. Monta o dataset (ml/dataset.py).
  2. Compara três modelos com validação cruzada AGRUPADA POR PARTIDA (GroupKFold):
       - linha de base trivial (sempre prevê a taxa média de erros)
       - regressão logística (com padronização)
       - gradient boosting (HistGradientBoostingClassifier)
     Agrupar por partida evita vazamento: lances da mesma partida são parecidos, e se uns caem
     no treino e outros no teste o modelo parece melhor do que é.
  3. Teste temporal: treina nas partidas mais antigas e testa nas 20% mais recentes,
     que é como o modelo seria usado de verdade.
  4. Mostra as features mais importantes e a taxa de erro real por faixa de risco prevista.

Métricas: ROC-AUC e PR-AUC (average precision). Como só ~11% dos lances são erros graves,
acurácia engana (prever "nunca erra" já acerta 89%). A PR-AUC da linha de base é igual à
taxa de erros; o quanto o modelo passa disso é o que importa.
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import GroupKFold, cross_validate
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from ml.dataset import DEFAULT_DB, build_dataset, feature_columns

RESULTS_DIR = Path(__file__).resolve().parent / "results"
SEED = 42
BALANCED_CP = 300  # posições "em aberto": nenhum lado com mais de 3 peões de vantagem


def make_models() -> dict:
    return {
        "Linha de base (taxa média)": DummyClassifier(strategy="prior"),
        "Regressão logística": make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            LogisticRegression(max_iter=2000, class_weight="balanced"),
        ),
        "Gradient boosting": HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.05, max_leaf_nodes=31, l2_regularization=1.0, random_state=SEED
        ),
    }


def temporal_split(df: pd.DataFrame, test_frac: float = 0.2) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Partidas mais antigas no treino, as `test_frac` mais recentes no teste."""
    order = df.groupby("game_id")["played_at"].first().sort_values()
    cut = int(len(order) * (1 - test_frac))
    test_games = set(order.index[cut:])
    is_test = df["game_id"].isin(test_games)
    return df[~is_test], df[is_test]


def risk_table(y_true: np.ndarray, proba: np.ndarray, bins: int = 5) -> pd.DataFrame:
    """Taxa de erro real em cada quintil de risco previsto (do menor para o maior)."""
    frame = pd.DataFrame({"y": y_true, "p": proba})
    frame["faixa"] = pd.qcut(frame["p"].rank(method="first"), bins, labels=[f"{i + 1}º" for i in range(bins)])
    out = frame.groupby("faixa", observed=True).agg(lances=("y", "size"), erro_real=("y", "mean"), risco_previsto=("p", "mean"))
    return out


def run(df: pd.DataFrame, behavior: bool = True, folds: int = 5) -> dict:
    features = feature_columns(df, behavior=behavior)
    X, y, groups = df[features], df["y"].to_numpy(), df["game_id"].to_numpy()

    results: dict = {"features": features, "cv": {}, "n": len(df), "games": df["game_id"].nunique(), "rate": y.mean()}

    cv = GroupKFold(n_splits=folds)
    for name, model in make_models().items():
        scores = cross_validate(model, X, y, groups=groups, cv=cv, scoring=["roc_auc", "average_precision"])
        results["cv"][name] = {
            "roc_auc": (scores["test_roc_auc"].mean(), scores["test_roc_auc"].std()),
            "pr_auc": (scores["test_average_precision"].mean(), scores["test_average_precision"].std()),
        }

    train, test = temporal_split(df)
    results["temporal"] = {"train_games": train["game_id"].nunique(), "test_games": test["game_id"].nunique(), "models": {}}
    fitted = {}
    for name, model in make_models().items():
        model.fit(train[features], train["y"])
        proba = model.predict_proba(test[features])[:, 1]
        fitted[name] = (model, proba)
        results["temporal"]["models"][name] = {
            "roc_auc": roc_auc_score(test["y"], proba),
            "pr_auc": average_precision_score(test["y"], proba),
        }

    # Interpretação
    logreg = fitted["Regressão logística"][0]
    coefs = pd.Series(logreg[-1].coef_[0], index=features).sort_values(key=np.abs, ascending=False)
    results["logreg_coefs"] = coefs

    gb, gb_proba = fitted["Gradient boosting"]
    perm = permutation_importance(
        gb, test[features], test["y"], scoring="average_precision", n_repeats=5, random_state=SEED, n_jobs=-1
    )
    results["gb_importance"] = pd.Series(perm.importances_mean, index=features).sort_values(ascending=False)
    results["risk_table"] = risk_table(test["y"].to_numpy(), gb_proba)
    return results


def render_report(username: str, r: dict, behavior: bool) -> str:
    lines = [
        f"# Modelo de chance de errar: {username}",
        "",
        f"Gerado em {datetime.now():%d/%m/%Y %H:%M}. {r['n']} lances de {r['games']} partidas; "
        f"{r['rate']:.1%} são erros graves (erro ou blunder).",
        f"Features: {len(r['features'])}" + ("" if behavior else " (sem time_spent)") + ".",
        "",
        "## Validação cruzada agrupada por partida (5 folds)",
        "",
        "| Modelo | ROC-AUC | PR-AUC |",
        "|---|---|---|",
    ]
    for name, m in r["cv"].items():
        lines.append(f"| {name} | {m['roc_auc'][0]:.3f} ± {m['roc_auc'][1]:.3f} | {m['pr_auc'][0]:.3f} ± {m['pr_auc'][1]:.3f} |")
    t = r["temporal"]
    lines += [
        "",
        f"## Teste temporal (treino: {t['train_games']} partidas mais antigas; teste: {t['test_games']} mais recentes)",
        "",
        "| Modelo | ROC-AUC | PR-AUC |",
        "|---|---|---|",
    ]
    for name, m in t["models"].items():
        lines.append(f"| {name} | {m['roc_auc']:.3f} | {m['pr_auc']:.3f} |")
    lines += [
        "",
        "## Taxa de erro real por faixa de risco (gradient boosting, teste temporal)",
        "",
        "| Faixa de risco | Lances | Erro real | Risco previsto |",
        "|---|---|---|---|",
    ]
    for faixa, row in r["risk_table"].iterrows():
        lines.append(f"| {faixa} | {int(row['lances'])} | {row['erro_real']:.1%} | {row['risco_previsto']:.1%} |")
    lines += ["", "## Features mais importantes", "", "**Gradient boosting** (queda na PR-AUC ao embaralhar a feature):", ""]
    for name, value in r["gb_importance"].head(10).items():
        lines.append(f"- `{name}`: {value:+.4f}")
    lines += ["", "**Regressão logística** (coeficientes padronizados; positivo = aumenta a chance de erro):", ""]
    for name, value in r["logreg_coefs"].head(10).items():
        lines.append(f"- `{name}`: {value:+.3f}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Treina o modelo de chance de errar.")
    parser.add_argument("username")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--no-behavior", action="store_true", help="remove time_spent das features")
    parser.add_argument(
        "--equilibradas", action="store_true",
        help=f"usa só posições equilibradas (|avaliação| <= {BALANCED_CP} cp), onde o erro depende mais de você",
    )
    args = parser.parse_args(argv)

    with sqlite3.connect(args.db) as conn:
        df = build_dataset(conn, args.username)
    if args.equilibradas and not df.empty:
        df = df[df["abs_eval"] <= BALANCED_CP].reset_index(drop=True)
    if df.empty or df["game_id"].nunique() < 20:
        print("Poucas partidas analisadas (mínimo 20). Rode o analyze_all.py antes.")
        return 1

    behavior = not args.no_behavior
    report = render_report(args.username, run(df, behavior=behavior), behavior)
    if args.equilibradas:
        report = report.replace("\n\n", f"\n\nSó posições equilibradas (|avaliação| <= {BALANCED_CP} cp).\n\n", 1)
    RESULTS_DIR.mkdir(exist_ok=True)
    suffix = ("" if behavior else "_sem_tempo") + ("_equilibradas" if args.equilibradas else "")
    out = RESULTS_DIR / f"{args.username.lower()}{suffix}.md"
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"Relatório salvo em {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
