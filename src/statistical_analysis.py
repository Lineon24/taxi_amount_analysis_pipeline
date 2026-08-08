"""전처리 완료 데이터의 가설을 검정하는 통계 분석 스크립트.

RatecodeID 0(flex fare)과 1(일반)의 마일당 요금을 비교하고, 거리와 요금의
상관계수, Mann–Whitney U 검정, Welch t-test 및 효과크기를 콘솔에 출력한다.
모델 학습이나 차트 생성은 수행하지 않는다.

# ── 이준희 리뷰 메모 ──────────────────────────────────────────────────────────
# 양방향 가설을 다 확인해보려고 alternative='greater'와 'less'를 둘 다 돌린 부분이
# 눈에 띔. 보통 한쪽 방향만 정하고 끝내는데, 여기선 두 방향 p-value를 다 보여줘서
# "어느 쪽이 더 비싼지"를 데이터가 열어놓고 판단하게 한 느낌.
# 다만 Mann-Whitney(비모수, non-parametric)와 Welch's t-test(모수적) 결과를
# 둘 다 보여주면서 두 검정이 서로 다른 결론을 낼 경우 어떻게 해석할지에 대한
# 코멘트는 없어서, 그 부분은 리포트 볼 때 직접 판단해야 할 듯.
# ────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from scipy import stats


SRC_DIR = Path(__file__).resolve().parent
PIPELINE_DIR = SRC_DIR.parent
DATA_PATH = PIPELINE_DIR / "data" / "processed" / "clean_train_with_ids.csv"
REQUIRED_COLUMNS = {"RatecodeID", "trip_distance", "fare_ex_tip"}
RATECODE_LABELS = {0: "flex fare", 1: "일반"}


def section(title: str) -> None:
    """콘솔 출력에서 분석 단계를 구분한다."""
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def load_data(path: Path = DATA_PATH) -> pd.DataFrame:
    """전처리 산출물을 읽고 통계 분석 계약을 검증한다."""
    if not path.is_file():
        raise FileNotFoundError(
            f"통계 분석 데이터가 없습니다: {path}\n"
            "src/data_preprocessing.py를 먼저 실행하세요."
        )
    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        raise RuntimeError(f"CSV 로딩에 실패했습니다: {path}") from exc
    missing = sorted(REQUIRED_COLUMNS - set(frame.columns))
    if missing:
        raise ValueError(f"통계 데이터에 필수 컬럼이 없습니다: {missing}")
    if frame.empty:
        raise ValueError("통계 분석 데이터가 비어 있습니다.")
    if frame["trip_distance"].le(0).any():
        raise ValueError("trip_distance에 0 이하 값이 있어 마일당 요금을 계산할 수 없습니다.")
    return frame


def rank_biserial(u_statistic: float, n_a: int, n_b: int) -> float:
    """Mann–Whitney U 통계량을 rank-biserial 효과크기로 변환한다."""
    # 이준희 리뷰: p-value만 보고 끝내지 않고 효과크기(effect size, 이펙트 사이즈 —
    # 차이가 통계적으로 유의한지를 넘어 "얼마나 큰 차이인지"를 나타내는 지표)까지
    # 계산해주는 점이 좋음. 표본이 워낙 크면 아주 작은 차이도 p-value가 낮게
    # 나올 수 있어서, 이 값이 없으면 차이의 실질적 크기를 가늠하기 어려웠을 것.
    if n_a == 0 or n_b == 0:
        raise ValueError("효과크기 계산에 필요한 비교 집단이 비어 있습니다.")
    return (2 * u_statistic) / (n_a * n_b) - 1


def main() -> None:
    """기술통계, 상관분석과 두 집단 가설검정을 순서대로 실행한다."""
    pd.set_option("display.width", 140)
    train = load_data()
    train["fare_per_mile"] = train["fare_ex_tip"] / train["trip_distance"]
    subset = train.loc[train["RatecodeID"].isin(RATECODE_LABELS)].copy()
    subset["그룹"] = subset["RatecodeID"].map(RATECODE_LABELS)
    g0 = subset.loc[subset["RatecodeID"].eq(0), "fare_per_mile"]
    g1 = subset.loc[subset["RatecodeID"].eq(1), "fare_per_mile"]
    if g0.empty or g1.empty:
        raise ValueError("RatecodeID 0 또는 1 비교 집단이 비어 있습니다.")

    section("1. 기술통계 (RatecodeID 0=flex vs 1=일반)")
    description = subset.groupby("그룹")[["fare_per_mile", "trip_distance"]].describe().round(3)
    print(description.T)

    section("2. 상관계수: trip_distance ↔ fare_ex_tip")
    # 이준희 리뷰: Pearson(피어슨, 선형관계 가정)과 Spearman(스피어만, 순위 기반이라
    # 비선형·이상치에 더 강건) 둘 다 뽑아본 것도 같은 맥락. 하나만 보고 판단하면
    # 이상치나 비선형 구간을 놓칠 수 있는데 두 지표를 나란히 두면 서로 검증이 됨.
    rho, p_spearman = stats.spearmanr(train["trip_distance"], train["fare_ex_tip"])
    pearson_r, p_pearson = stats.pearsonr(train["trip_distance"], train["fare_ex_tip"])
    print(f"Spearman rho = {rho:.4f}, p-value = {p_spearman:.4g}")
    print(f"Pearson r    = {pearson_r:.4f}, p-value = {p_pearson:.4g}")

    section("3. 가설1 검정: RatecodeID=0(flex) vs 1(일반) fare_per_mile")
    n0, n1 = len(g0), len(g1)
    print(f"n0(flex)={n0:,}, n1(일반)={n1:,}")
    print("H0: 두 그룹의 fare_per_mile 분포에는 차이가 없다")
    print("H1(원래): flex(0)의 fare_per_mile이 일반(1)보다 높다")
    print("H1(반대방향): flex(0)의 fare_per_mile이 일반(1)보다 낮다\n")

    u_greater, p_greater = stats.mannwhitneyu(g0, g1, alternative="greater")
    u_less, p_less = stats.mannwhitneyu(g0, g1, alternative="less")
    effect = rank_biserial(u_less, n0, n1)
    print(f"Mann-Whitney U (alternative='greater'): U={u_greater:.3e}, p={p_greater:.4g}")
    print(f"Mann-Whitney U (alternative='less'):    U={u_less:.3e}, p={p_less:.4g}")
    print(f"효과크기(rank-biserial correlation) = {effect:.4f}")

    t_stat, p_t = stats.ttest_ind(g0, g1, equal_var=False)
    print(f"\nWelch's t-test: t={t_stat:.3f}, p={p_t:.4g}")
    print(f"\n중앙값: flex=${g0.median():.2f}, 일반=${g1.median():.2f}")
    print(f"평균:   flex=${g0.mean():.2f}, 일반=${g1.mean():.2f}")
    print(
        "거리 중앙값: "
        f"flex={subset.loc[subset['RatecodeID'].eq(0), 'trip_distance'].median():.2f}mi, "
        f"일반={subset.loc[subset['RatecodeID'].eq(1), 'trip_distance'].median():.2f}mi"
    )
    print("\n완료.")


if __name__ == "__main__":
    main()
