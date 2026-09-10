# -*- coding: utf-8 -*-
"""지표 계산.

**지표의 정의는 위키가 원본이다.** 이 파일은 위키에 적힌 정의를 코드로 옮긴 것일 뿐,
여기서 정의를 새로 만들지 않는다. 정의가 바뀌면 위키를 먼저 고친다.

────────────────────────────────────────────────────────────────────
컬럼명은 config.py 가 아니라 **이 파일 안에도** 박혀 있다. 지금은 내 도메인 것으로
바꿔 놓았다 — grn · cat · closure_date · filing_date · Notifier · case_id · stage.

남은 통신사 흔적은 experiment_results() 의 가드레일 분기 하나뿐이다(is_churned ·
customers). 이 도메인엔 실험 테이블이 없어 그 분기는 실행되지 않는다.
────────────────────────────────────────────────────────────────────

계산은 전부 pandas로 한다. 어디서 읽어왔든 입력은 동일한 DataFrame이다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st
from scipy import stats

from core import config as C
from core.load import to_dt


# ── 퍼널 ──────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def funnel(fe: pd.DataFrame, id_col: str | None = None,
           step_col: str = "stage") -> pd.DataFrame:
    """단계별 도달 수와 전환율. 단계 순서는 config.FUNNEL_STEPS 를 따른다.

    ── 그레인 ────────────────────────────────────────────────────
    **확정: 1건 = 과제번호 1개.** id_col 로 준 컬럼(기본 case_id, 실제 데이터는 grn)을
    고유하게 센다 — 같은 단계를 두 번 밟을 수 있는 데이터라 행을 세면 안 된다.
    그래서 행을 세지 않고 **고유 대상 수(nunique)로 센다.**

    두 가지 이유로 중복이 생긴다.

        완전중복 이벤트 행   일부러 섞인 176행.
                            행으로 세면 첫 단계가 2,072, 고유로 세면 2,000이다
        같은 건의 재제출     한 건이 여러 번 접수될 수 있다.
                            id_col 을 무엇으로 주느냐로 이 그레인이 갈린다

    id_col 을 **인자로 둔 이유**가 여기 있다. 그레인은 데이터가 아니라 질문이
    정하는 것이라, 같은 표에서 두 그레인을 각각 계산해 비교할 수 있어야 한다.
    생략하면 아래 후보를 순서대로 찾아 쓴다.

    ── 세는 방식 ─────────────────────────────────────────────────
    각 단계의 도달 수를 **그 단계 이벤트가 있는 고유 대상 수**로 센다.
    앞 단계를 거쳤는지 강제로 맞추지 않는다 — 순서가 깨져 있으면 그것이
    표에 그대로 드러나야 한다. **감추면 검증할 수 없다.**
    (순서 위반 여부는 validate 에서 따로 본다)

    반환: DataFrame[step, label, n, step_rate, cum_rate, drop, is_bottleneck]

        step           config.FUNNEL_STEPS 의 값
        label          config.FUNNEL_LABELS 의 값 (화면 표시용)
        n              그 단계에 도달한 수
        step_rate      전 단계 대비 비율 (첫 단계는 NaN)
        cum_rate       첫 단계 대비 비율
        drop           전 단계에서 빠진 수
        is_bottleneck  step_rate 가 가장 낮은 구간이면 True

    ⚠ step_rate 첫 행은 반드시 **NaN** 이다. 차트가 NaN 여부로 첫 단계를
      가려내므로 0이나 1을 넣으면 표기가 깨진다.

    **손계산과 대조한다.** 이 데이터에는 대조할 실측값이 이미 있다 —
    mydomain/notes/02_퍼널실측.md 의 표와 자리마다 맞아야 한다.
    """
    if id_col is None:
        id_col = next((c for c in ("case_id", "grn", "chain", "visitor_id")
                       if c in fe.columns), fe.columns[0])
    if step_col not in fe.columns:
        raise KeyError(
            f"단계 컬럼 '{step_col}' 이 없습니다. 있는 컬럼: {list(fe.columns)}")

    step = fe[step_col].astype(str)
    rows = []
    for s in C.FUNNEL_STEPS:
        rows.append({
            "step": s,
            "label": C.FUNNEL_LABELS.get(s, s),
            "n": int(fe.loc[step == s, id_col].nunique()),
        })
    f = pd.DataFrame(rows)

    top = f.n.iloc[0]
    prev = f.n.shift(1)
    f["step_rate"] = np.where(prev.notna() & (prev > 0), f.n / prev, np.nan)
    f["cum_rate"] = f.n / top if top else np.nan
    f["drop"] = (prev - f.n).fillna(0).astype(int)

    f["is_bottleneck"] = False
    if f.step_rate.notna().any():
        f.loc[f.step_rate.idxmin(), "is_bottleneck"] = True
    return f


#: 분류가 안 된 잔여 범주. funnel_by() 가 붙이는 미매칭 라벨과 데이터의 "미상" 이
#: 여기 든다. trust_check() 가 이 목록으로 "정의 안 된 칸"을 가려낸다.
#: "미분류"(bio 의 실제 범주)는 **넣지 않는다** — 그건 비교 대상이다.
_UNMATCHED = "(미매칭)"
_RESIDUAL_LABELS = (_UNMATCHED, "미상")


@st.cache_data(show_spinner=False)
def funnel_by(fe: pd.DataFrame, se: pd.DataFrame, dim: str,
              step_from: str, step_to: str,
              id_col: str | None = None, step_col: str = "stage",
              missing_is_pending: bool = False) -> pd.DataFrame:
    """분해 축(dim)별로 한 구간(step_from → step_to)의 전환율.
    평균 하나로는 어디를 고칠지 모른다.

    ★ Day3 실습 A·B. **판정이 계산보다 먼저다.**

    ── 무엇으로 쪼개나 ─────────────────────────────────────────
    dim 은 분해 축이고 **무엇으로 쪼갤지는 내가 정한다.** 고르는 기준은
    "격차가 보이는가"가 아니라 **"손을 쓸 수 있는가"** 다 — 나눠서 격차가
    보여도 우리가 못 바꾸는 것(국가·계절 같은)이면 분해할 이유가 적다.
    격차가 없는 것도 결과다: 그 축으로는 안 갈린다는 것을 확인한 것이다.

    ── 그레인 ─────────────────────────────────────────────────
    funnel() 과 같다. 행이 아니라 **고유 대상 수**로 센다. step_from 에
    도달한 고유 대상을 dim 값으로 가르고, 그 안에서 step_to 에도 도달한
    비율을 낸다. id_col 을 생략하면 funnel() 과 같은 후보를 순서대로 찾는다.

    dim 값은 se(대상 1행짜리 속성 표)에서 id_col 로 붙인다. se 에 없는
    대상은 버리지 않고 **"(미매칭)" 한 칸으로 모아** 함께 낸다 — 분류 밖이
    몇 건인지 화면에 보여야 한다.

    ── 판정을 계산 앞에 둔다 (교안 2-2) ───────────────────────
    각 칸의 **도달·전환(원시 카운트)만** 먼저 세고 trust_check() 에 물어본다.
    못 믿을 칸은 **전환율·비중을 계산하지 않는다** — NaN 으로 두고 사유만 채운다.
    계산해 놓고 숨기는 것이 아니라, 꺼낼 값 자체를 만들지 않는다.
    통과한 칸만 전환율·비중이 있다.

    missing_is_pending — step_to 도달 실패를 '아직 진행 중'으로 볼지(제출→종결
      구간: True)  '탈락'으로 볼지(종결→결과 구간: False). True 면 (도달 − 전환)을
      trust_check 의 pending 인자로 넘긴다.

    반환: DataFrame[<dim>, 도달, 전환, 전환율, 비중, 사유]  — 도달 큰 칸부터

        <dim>    분해 축의 값 (컬럼 이름은 dim 그대로)
        도달     step_from 에 도달한 고유 대상 수 (표본)
        전환     그중 step_to 에도 도달한 수
        전환율   전환 / 도달       — 사유가 있으면 **NaN** (계산하지 않음)
        비중     도달 / 전체 도달   — 사유가 있으면 **NaN**
        사유     trust_check 결과. 통과하면 None

    ⚠ 전환율·비중은 0~1 분수다. device_compare 차트가 ×100 해서 그린다.
    """
    if id_col is None:
        id_col = next((c for c in ("case_id", "grn", "chain", "visitor_id")
                       if c in fe.columns), fe.columns[0])
    if step_col not in fe.columns:
        raise KeyError(
            f"단계 컬럼 '{step_col}' 이 없습니다. 있는 컬럼: {list(fe.columns)}")

    step = fe[step_col].astype(str)
    reach_from = set(fe.loc[step == step_from, id_col])
    reach_to = set(fe.loc[step == step_to, id_col])

    out_cols = [dim, "도달", "전환", "전환율", "비중", "사유"]
    if not reach_from:
        return pd.DataFrame(columns=out_cols)

    key = next((c for c in (id_col, "case_id", "grn") if c in se.columns),
               se.columns[0])
    attr = se[[key, dim]].drop_duplicates(subset=key)

    d = pd.DataFrame({id_col: sorted(reach_from)})
    d = d.merge(attr, left_on=id_col, right_on=key, how="left")
    if key != id_col and key in d.columns:
        d = d.drop(columns=key)
    d[dim] = d[dim].astype("object")
    d.loc[d[dim].isna(), dim] = _UNMATCHED
    d["_conv"] = d[id_col].isin(reach_to)

    # 1) 원시 카운트만. 아직 지표(전환율·비중)는 만들지 않는다.
    counts = (d.groupby(dim, sort=False)
                .agg(도달=(id_col, "size"), 전환=("_conv", "sum")))
    total = int(counts["도달"].sum())

    # 2) 칸마다 먼저 판정하고, 3) 통과한 칸만 지표를 계산한다.
    rows = []
    for cat, c in counts.iterrows():
        n, conv = int(c["도달"]), int(c["전환"])
        pending = (n - conv) if missing_is_pending else 0
        reason = trust_check(n, pending=pending, category=str(cat))
        rows.append({
            dim: cat, "도달": n, "전환": conv,
            "전환율": np.nan if reason else conv / n,
            "비중": np.nan if reason else n / total,
            "사유": reason,
        })
    return (pd.DataFrame(rows, columns=out_cols)
              .sort_values("도달", ascending=False)
              .reset_index(drop=True))


def funnel_by_verdict(g: pd.DataFrame, reason_col: str = "사유",
                      rate_col: str = "전환율") -> dict:
    """분해 축 하나의 판정. funnel_by() 결과(trust_check 사유 컬럼 포함)를 받아
    "이 축으로 쪼갠 게 주목할 만한가, 아니면 안 갈리는가"를 판정한다.

    ★ Day3 실습 C. 실험이 없어 p값을 못 쓴다 — 격차 **크기**와 표본만 본다.

    순서 (좋은 결과를 먼저 보면 뒤 확인을 대충 하니까 코드로 고정):
      0. trust_check 에 걸린 칸(reason_col 이 채워진 행)은 판정에서 뺀다.
         이미 값이 없다 — 판정할 재료가 아니다.
      1. 남은 칸이 2개 미만            → "차이 없음" (비교할 게 없다)
      2. 남은 칸 간 전환율 격차 < config.MIN_GAP
                                       → "차이 없음 (이 축으로는 안 갈린다)"
      3. 격차 >= config.MIN_GAP        → "주목할 만함"

    가드레일은 없다 — 분해 격차 비교는 개입이 아니라 관찰이다.
    "무엇을 희생했는지 확인되지 않음"을 note 로 함께 돌려준다. 카드에 박는다.

    "통계적으로 유의" 같은 표현은 쓰지 않는다.

    반환: {
        "verdict": str,                판정 배지 문구
        "color":   str,                config.COLORS 의 키 — "warn" | "none"
        "gap":     float | None,       남은 칸 전환율 최대-최소 (0~1)
        "hi", "lo": (칸 이름, 전환율) | None,
        "n_shown": int,  "n_hidden": int,
        "note":    str,                가드레일 부재 문구
    }
    """
    note = "가드레일 없음 — 무엇을 희생했는지 확인되지 않음"
    if reason_col in g.columns:
        shown = g[g[reason_col].isna()]
        n_hidden = int(g[reason_col].notna().sum())
    else:
        shown, n_hidden = g, 0

    out = {"n_shown": len(shown), "n_hidden": n_hidden, "note": note,
           "gap": None, "hi": None, "lo": None}

    if len(shown) < 2:
        return {**out, "verdict": "차이 없음", "color": "none"}

    dcol = shown.columns[0]
    rates = shown[rate_col]
    hi, lo = shown.loc[rates.idxmax()], shown.loc[rates.idxmin()]
    gap = float(rates.max() - rates.min())
    out.update(gap=gap,
               hi=(str(hi[dcol]), float(hi[rate_col])),
               lo=(str(lo[dcol]), float(lo[rate_col])))

    if gap >= C.MIN_GAP:
        return {**out, "verdict": "주목할 만함", "color": "warn"}
    return {**out, "verdict": "차이 없음 (이 축으로는 안 갈린다)", "color": "none"}


# ── 유지 퍼널 ─────────────────────────────────────────────────────
def _company_history(g: pd.DataFrame) -> pd.DataFrame:
    """회사(Notifier)별 제출 이력. 유지 퍼널 세 단계가 모두 이걸 본다.

    그레인은 **회사 1곳**이다. 물질(GRN)에는 재방문이 없지만
    같은 회사가 다른 물질로 다시 오는가는 실재하는 신호다 (명세 5행).

    Notifier 는 자유 입력이라 공백·대소문자가 섞여 있다. strip + 소문자로
    정규화해 묶는다 — 그래도 법인격 표기 차이(Inc. / LLC)까지는 못 맞춘다.
    이 정규화 방식에 따라 회사 수가 ±1% 흔들린다. (notes/04 는 842, 여기는 832)
    """
    gg = g.copy()
    gg["_notif"] = gg["Notifier"].astype(str).str.strip().str.lower()
    gg = gg[gg["Notifier"].notna() & (gg["_notif"] != "")]
    gg["_closed"] = pd.to_datetime(gg.get("closure_date"), errors="coerce")
    gg = gg.sort_values(["_notif", "_closed", "grn"], na_position="last")

    rows = []
    for notif, sub in gg.groupby("_notif", sort=False):
        cats = sub["cat"].tolist()               # 종결일 순
        rows.append({
            "notifier": notif,
            "n_sub": len(sub),
            "revisit_ok": len(cats) >= 2 and ("no_questions" in cats[1:]),
        })
    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False)
def retention_funnel(t: dict) -> pd.DataFrame:
    """유지 퍼널. config.RETENTION_STEPS 의 단계대로 센다. "데려온 대상이 남는가."

    그레인 = 회사(Notifier) 1곳.  단계(coupled to config):

        통지자        한 번이라도 GRN을 제출한 회사
        다회 제출     GRN을 2건 이상 제출한 회사
        재방문도 성공  다회 제출 회사 중, 첫 건 이후 제출에 no_questions 가 하나라도

    ⚠ 코호트(관측 기간) 필터를 두지 않는다. 오래된 회사가 유리하다 —
      생존 편향이 남는다. notes/04 의 3년 고정창 값(재방문율 20.06%)과
      다르다. 차이는 리포트 7장 한계로. → config.RETENTION_STEPS 주석

    ⚠ 이 세 단계는 정의가 서로 겹친다(뒤 단계 조건이 앞 조건을 포함).
      그래서 부분집합이 **구조적으로** 성립한다 — "진짜 퍼널인가" 판정은
      순서 위반 수만으로는 약하다. retention_order_check() 참조.

    반환: DataFrame[step, label, n, step_rate, cum_rate]
    """
    steps = C.RETENTION_STEPS
    if not steps:
        return pd.DataFrame(columns=["step", "label", "n", "step_rate", "cum_rate"])

    hist = _company_history(t["GRASNotices"])
    counts = {
        "통지자": len(hist),
        "다회 제출": int((hist.n_sub >= 2).sum()),
        "재방문도 성공": int(hist.revisit_ok.sum()),
    }
    expected = ["통지자", "다회 제출", "재방문도 성공"]
    if [name for name, _ in steps] != expected:
        raise ValueError(
            f"retention_funnel() 은 {expected} 단계에 맞춰 짜였습니다. "
            f"config.RETENTION_STEPS 를 {[n for n, _ in steps]} 로 바꾸려면 "
            f"이 함수의 counts 분기도 함께 고치십시오.")

    n = [counts[name] for name, _ in steps]
    f = pd.DataFrame({"step": [s for s, _ in steps],
                      "label": [s for s, _ in steps], "n": n})
    prev = f.n.shift(1)
    f["step_rate"] = np.where(prev.notna() & (prev > 0), f.n / prev, np.nan)
    f["cum_rate"] = f.n / f.n.iloc[0] if f.n.iloc[0] else np.nan
    return f


def retention_order_check(t: dict) -> pd.DataFrame:
    """앞 단계를 거치지 않고 다음 단계에 나타난 회사가 몇 곳인가.

    많으면 이건 퍼널이 아니라 분류다. 다만 이 세 단계는 뒤 조건이 앞 조건을
    포함하도록 정의돼 있어 위반 수는 **구조적으로 0**이다 — 그 사실을
    확인하는 것도 결과다.

    반환: DataFrame[구간, 뒷단계_n, 앞단계_미충족, 판정]
    """
    hist = _company_history(t["GRASNotices"])
    s1 = set(hist.notifier)
    s2 = set(hist.loc[hist.n_sub >= 2, "notifier"])
    s3 = set(hist.loc[hist.revisit_ok, "notifier"])
    rows = [
        ("통지자 → 다회 제출", len(s2), len(s2 - s1)),
        ("다회 제출 → 재방문도 성공", len(s3), len(s3 - s2)),
    ]
    out = pd.DataFrame(rows, columns=["구간", "뒷단계_n", "앞단계_미충족"])
    out["판정"] = np.where(out.앞단계_미충족 == 0, "부분집합 성립", "퍼널 아님")
    return out


# ── vintage (제출 시점별 전환) ────────────────────────────────────
_MATURE_CLOSED = 90.0   # 제출→종결 이 이 %를 넘으면 "성숙한" 묶음으로 본다


@st.cache_data(show_spinner=False)
def funnel_by_vintage(t: dict, bucket_size: int = 50,
                      recent_buckets: int = 6) -> pd.DataFrame:
    """제출 시점별로 묶어 다음 단계 도달률을 본다.

    "시작 시점" 프록시는 **GRN 번호**다. 제출 시 순차 부여되어 종결일 순위와
    상관 0.999 — 접수일(2016년 이후 비공개)이 없어도 제출 순서를 알 수 있다.

    가장 최근 recent_buckets 개 묶음만 bucket_size 개씩 자르고, 그보다 오래된
    것은 "그 이전" 한 줄로 합친다. 최근 꼬리를 확대해 보는 것이 목적이다.

    반환: DataFrame[묶음, n, 성공, 미종결, 반려,
                    제출_종결, 종결_성공, 누적_성공, 종결시기]
          비율 세 컬럼은 % 숫자(float).
    """
    cols = ["묶음", "n", "성공", "미종결", "반려",
            "제출_종결", "종결_성공", "누적_성공", "종결시기"]
    if "GRASNotices" not in t:
        return pd.DataFrame(columns=cols)

    g = t["GRASNotices"][["grn", "cat", "closure_date"]].copy()
    g = g.sort_values("grn").reset_index(drop=True)
    g["cd"] = pd.to_datetime(g["closure_date"], errors="coerce")

    recent_n = bucket_size * recent_buckets
    edge = max(len(g) - recent_n, 0)
    labels, lo = [], 0
    # 오래된 것 한 덩어리
    if edge > 0:
        labels.append((f"~{int(g.grn.iloc[edge - 1])} (이전 {edge}건)", 0, edge))
        lo = edge
    while lo < len(g):
        hi = min(lo + bucket_size, len(g))
        labels.append((f"{int(g.grn.iloc[lo])}–{int(g.grn.iloc[hi - 1])}", lo, hi))
        lo = hi

    rows = []
    for name, a, b in labels:
        sub = g.iloc[a:b]
        n = len(sub)
        pend = int((sub.cat == "Pending").sum())
        closed = n - pend
        ok = int((sub.cat == "no_questions").sum())
        rej = int(sub.cat.isin(("no_basis", "ceased")).sum())
        yr = sub.cd.dropna()
        rows.append({
            "묶음": name, "n": n, "성공": ok, "미종결": pend, "반려": rej,
            "제출_종결": round(closed / n * 100, 1) if n else np.nan,
            "종결_성공": round(ok / closed * 100, 1) if closed else np.nan,
            "누적_성공": round(ok / n * 100, 1) if n else np.nan,
            "종결시기": (f"{yr.min().date()}~{yr.max().date()}"
                     if len(yr) else "—"),
        })
    return pd.DataFrame(rows, columns=cols)


def vintage_verdict(vf: pd.DataFrame) -> pd.DataFrame:
    """묶음마다 "값이 낮은 이유"를 판정한다.

        관측 중단   제출→종결 이 성숙선 미만 — 아직 결정이 안 난 건이 많다.
                    낮은 누적 성공은 실패가 아니라 Pending 때문이다.
        성과 확인   성숙했는데(제출→종결 높음) 종결→성공이 성숙 묶음
                    중앙값보다 5%p 넘게 낮다 — 시간 문제가 아니다.
        정상        위 둘 다 아님.

    반환: DataFrame[묶음, 판정, 근거]
    """
    cols = ["묶음", "판정", "근거"]
    if vf.empty:
        return pd.DataFrame(columns=cols)

    mature = vf[vf.제출_종결 >= _MATURE_CLOSED]
    base = float(mature.종결_성공.median()) if len(mature) else np.nan

    out = []
    for _, r in vf.iterrows():
        if pd.notna(r.제출_종결) and r.제출_종결 < _MATURE_CLOSED:
            out.append((r.묶음, "관측 중단",
                        f"제출→종결 {r.제출_종결:.0f}% · 미종결 {r.미종결}건 "
                        f"(반려 {r.반려}건). 아직 갈 시간이 부족하다."))
        elif (pd.notna(base) and pd.notna(r.종결_성공)
              and r.종결_성공 < base - 5):
            out.append((r.묶음, "성과 확인 필요",
                        f"성숙(제출→종결 {r.제출_종결:.0f}%)했는데 종결→성공 "
                        f"{r.종결_성공:.0f}% — 성숙 묶음 중앙값 {base:.0f}%보다 낮다."))
        else:
            out.append((r.묶음, "정상", ""))
    return pd.DataFrame(out, columns=cols)


# ── KPI ───────────────────────────────────────────────────────────
#
# 지표 넷 (내가 정한 것). 그레인은 GRN 1건, 분모 "접수"는 전체 GRN.
# 시계열(monthly)은 **종결일 기준 연도별** — 접수일은 2016년까지 사실상 완전하고
# 2017~2019 는 5건뿐이라(2017:2 · 2018:1 · 2019:2) 그 뒤로는 감시가 안 된다.
# 월로 자르면 314개월 전부 표본 부족(월평균 4건)이라 굵게 묶는다.
#
#   신규 과제 수     GRASNotices 행 수                     (연도별 = 종결연도 건수)
#   최종 승인율      no_questions ÷ 접수                    THRESHOLDS 로 색 판정
#   평균 처리 일수    median(종결일 - 접수일)  ⚠ N=676     (아래 lead_days 주 참조)
#   반려율          (no_basis + ceased) ÷ 접수
#
# ⚠ 평균 처리 일수 · 반려율은 **높을수록 나쁜** 지표다. THRESHOLDS 엔트리에
#   "높을수록_나쁨": True 를 넣어야 status_of() 색이 뒤집히지 않는다.

_APPROVE = "no_questions"
# ⚠ 반려는 "무사 종결도 미종결도 아닌 것" 과 **같지 않다.** cat 에는 MIXED 가 1건 있고
#   그 건은 no_questions 도 Pending 도 no_basis/ceased 도 아니라 어느 분자에도 안 들어간다.
#   그래서 갈래 합계가 전체와 1건 어긋난다 — 검산할 때 이 1건을 찾느라 헤매지 않도록 적어 둔다.
#       승인 1,056 + 반려 244 + Pending 35 = 1,335   /   전체 1,336   (차 1 = MIXED)
_REJECT = ("no_basis", "ceased")


def _grn_frame(t: dict) -> pd.DataFrame:
    """GRN 1건 = 1행. kpis() 와 monthly() 가 같은 규칙을 쓰도록 여기서 한 번 만든다."""
    g = t["GRASNotices"]
    d = pd.DataFrame({
        "grn": g["grn"],
        "cat": g["cat"].astype(str),
        "closed": pd.to_datetime(g.get("closure_date"), errors="coerce"),
        "filed": pd.to_datetime(g.get("filing_date"), errors="coerce"),
    })
    d["approved"] = d.cat == _APPROVE
    d["rejected"] = d.cat.isin(_REJECT)
    d["lead_days"] = (d.closed - d.filed).dt.days   # 둘 다 있을 때만 값
    # ⚠ GRN 813·824 는 접수일 == 종결일 (lead 0). 0일 심사는 없다 —
    #   접수일이 종결일로 백필된 데이터 아티팩트로 보고 처리일수에서 뺀다.
    #   (전 구간에서 lead <= 0 인 건은 이 둘뿐)
    #
    #   ★ 그래서 이 지표의 표본은 **676** 이지 678 이 아니다.
    #     접수일이 있는 GRN 678건 - 위 2건 = 676.  다시 세어볼 사람을 위해:
    #         빼기 전  N=678 · 평균 195.0일 · 중앙 176일 · P90 290일
    #         코드 값  N=676 · 평균 195.6일 · 중앙 176일 · P90 290일   <- kpis() 가 내는 값
    #     중앙값은 같아서 카드 숫자는 안 흔들리지만 평균·N 은 다르다.
    d.loc[d.lead_days <= 0, "lead_days"] = pd.NA
    d["lead_days"] = pd.to_numeric(d["lead_days"], errors="coerce")
    d["year"] = d.closed.dt.year
    return d


def _chain_frame(t: dict) -> pd.DataFrame:
    """체인 1건 = 1행. 체인은 같은 물질의 재제출 묶음이다
    (Resubmission 링크를 union-find 로 묶어 둔 GRASNotices.chain 컬럼).

    그레인이 GRN 이 아니라 **체인**인 지표는 전부 이 표를 본다.
    정의서: mydomain/notes/03_지표정의.md

    반환: index=chain, 컬럼 [n, pending, approved]
        n         그 체인에 든 GRN 수 (2 이상이면 재제출이 있었다는 뜻)
        pending   아직 심사 중인 멤버가 있는가 — 있으면 그 체인은 결론이 안 났다
        approved  no_questions 멤버가 하나라도 있는가
    """
    return t["GRASNotices"].groupby("chain")["cat"].agg(
        n="size",
        pending=lambda s: (s == "Pending").any(),
        approved=lambda s: (s == _APPROVE).any())


@st.cache_data(show_spinner=False)
def kpis(t: dict) -> dict:
    """지표 카드. 분모 "접수" = 전체 GRN(Pending 포함).

    맨 앞이 **주지표(최종 성공률)** 다 — 명세 3행. "이 물질이 결국 등록되는가"를
    묻는 것이라 그레인이 GRN 이 아니라 **체인(재제출 묶음)** 이다. 나머지 넷은
    GRN 그레인이고, 마지막 재제출 필요 비율은 가드레일 ② 다.

    ⚠ 최종 성공률(체인)과 최종 승인율(GRN)은 **다른 지표다.** 분모가 다르다 —
      전자는 결론이 난 체인, 후자는 전체 접수. 섞어 인용하면 안 된다.
    ⚠ 새로 넣은 둘은 config.THRESHOLDS 에 임계값이 없다. 정의서가 "사용자가 정할 것"
      으로 남겨둔 칸이라 지어내지 않았다 — 화면에는 "임계값 없음"으로 나온다.

    반환: {"지표이름": {"value": float, "n": int, "unit": str, "fmt": str}}
        n — 그 지표를 낸 표본 수. 승인율·반려율은 분모(접수), 처리 일수는
            접수일·종결일이 둘 다 있는 건 수, 체인 지표는 체인 수.
            "표본 확인 → 계산 → 임계값 판정" 순서에서 첫 단계가 이 값을 본다.
    """
    d = _grn_frame(t)
    n_intake = len(d)                       # 접수 = 전체 GRN
    lead = d.lead_days.dropna()             # 종결일·접수일 둘 다 있는 건만

    ch = _chain_frame(t)
    resolved = ch[~ch.pending]              # 결론이 난 체인만 (미결 섞이면 값이 아니다)

    return {
        "최종 성공률": {
            "value": (resolved.approved.mean() * 100 if len(resolved)
                      else float("nan")),
            "n": int(len(resolved)),
            "unit": "%", "fmt": "{:.1f}%"},
        "신규 과제 수": {
            "value": float(n_intake), "n": n_intake,
            "unit": "건", "fmt": "{:,.0f}건"},
        "최종 승인율": {
            "value": d.approved.sum() / n_intake * 100, "n": n_intake,
            "unit": "%", "fmt": "{:.1f}%"},
        "평균 처리 일수": {
            "value": float(lead.median()) if len(lead) else float("nan"),
            "n": int(len(lead)),
            "unit": "일", "fmt": "{:,.0f}일"},
        "반려율": {
            "value": d.rejected.sum() / n_intake * 100, "n": n_intake,
            "unit": "%", "fmt": "{:.1f}%"},
        # 가드레일 ② — 주지표를 올리려 할 때 희생될 수 있는 것.
        # 분모는 결론 여부와 무관한 **전체 체인**이다 (재제출은 심사 중에도 일어난다).
        "재제출 필요 비율": {
            "value": (ch.n >= 2).mean() * 100 if len(ch) else float("nan"),
            "n": int(len(ch)),
            "unit": "%", "fmt": "{:.1f}%"},
    }


@st.cache_data(show_spinner=False)
def monthly(t: dict) -> pd.DataFrame:
    """추이 — **종결연도별** (함수 이름은 monthly 지만 월이 아니라 연이다).

    월로 자르면 모든 점이 표본 부족이라 굵게 묶었다. → kpis() 위 주석.
    열 이름은 kpis() 의 지표 이름과 같다 — 그래야 스파크라인이 그려진다.

    반환: 인덱스가 연도 문자열("1998" ...), 열이 지표인 DataFrame.
          평균 처리 일수는 접수일이 있는 해(~2019)까지만 값이 있고 이후는 NaN.
    """
    d = _grn_frame(t)
    d = d[d.year.notna()].copy()
    d["year"] = d.year.astype(int)
    grp = d.groupby("year")

    out = pd.DataFrame({
        "신규 과제 수": grp.size(),
        "최종 승인율": grp.approved.mean() * 100,
        "평균 처리 일수": grp.lead_days.median(),
        "반려율": grp.rejected.mean() * 100,
    })
    out.index = out.index.astype(str)
    return out


def status_of(name: str, value: float) -> str:
    """지표 값을 상태 색으로 판정한다. 임계값은 config.THRESHOLDS 에 있다.

    이 함수는 **그대로 쓴다.** 판정 규칙이지 도메인이 아니다.
    THRESHOLDS 가 비어 있으면 전부 "ok"로 나온다 — 채우면 색이 갈린다.
    방향은 그 엔트리의 "높을수록_나쁨" 플래그가 정한다 (없으면 낮을수록 나쁨).
    """
    th = C.THRESHOLDS.get(name)
    if not th:
        return "ok"
    if th.get("높을수록_나쁨"):
        return ("block" if value > th["위험"]
                else "warn" if value > th["경고"] else "ok")
    return ("block" if value < th["위험"]
            else "warn" if value < th["경고"] else "ok")


# ── 실험 ──────────────────────────────────────────────────────────
# ★ 실험별로 어느 구간을 보는지. 도메인이 바뀌면 이 표를 갈아끼운다.
#   실험이 없는 도메인이면 비워 둔다.
EXP_STEPS: dict[str, tuple[str, str]] = {
    "EXP-001": ("랜딩방문", "요금제조회"),
    "EXP-002": ("요금제조회", "신청시작"),
    "EXP-003": ("신청시작", "신청완료"),
    "EXP-004": ("요금제조회", "신청시작"),
    "EXP-005": ("요금제조회", "신청시작"),
}


def _two_prop(sc, nc, stt, nt):
    """두 비율 비교. 차이·신뢰구간·p값을 함께 돌려준다.

    **그대로 쓴다.** 통계 계산은 도메인이 바뀌어도 같다.

    p값만 보면 '유의하지만 실질 효과가 없는' 경우를 놓친다.
    그래서 신뢰구간을 항상 함께 계산해 화면에 그린다.
    """
    rc, rt = sc / nc, stt / nt
    se = np.sqrt(rc * (1 - rc) / nc + rt * (1 - rt) / nt)
    if se == 0:
        return dict(rc=rc, rt=rt, nc=nc, nt=nt, diff=0, lo=0, hi=0, p=1.0, lift=0)
    z = (rt - rc) / se
    return dict(rc=rc, rt=rt, nc=nc, nt=nt, diff=rt - rc,
                lo=(rt - rc) - 1.96 * se, hi=(rt - rc) + 1.96 * se,
                p=2 * (1 - stats.norm.cdf(abs(z))),
                lift=(rt / rc - 1) if rc else 0)


def srm_check(asg: pd.DataFrame, exp_id: str) -> dict:
    """SRM(Sample Ratio Mismatch). 배정이 50:50인지 검정한다.

    **그대로 쓴다.** 7주차에 손으로 해본 그 계산이다.

    배정이 50:50이 아니면 배정 로직에 버그가 있다는 뜻이고,
    그 경우 어떤 효과가 나오든 해석할 수 없다.
    """
    a = asg[asg.experiment_id == exp_id]
    c = int((a.variant == "control").sum())
    t = int((a.variant == "treatment").sum())
    if c + t == 0:
        return {"ok": False, "c": 0, "t": 0, "p": 1.0, "ratio": (0.0, 0.0)}
    p = stats.chisquare([c, t]).pvalue
    return {"ok": p >= 0.001, "c": c, "t": t, "p": float(p),
            "ratio": (c / (c + t), t / (c + t))}


def trust_check(n: int, *, pending: int = 0, category: str = "",
                unfair: str = "") -> str | None:
    """이 칸(분해 칸 하나 · 비교 카드 하나)을 믿을 수 있는가. **계산 결과를
    화면에 올리기 전에** 묻는다.

    ★ Day3 실습 B. ← 오늘의 핵심

    ────────────────────────────────────────────────────────────
    오늘의 어려운 일은 계산이 아니다.
    **계산은 이미 할 수 있는데, 화면에 안 그리는 코드를 쓰는 것**이다.
    ────────────────────────────────────────────────────────────

    이 도메인엔 A/B 실험이 없다. 그래서 SRM(배정) 대신 아래 셋을 본다.
    **조건은 셋인데 분기는 하나** — 걸리는 즉시 사유를 돌려주고 끝낸다.

        1. 표본이 모자란다   n < config.MIN_CELL
                            → 계산해도 못 믿는다. 내 데이터는 대개 여기 걸린다
        2. 기간이 안 찼다    pending / (n + pending) > config.MAX_PENDING_RATIO
                            → 아직 심사 중인 건이 섞여 값이 아니라 진행 상황이다
        3. 비교가 공정하지 않다
                            category 가 잔여 범주("(미매칭)"·"미상") — 무엇과
                            비교하는지 모른다 / 또는 호출자가 unfair 사유를 준다
                            (관측 기간이 다른 대상 누적 비교 · 제도 변경 경계 전후 등)

    하나라도 걸리면 **사유 문자열**(실제 숫자 포함)을 돌려준다. 부르는 쪽은
    거기서 멈추고 그 칸의 전환율·비중을 **화면에 그리지 않는다.** 다 통과하면
    None 을 돌려준다.

    "그래도 회색으로라도 보여주면 안 되나요?"

        안 됩니다. **사람은 본 숫자를 기억합니다.**
        옆에 아무리 경고를 붙여도 회의실에서 인용되는 것은 숫자입니다.

    인자
        n         이 칸의 '도달' 수 (구간 시작 단계 도달 고유 수 = 표본)
        pending   그 칸에서 제출은 됐으나 아직 종결 안 된 수. 종결 이후 구간이면 0
        category  이 칸의 분류 값. 잔여 범주면 3번에 걸린다
        unfair    비교가 공정하지 않은 이유(호출자가 안다). 비면 무시

    반환: 못 믿을 이유(str) 또는 None
    """
    if n < C.MIN_CELL:
        return f"표본 {n:,}건 (최소 {C.MIN_CELL:,}건)"

    submitted = n + max(pending, 0)
    if pending > 0 and pending / submitted > C.MAX_PENDING_RATIO:
        return (f"미결 {pending:,}건 / 제출 {submitted:,}건 "
                f"({pending / submitted * 100:.0f}%) — 아직 진행 중")

    if str(category).strip() in _RESIDUAL_LABELS:
        return f"'{category}' 는 정의된 분류가 아님 (잔여 범주 · n={n:,})"

    if unfair:
        return f"공정한 비교가 아님 — {unfair}"

    return None


@st.cache_data(show_spinner=False)
def experiment_results(t: dict) -> list[dict]:
    """실험 결과와 판정.

    **판정 순서가 이 함수의 전부다.** 믿을 수 있는지 먼저 묻고,
    믿을 수 있을 때만 계산한다.

    좋은 결과를 먼저 보면 경고를 무시하고 싶어진다. 그래서 사람의 규율에
    맡기지 않고 **코드로 순서를 박는다.**

    실험이 없는 도메인이면 이 함수는 빈 목록을 돌려준다. 대신 전후 비교
    카드를 만들되 **"인과 주장 불가"를 카드에 박아 둔다.** → DESIGN.md §4-4
    """
    if "experiments" not in t or "experiment_assignments" not in t:
        return []
    ex, asg, fe = t["experiments"], t["experiment_assignments"], t["funnel_events"]
    reach = {s: set(fe.loc[fe.funnel_step == s, "visitor_id"]) for s in C.FUNNEL_STEPS}
    out = []
    for _, e in ex.iterrows():
        eid = e.experiment_id
        srm = srm_check(asg, eid)
        n_total = int((asg.experiment_id == eid).sum())
        row = {
            "id": eid, "name": e.experiment_name, "hypothesis": e.hypothesis,
            "primary": e.primary_metric, "guardrail": e.guardrail_metric,
            "start": e.start_date, "end": e.end_date, "srm": srm,
        }

        # ★ 판정이 계산보다 먼저다. 못 믿으면 여기서 끝난다.
        #   이 도메인엔 실험이 없어 아래는 실행되지 않는다. 실험 데이터가 생기면
        #   배정(SRM)·표본을 여기서 막는다 — trust_check() 는 분해/비교 칸 전용으로 옮겼다.
        reason = None
        if not srm["ok"]:
            reason = (f"배정이 깨졌습니다 — "
                      f"{srm['ratio'][0] * 100:.1f}:{srm['ratio'][1] * 100:.1f} "
                      f"(p={srm['p']:.4f})")
        elif n_total < C.MIN_SAMPLE:
            reason = f"표본 {n_total}건 (최소 {C.MIN_SAMPLE}건)"
        if reason:
            row["verdict"] = "무효"
            row["color"] = "block"
            row["reason"] = reason
            out.append(row)
            continue        # 지표를 계산하지 않는다. 숨기는 것이 아니다.

        # ── 여기부터 계산 ─────────────────────────────────────────
        if eid not in EXP_STEPS:
            row.update(verdict="데이터 없음", color="none",
                       reason="EXP_STEPS 에 이 실험의 구간이 없습니다.")
            out.append(row)
            continue
        sf, stp = EXP_STEPS[eid]
        a = asg[asg.experiment_id == eid][["visitor_id", "variant", "assigned_at"]]
        a = a[a.visitor_id.isin(reach[sf])]
        a = a.assign(conv=a.visitor_id.isin(reach[stp]).astype(int))
        g = a.groupby("variant", observed=True).conv.agg(["sum", "count"])
        if len(g) < 2:
            row.update(verdict="데이터 없음", color="none")
            out.append(row)
            continue
        r = _two_prop(g.loc["control", "sum"], g.loc["control", "count"],
                      g.loc["treatment", "sum"], g.loc["treatment", "count"])
        row.update(r, step_from=sf, step_to=stp, assignments=a)

        # 가드레일 — 주지표를 올리려 할 때 희생될 수 있는 것
        # ★ 아래는 통신사 컬럼(is_churned)이다. 내 가드레일 지표로 바꾼다.
        row["guard"] = None
        if "유지율" in str(e.guardrail_metric) and "customers" in t:
            cu = t["customers"]
            m = cu.merge(a[["visitor_id", "variant"]], on="visitor_id", how="inner")
            if len(m) and m.variant.nunique() == 2:
                ret = m.groupby("variant", observed=True).is_churned.mean()
                row["guard"] = {
                    "name": e.guardrail_metric,
                    "control": float(1 - ret["control"]),
                    "treatment": float(1 - ret["treatment"]),
                    "delta": float((1 - ret["treatment"]) - (1 - ret["control"])),
                }

        # 판정 — ★ 3%p 는 예시다. 내 가드레일 기준으로 바꾼다.
        sig = r["p"] < 0.05
        guard_bad = row["guard"] is not None and row["guard"]["delta"] < -0.03
        if guard_bad:
            # 주지표가 좋아져도 가드레일이 무너지면 성공이 아니다
            row.update(verdict="주의 필요", color="warn",
                       reason="주지표는 개선됐으나 가드레일이 악화됐습니다.")
        elif sig and r["lift"] > 0:
            row.update(verdict="성공", color="ok", reason="")
        elif sig:
            row.update(verdict="악화", color="block", reason="")
        else:
            row.update(verdict="효과 없음", color="none",
                       reason="통계적으로 유의한 차이가 없습니다.")
        out.append(row)
    return out


def peeking_curve(res: dict, start: str, cuts=(7, 14, 30, 60, 92)) -> pd.DataFrame:
    """관측 시점별 누적 결과. '그때 멈췄다면 무엇을 봤을까'를 재현한다.

    **그대로 쓴다.** 7주차에 겪은 조기 중단이다.
    """
    a = res.get("assignments")
    if a is None:
        return pd.DataFrame()
    a = a.copy()
    a["d"] = (to_dt(a.assigned_at) - pd.Timestamp(start)).dt.days
    rows = []
    for c in cuts:
        s = a[a.d <= c].groupby("variant", observed=True).conv.agg(["sum", "count"])
        if len(s) < 2 or s["count"].min() < 30:
            continue
        r = _two_prop(s.loc["control", "sum"], s.loc["control", "count"],
                      s.loc["treatment", "sum"], s.loc["treatment", "count"])
        rows.append({"cut": c, "lift": r["lift"], "p": r["p"], "sig": r["p"] < 0.05})
    return pd.DataFrame(rows)


def weekly_effect(res: dict, start: str, bucket_days: int = 14) -> pd.DataFrame:
    """기간을 쪼개 효과 추이를 본다. 신규성 효과는 전체 평균에 가려진다.

    **그대로 쓴다.** 7주차에 겪은 그것이다.
    """
    a = res.get("assignments")
    if a is None:
        return pd.DataFrame()
    a = a.copy()
    a["b"] = (to_dt(a.assigned_at) - pd.Timestamp(start)).dt.days // bucket_days
    g = (a[a.b >= 0].groupby(["b", "variant"], observed=True).conv
         .mean().unstack().dropna())
    if g.empty:
        return pd.DataFrame()
    g["lift"] = g.treatment / g.control - 1
    g = g.reset_index()
    g["label"] = g.b.apply(lambda i: f"{int(i)*2+1}~{int(i)*2+2}주")
    return g


# ── 제안서 주제 후보 ──────────────────────────────────────────────
#
# ★ Day3(9주차) 실습 A. **하나만 고르지 않는다.**
#   발견 하나로 제안서 하나를 만들면 그날 눈에 띈 것이 그대로 이번 분기의
#   우선순위가 되어 버린다. 뽑을 수 있는 만큼 뽑아 놓고 **사람이 고른다.**
#
# 기각과 "못 믿을 것"은 다르다 — 섞으면 안 된다.
#     기각      비교했는데 차이가 작다   -> 목록에 남긴다. 기각사유를 채운다
#     못 믿을 것 비교 자체가 안 된다     -> 애초에 후보로 만들지 않는다
#
# 지우면 "안 봤다"와 "보고 아니었다"가 구분되지 않는다.

#: 규모 환산의 분모로 쓸 **최근 완결연도 수.** 지금 운영 규모에 가깝게 잰다.
#: PERIOD 전체(28.1년) 평균은 연 47.5건인데, 초기 몇 해가 연 20건대라 현재를 대표하지 못한다.
RECENT_YEARS = 10


def _per_year(t: dict) -> tuple[float, str]:
    """연간 건수와 그 근거 한 줄.

    ⚠ **완결된 해만 센다.** PERIOD 마지막 해는 반쪽이라(종결일 최댓값이 연중이다)
      평균에 넣으면 값을 끌어내린다 — "완결된 기간만 비교한다"를 분모에도 적용한다.
    ⚠ 현재 시각을 쓰지 않는다. 기간은 config.PERIOD 에서만 온다 (재현).
    """
    last_full = pd.Timestamp(C.PERIOD[1]).year - 1
    first = last_full - RECENT_YEARS + 1
    m = monthly(t)
    idx = [i for i in m.index if first <= int(i) <= last_full]
    if not idx:                                    # 연도가 모자라면 전체 평균으로
        a, b = pd.Timestamp(C.PERIOD[0]), pd.Timestamp(C.PERIOD[1])
        yrs = (b - a).days / 365.25
        n = int(t["GRASNotices"]["grn"].nunique())
        return n / yrs, f"PERIOD 전체 {yrs:.1f}년 평균"
    v = float(m.loc[idx, "신규 과제 수"].mean())
    return v, (f"최근 {len(idx)} 완결연도({idx[0]}~{idx[-1]}) 평균 · "
               f"{pd.Timestamp(C.PERIOD[1]).year}년은 반쪽이라 뺐다")


def _per_year_plain(t: dict) -> str:
    """연간 건수의 근거를 **읽는 사람 말로.** 계산식·코드 용어를 쓰지 않는다.

    결재 문서에 계산 과정을 넣지 않는다 (Day3 판단 기준 1). 다만 **가정은 남긴다** —
    환산에 가정이 안 붙으면 예측을 실측처럼 쓰는 것이다.
    """
    v, _ = _per_year(t)
    last_full = pd.Timestamp(C.PERIOD[1]).year - 1
    first = last_full - RECENT_YEARS + 1
    return (f"최근 {RECENT_YEARS}년({first}~{last_full}) 평균인 연 {v:.1f}건이 "
            f"이어진다고 보았습니다. {pd.Timestamp(C.PERIOD[1]).year}년은 "
            f"아직 반년치라 평균에서 뺐습니다.")


def _gap_pp(hi: float, lo: float) -> float:
    """두 비율의 격차(%p). **표시값끼리 뺀다.**

    원본 비율끼리 빼고 나중에 반올림하면 문서에 적힌 두 값의 차와 어긋난다 —
    91.25 와 77.56 이 적혀 있는데 격차가 13.70 이면 읽는 사람이 계산을 의심한다.
    소수 둘째 자리까지 맞춘다. (2026-09-10 결정)
    """
    return round(round(hi * 100, 2) - round(lo * 100, 2), 2)


def _real_funnel(t: dict) -> list[dict]:
    """실측 퍼널을 **스냅샷에서 직접** 센다.

    funnel() 에는 실측을 못 먹인다(이벤트 로그를 요구, 어댑터 미정). 다만 세 단계가
    전부 GRN 1행짜리 속성이라 값 자체는 여기서 세어진다. → CLAUDE.md 퍼널 절
    """
    g = t["GRASNotices"]
    cat = g["cat"].astype(str)
    n_sub = int(g["grn"].nunique())
    n_close = int(g.loc[cat != "Pending", "grn"].nunique())
    n_ok = int(g.loc[cat == _APPROVE, "grn"].nunique())
    return [
        {"step": C.FUNNEL_STEPS[0], "n": n_sub, "rate": None},
        {"step": C.FUNNEL_STEPS[1], "n": n_close, "rate": n_close / n_sub},
        {"step": C.FUNNEL_STEPS[2], "n": n_ok, "rate": n_ok / n_close},
    ]


def _real_dim_cells(t: dict, real_col: str) -> list[dict]:
    """실측 축 한 개를 종결 -> 결과 구간에서 쪼갠다. **trust_check 를 그대로 적용한다.**

    못 믿을 칸은 값을 만들지 않는다 — 후보로도 만들지 않는다.
    """
    g = t["GRASNotices"]
    cat = g["cat"].astype(str)
    closed = g[cat != "Pending"]
    total = len(closed)
    out = []
    for val, sub in closed.groupby(closed[real_col].astype(str), sort=False):
        n = len(sub)
        conv = int((sub["cat"].astype(str) == _APPROVE).sum())
        reason = trust_check(n, pending=0, category=str(val))
        out.append({"칸": str(val), "도달": n, "전환": conv,
                    "전환율": None if reason else conv / n,
                    "비중": None if reason else n / total,
                    "사유": reason})
    return out


@st.cache_data(show_spinner=False)
def proposal_topics(t: dict) -> list[dict]:
    """제안서로 쓸 만한 주제 후보를 **가능한 만큼** 뽑는다.

    ★ Day3 실습 A 프롬프트 1.

    후보가 나오는 곳 넷 — 이 도메인의 사정을 반영했다:

        ① 퍼널 구간   단계가 셋이라 **구간이 둘뿐**이다. 비교가 한 쌍만 나온다
        ② 분해 축     config.FUNNEL_DIMS. ⚠ 키는 합성 컬럼, 실측 컬럼은 "real" 값
        ③ 임계값      config.THRESHOLDS 를 벗어난 지표. **지금은 0개다 — 0개도 결과다**
        ④ 추세       monthly() 는 **연도별**이다. 완결된 두 해만 비교한다

    규모 = 격차 x 비중 x 연간 건수.  갈래마다 격차·비중이 무엇인지는 아래 각 절에.
    **금액으로 환산하지 않는다** — 이 데이터에 금액 컬럼이 없다. 건수로만.

    반환: 후보 리스트. 규모 큰 순, 기각된 것은 맨 뒤.
        {"키", "갈래", "제목", "한줄", "규모_연간건수", "격차_%p", "비중",
         "근거축", "구간", "기각사유", "가정"}

    ⚠ 후보가 5개 미만으로 나와도 억지로 늘리지 않는다. 축이 둘, 구간이 둘인 도메인이다.
    """
    per_year, per_year_why = _per_year(t)
    n_total = int(t["GRASNotices"]["grn"].nunique())
    plain = _per_year_plain(t)          # 문서에 그대로 나갈 문장 (코드 용어 없음)
    base = ["규모 = 격차 x 비중 x 연간 건수",
            f"연간 건수 = 연 {per_year:.1f}건 ({per_year_why})",
            f"⚠ PERIOD 전체 {n_total:,}건 평균은 연 47.5건이다. 초기 몇 해가 얇아 "
            f"현재를 대표하지 못해 최근 {RECENT_YEARS}년을 썼다",
            "금액 컬럼이 없어 건수로만 낸다"]
    out: list[dict] = []

    # ── ① 퍼널 구간 ───────────────────────────────────────────────
    #   격차 = 가장 낮은 구간과 그다음으로 낮은 구간의 전환율 차
    #   비중 = 그 구간 시작 단계에 도달한 비율 (전체 제출 대비)
    f = _real_funnel(t)
    segs = [(f[i - 1], f[i]) for i in range(1, len(f)) if f[i]["rate"] is not None]
    segs.sort(key=lambda s: s[1]["rate"])
    if len(segs) >= 2:
        (lo_a, lo_b), (nx_a, nx_b) = segs[0], segs[1]
        gap = _gap_pp(nx_b["rate"], lo_b["rate"])
        share = lo_a["n"] / f[0]["n"]
        out.append({
            "키": "seg_" + lo_a["step"] + "_" + lo_b["step"],
            "갈래": "① 퍼널 구간",
            "제목": lo_a["step"] + " -> " + lo_b["step"] + " 구간을 점검한다",
            "한줄": (lo_a["step"] + " 도달 " + format(lo_a["n"], ",") + "건 중 "
                   + lo_b["step"] + " 로 넘어가는 것은 " + format(lo_b["n"], ",")
                   + "건, " + f"{lo_b['rate'] * 100:.2f}%" + " 다. 구간 둘 중 낮은 쪽이고, "
                   + nx_a["step"] + " -> " + nx_b["step"] + " 는 "
                   + f"{nx_b['rate'] * 100:.2f}%" + " 로 " + f"{gap:.2f}%p" + " 높다."),
            "규모_연간건수": round(gap / 100 * share * per_year, 1),
            "격차_%p": round(gap, 2), "비중": round(share, 4),
            "근거축": None, "구간": (lo_a["step"], lo_b["step"]),
            "기각사유": None,
            "가정_문서용": plain,
            "가정": base + [
                "격차 = 낮은 구간과 그다음 구간의 전환율 차",
                "비중 = " + lo_a["step"] + " 도달 / 전체 제출",
                "⚠ 단계가 셋이라 구간이 둘뿐이다. 비교가 한 쌍만 나온다"],
        })

    # ── ② 분해 축 ─────────────────────────────────────────────────
    #   격차 = 최고 칸과 최저 칸의 전환율 차
    #   비중 = **낮은 쪽 칸**의 비중 (손을 쓸 수 있는 쪽이 전체의 얼마인가)
    #   ⚠ 키는 합성 컬럼 이름, 실측 컬럼은 "real" 값이다. 이름이 다르다.
    seg_from, seg_to = C.FUNNEL_STEPS[1], C.FUNNEL_STEPS[2]
    for key, spec in C.FUNNEL_DIMS.items():
        cells = _real_dim_cells(t, spec["real"])
        shown = [c for c in cells if c["사유"] is None]
        hidden = [c for c in cells if c["사유"] is not None]
        if len(shown) < 2:
            # 비교 자체가 안 된다 — **기각이 아니라 후보를 안 만든다**
            continue
        hi = max(shown, key=lambda c: c["전환율"])
        lo = min(shown, key=lambda c: c["전환율"])
        gap = _gap_pp(hi["전환율"], lo["전환율"])
        rejected = gap < C.MIN_GAP * 100
        out.append({
            "키": "dim_" + key,
            "갈래": "② 분해 축",
            "제목": spec["label"] + " 로 갈리는지 본다",
            "한줄": (seg_to + " 도달률이 " + lo["칸"] + " " + f"{lo['전환율'] * 100:.2f}%"
                   + " (" + format(lo["전환"], ",") + "/" + format(lo["도달"], ",") + "), "
                   + hi["칸"] + " " + f"{hi['전환율'] * 100:.2f}%"
                   + " (" + format(hi["전환"], ",") + "/" + format(hi["도달"], ",")
                   + ") 로 " + f"{gap:.2f}%p" + " 벌어진다. 낮은 쪽이 "
                   + seg_from + " 도달의 " + f"{lo['비중'] * 100:.2f}%" + " 다."),
            "규모_연간건수": round(gap / 100 * lo["비중"] * per_year, 1),
            "격차_%p": round(gap, 2), "비중": round(lo["비중"], 4),
            "근거축": key, "구간": (seg_from, seg_to),
            # ⚠ **코드 상수 이름을 사유에 넣지 않는다.** 문서로 그대로 실려 나가
            #   읽는 사람이 뜻을 모르는 말이 된다. 수치만 남긴다. (2026-09-10)
            "기각사유": (f"격차 {gap:.2f}%p 로 "
                     f"{C.words('판정어', '격차기준')} {C.MIN_GAP * 100:.0f}%p 에 미달"
                     if rejected else None),
            "가정_문서용": plain,
            "가정": base + [
                "격차 = 최고 칸과 최저 칸의 전환율 차",
                "비중 = 낮은 쪽 칸(" + lo["칸"] + ") 의 " + seg_from + " 도달 비중",
                "실측 컬럼 " + spec["real"] + " (화면의 합성 컬럼 " + key + " 와 이름이 다르다)",
            ] + (["못 믿을 칸 " + str(len(hidden)) + "개는 비교에서 뺐다: "
                  + " / ".join(c["칸"] + " " + c["사유"] for c in hidden)] if hidden else []),
        })

    # ── ③ 임계값 ──────────────────────────────────────────────────
    #   ⚠ config.THRESHOLDS 에 **있는 지표만** 본다. 임계값이 없는 지표의 ok 는
    #     "괜찮다"가 아니라 "임계값 미정"이라 후보로 세지 않는다.
    k = kpis(t)
    for name, th in C.THRESHOLDS.items():
        if name not in k:
            continue
        val = k[name]["value"]
        st_ = status_of(name, val)
        if st_ == "ok":
            continue                       # 벗어나지 않았다 — 후보가 아니다
        line = th["위험"] if st_ == "block" else th["경고"]
        gap = abs(val - line)
        out.append({
            "키": "th_" + name,
            "갈래": "③ 임계값",
            "제목": name + " 가 정해둔 선을 벗어났다",
            "한줄": (name + " 가 " + f"{val:.2f}" + k[name]["unit"] + " 로 "
                   + ("위험선" if st_ == "block" else "경고선") + " "
                   + f"{line:g}" + " 를 " + f"{gap:.2f}" + " 만큼 벗어났다 (표본 "
                   + format(k[name]["n"], ",") + ")."),
            "규모_연간건수": round(gap / 100 * per_year, 1),
            "격차_%p": round(gap, 2), "비중": 1.0,
            "근거축": None, "구간": None, "기각사유": None,
            "가정_문서용": plain,
            "가정": base + ["격차 = 현재값과 벗어난 선의 차", "비중 = 1 (전체 지표)"],
        })

    # ── ④ 추세 ────────────────────────────────────────────────────
    #   monthly() 는 이름과 달리 **종결연도별**이다. 월로 자르면 표본이 없다.
    #   완결된 두 해만 비교한다 — 마지막 해는 반쪽이라 뺀다.
    m = monthly(t)
    last_full = str(pd.Timestamp(C.PERIOD[1]).year - 1)     # 반쪽 해를 뺀 마지막 완결 해
    yrs_idx = [i for i in m.index if i <= last_full]
    if len(yrs_idx) >= 2:
        cur_y, prev_y = yrs_idx[-1], yrs_idx[-2]
        for name in C.THRESHOLDS:
            if name not in m.columns:
                continue
            cur, prev = m.loc[cur_y, name], m.loc[prev_y, name]
            if pd.isna(cur) or pd.isna(prev):
                continue                   # 값이 없다 — 비교 자체가 안 된다
            worse_up = bool(C.THRESHOLDS[name].get("높을수록_나쁨"))
            delta = cur - prev
            got_worse = (delta > 0) if worse_up else (delta < 0)
            gap = abs(delta)
            out.append({
                "키": "trend_" + name,
                "갈래": "④ 추세",
                "제목": name + " 의 연도별 움직임을 본다",
                "한줄": (name + " 가 " + prev_y + "년 " + f"{prev:.2f}" + " 에서 "
                       + cur_y + "년 " + f"{cur:.2f}" + " 로 " + f"{delta:+.2f}"
                       + " 움직였다 (종결연도 기준, 연 단위)."),
                # ⚠ 나빠지지 않았으면 **규모를 재지 않는다.** 0 으로 두면 "작다"로
                #   읽히는데, 실제로는 "얼마짜리 문제인가"라는 질문이 성립하지 않는 것이다.
                "규모_연간건수": round(gap / 100 * per_year, 1) if got_worse else None,
                "격차_%p": round(gap, 2), "비중": 1.0,
                "근거축": None, "구간": None,
                "기각사유": (None if got_worse else
                          f"직전 해보다 나빠지지 않았다 ({delta:+.2f})"),
                "가정_문서용": plain,
                "가정": base + [
                    "월이 아니라 **연** 단위다. monthly() 가 종결연도별이라서다",
                    f"완결된 두 해만 비교했다 ({prev_y} vs {cur_y}). "
                    f"{pd.Timestamp(C.PERIOD[1]).year}년은 반쪽이라 뺐다",
                    "격차 = 두 해의 차", "비중 = 1 (전체 지표)"],
            })

    # 규모 큰 순, 기각된 것은 맨 뒤 — **순서를 대신 정해주는 것이 아니라 정렬만 한다**
    #   규모가 None 인 것(재지 않은 것)은 그 안에서도 맨 뒤로.
    out.sort(key=lambda c: (c["기각사유"] is not None,
                            c["규모_연간건수"] is None,
                            -(c["규모_연간건수"] or 0)))
    return out


# ── 주제 하나에 딸린 근거 ─────────────────────────────────────────
#
# ★ Day3(9주차) 실습 A 프롬프트 2.
#
# **이 함수는 조회만 한다. 문장을 만들지 않는다.** 문장은 report/proposal.py 가 만든다.
# 여기서 문장을 만들면 같은 사실이 두 곳에서 다르게 쓰이기 시작한다.
#
# ⚠ **실측과 환산을 같은 항목에 섞지 않는다.** 절마다 "출처" 를 달아 둔다 —
#   현황 · 원인 · 추세는 실측이고, 규모만 환산이다. 합치면 추정이 실측처럼 읽힌다.

#: 주제 갈래가 ①·② 일 때 추세로 보여줄 지표. 그 구간의 **결과**에 해당하는 것.
_TREND_DEFAULT = "최종 승인율"


def _trend_years(t: dict, name: str) -> tuple[list[dict] | None, str | None]:
    """지표 하나의 **연도별** 값. 없으면 (None, 사유).

    ⚠ monthly() 는 이름과 달리 종결연도별이다. "최근 12개월"은 이 도메인에 없다.
    ⚠ 마지막 해는 반쪽이다 — **빼지 않고 싣되 반쪽이라고 표시한다.** 비교에는 쓰지 않는다.
    """
    m = monthly(t)
    if name not in m.columns:
        return None, f"'{name}' 은 연도별 표에 없는 지표다"
    col = m[name].dropna()
    if col.empty:
        return None, f"'{name}' 은 연도별 값이 모두 비어 있다"

    half = str(pd.Timestamp(C.PERIOD[1]).year)
    rows = [{"연도": str(y), "값": round(float(v), 2),
             "반쪽": str(y) == half} for y, v in col.items()]
    note = None
    missing = [str(y) for y in m.index if pd.isna(m.loc[y, name])]
    if missing:
        note = (f"값이 없는 해 {len(missing)}개: {missing[0]}~{missing[-1]} "
                f"(접수일이 없어 계산되지 않는다)")
    return rows, note


@st.cache_data(show_spinner=False)
def topic_evidence(t: dict, topic: dict) -> dict:
    """주제 하나가 쓸 근거를 한 번에 모은다. **조회만 한다.**

    ★ Day3 실습 A 프롬프트 2.

    반환: {"주제", "현황", "원인", "규모", "추세"}
      현황  실측 퍼널 전체 (단계 · 도달 · 전환율 · 병목)
      원인  분해 축 표. **주제 갈래마다 다르다** — 아래 참조
      규모  연간 건수 + 가정. **topic 이 이미 가진 것을 그대로 싣는다**
      추세  관련 지표의 연도별 값

    없는 것은 지어내지 않고 None 으로 두되 **사유를 함께** 넣는다.
    None 만 있고 사유가 없으면 다음 사람이 버그인 줄 안다.

    원인 절이 갈래마다 다른 이유 — 이 도메인엔 축이 둘뿐이고, 주제 갈래에 따라
    축이 있기도 없기도 하다.

        ② 분해 축 주제    topic["근거축"] 그 축 하나
        ① 퍼널 구간 주제  근거축이 없다. 그 구간을 FUNNEL_DIMS 축 전부로 쪼갠다
        ③ 임계값 · ④ 추세  분해 축이 없다 -> None + 사유
    """
    갈래 = str(topic.get("갈래", ""))

    # ── 현황 — 실측 퍼널 (항상 셀 수 있다) ────────────────────────
    f = _real_funnel(t)
    rates = [(i, s["rate"]) for i, s in enumerate(f) if s["rate"] is not None]
    bi = min(rates, key=lambda x: x[1])[0] if rates else None
    현황 = {
        "출처": "실측",
        "단계": [{"단계": s["step"], "도달": s["n"],
                "전환율": None if s["rate"] is None else round(s["rate"] * 100, 2),
                "병목": (i == bi)} for i, s in enumerate(f)],
        "병목구간": (f[bi - 1]["step"], f[bi]["step"]) if bi else None,
        "사유": None,
    }

    # ── 원인 — 분해 축 표 (갈래마다 다르다) ───────────────────────
    seg_from, seg_to = C.FUNNEL_STEPS[1], C.FUNNEL_STEPS[2]
    if 갈래.startswith("②") and topic.get("근거축"):
        dims = [topic["근거축"]]
    elif 갈래.startswith("①"):
        dims = list(C.FUNNEL_DIMS)          # 축이 둘뿐이라 전부 준다
    else:
        dims = []

    if not dims:
        원인 = {"출처": "실측", "축": None,
              "사유": f"{갈래} 주제에는 분해 축이 없다 — "
                    f"지표 하나를 보는 갈래라 쪼갤 칸이 없다"}
    else:
        축들 = []
        for key in dims:
            spec = C.FUNNEL_DIMS[key]
            cells = _real_dim_cells(t, spec["real"])   # 실측 컬럼은 "real" 값
            shown = [c for c in cells if c["사유"] is None]
            hi = max(shown, key=lambda c: c["전환율"]) if shown else None
            lo = min(shown, key=lambda c: c["전환율"]) if shown else None
            축들.append({
                "축": key, "이름": spec["label"], "실측컬럼": spec["real"],
                "구간": (seg_from, seg_to),
                "칸": [{"칸": c["칸"], "도달": c["도달"], "전환": c["전환"],
                       "전환율": None if c["전환율"] is None else round(c["전환율"] * 100, 2),
                       "비중": None if c["비중"] is None else round(c["비중"] * 100, 2),
                       "최고": bool(hi and c["칸"] == hi["칸"]),
                       "최저": bool(lo and c["칸"] == lo["칸"]),
                       "사유": c["사유"]} for c in cells],
                "격차_%p": _gap_pp(hi["전환율"], lo["전환율"]) if (hi and lo) else None,
                "감춘칸": [c["칸"] + " " + c["사유"] for c in cells if c["사유"]],
            })
        원인 = {"출처": "실측", "축": 축들, "사유": None}

    # ── 규모 — **환산이다.** topic 이 이미 가진 것을 그대로 싣는다 ──
    #   여기서 다시 계산하면 두 곳에서 갈라진다.
    size = topic.get("규모_연간건수")
    규모 = {
        "출처": "환산",
        "연간건수": size,
        "격차_%p": topic.get("격차_%p"),
        "비중": topic.get("비중"),
        "가정": list(topic.get("가정") or []),
        # ⚠ 문서에 나가는 것은 이쪽이다. 위 "가정" 은 계산 근거라 코드 용어가 들어 있다.
        "가정_문서용": topic.get("가정_문서용"),
        "사유": (None if size is not None else
                "나빠진 방향이 아니라 규모를 재지 않았다 — "
                "0 이 아니라 '질문이 성립하지 않음' 이다"),
    }

    # ── 추세 — 연도별 (월이 아니다) ───────────────────────────────
    if 갈래.startswith("③") or 갈래.startswith("④"):
        target = topic["키"].split("_", 1)[1]      # th_<지표> / trend_<지표>
    else:
        target = _TREND_DEFAULT
    rows, note = _trend_years(t, target)
    추세 = {
        "출처": "실측", "지표": target, "단위": "연 (종결연도)",
        "연도별": rows,
        "사유": (note if rows else
                f"'{target}' 의 연도별 값을 낼 수 없다 — {note}"),
    }

    return {
        "주제": {k: topic.get(k) for k in
               ("키", "갈래", "제목", "한줄", "근거축", "구간", "기각사유")},
        "현황": 현황, "원인": 원인, "규모": 규모, "추세": 추세,
    }
