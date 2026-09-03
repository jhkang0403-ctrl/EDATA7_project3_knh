# -*- coding: utf-8 -*-
"""검증.

검증은 **자동으로 통과시키지 않는다.** 결과를 사람 앞에 놓고 게이트에서 판단하게 한다.
경고를 앱이 마음대로 무시하면, 사람은 무엇을 승인했는지 모른 채 승인하게 된다.

판정 3종:

  ok    통과
  warn  경고 — **정상일 수도 있다. 사람이 판단한다.**
  block 차단 — 이 상태로는 분석할 수 없다.

────────────────────────────────────────────────────────────────────
차단과 경고를 가르는 것은 한 질문이다.

    이 규칙이 깨진 채로 계산하면 값이 틀리는가?
        틀린다              → block
        해석만 조심하면 된다 → warn

차단을 늘리면 안전해 보이지만, 실무 데이터는 늘 어딘가 깨져 있어서
앱이 아무것도 못 돌리게 된다. **차단은 "이대로 계산하면 확실히 틀리는 것"에만 건다.**
────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import pandas as pd

from core import config as C
from core.load import to_dt


def _r(name, level, msg, detail=""):
    """검증 결과 한 줄. 그대로 쓴다."""
    return {"name": name, "level": level, "msg": msg, "detail": detail}


def profile(t: dict) -> pd.DataFrame:
    """적재 직후 개요. 게이트 1에서 사람이 보는 화면.

    **그대로 쓴다.** 어느 도메인이든 행수·컬럼·기간·결측은 먼저 본다.
    """
    rows = []
    for name, df in t.items():
        date_col = next((c for c in df.columns
                         if c.endswith("_date") or c == "year_month"), None)
        span = ""
        if date_col is not None:
            s = df[date_col].astype(str)
            span = f"{s.min()} ~ {s.max()}"
        rows.append({
            "테이블": name, "행수": len(df), "컬럼": df.shape[1],
            "기간": span,
            "결측 컬럼": int(df.isna().any().sum()),
            "메모리(MB)": round(df.memory_usage(deep=True).sum() / 1e6, 1),
        })
    return pd.DataFrame(rows)


# ── 규칙 3건이 쓰는 기준표 ────────────────────────────────────────
# 기대 행수. **재현의 기준선**이다.
# FDA GRAS Inventory 는 갱신된다(원본 사본은 2026-08-18 갱신분). 행 수가 달라지면
# mydomain/notes/ 에 적힌 숫자가 전부 낡은 것이 되므로 조용히 넘기면 안 된다.
EXPECTED_ROWS = {
    "GRASNotices": 1_336,
    "cases_synthetic": 2_000,
    "funnel_events_synthetic": 6_064,
}

# 계산에 반드시 있어야 하는 컬럼. 없으면 값이 틀리는 게 아니라 **아예 못 돈다.**
# GRASNotices 는 파생 컬럼을 본다 — 정제 안 된 원본 CSV 를 넣으면 여기서 잡힌다.
REQUIRED_COLS = {
    "GRASNotices": ["grn", "cat", "closure_date", "chain", "bio", "country"],
    "cases_synthetic": ["case_id", "host_identified", "country"],
    "funnel_events_synthetic": ["case_id", "stage", "event_time"],
}

# 테이블별 날짜 컬럼과 **기대 범위**. 날짜가 없는 테이블(cases_synthetic)은 검사하지 않는다.
#
#   real   True  실측 원본. PERIOD 가 곧 이 테이블의 유효구간이다.
#          False 합성. PERIOD 를 넘어가는 것이 **설계상 정상**이다.
#   span   그 테이블이 실제로 들어와야 하는 범위.
#
# 왜 span 을 따로 두는가 — 합성이라고 무조건 경고로 두면 **누가 날짜를 통째로
# 옮겨도 경고에 머문다.** 벗어난 건수만 늘어나 보일 뿐이라 손상을 못 잡는다.
# 그래서 합성에도 자기 기대 범위를 주고, 그것마저 벗어나면 차단한다.
#
# funnel_events_synthetic 의 span 은 generate_mydata.py 의 설계값이다
# (제출은 2025-09-01부터 12개월 · 종결까지 30~200일 · 관측 스냅샷 +135일).
# → mydomain/notes/데이터노트_합성데이터.md 의 실측 프로파일과 같다.
# ⚠ 생성 스크립트를 고쳐 다시 만들면 이 값도 함께 고쳐야 한다.
DATE_SPEC = {
    "GRASNotices": {
        "col": "closure_date", "real": True, "span": C.PERIOD,
    },
    "funnel_events_synthetic": {
        "col": "event_time", "real": False, "span": ("2025-09-01", "2027-01-14"),
    },
}


def run_checks(t: dict) -> list[dict]:
    """정합성 검증. 결과는 게이트 1에서 사람에게 보여준다.

    규칙 3건. 각 규칙의 레벨은 **"이게 깨진 채로 계산하면 값이 틀리는가"** 로 갈랐다.

        1. 행 수      0행·표본 미만 -> block  /  기준선과 다름 -> warn
        2. 필수 컬럼  없음           -> block
        3. 날짜 범위  실측 원본      -> block  /  합성           -> warn

    반환: [_r(이름, 레벨, 메시지, 상세), ...]
    """
    out = []

    # ── 규칙 1. 행 수 ─────────────────────────────────────────────
    # 근거: 0행이거나 MIN_SAMPLE 미만이면 비율 자체를 낼 수 없다(적재 실패·파일 잘림).
    #      기준선과 다른 것은 계산은 되지만 노트의 숫자와 안 맞는다는 뜻이라 경고다.
    empty, small, drift, fine = [], [], [], []
    for name, df in t.items():
        n = len(df)
        exp = EXPECTED_ROWS.get(name)
        if n == 0:
            empty.append(f"{name} 0행")
        elif n < C.MIN_SAMPLE:
            small.append(f"{name} {n:,}행 (최소 {C.MIN_SAMPLE:,})")
        elif exp is not None and n != exp:
            drift.append(f"{name} {n:,}행 (기준 {exp:,}, {n - exp:+,})")
        else:
            fine.append(f"{name} {n:,}행")
    if empty or small:
        out.append(_r("행 수", "block",
                      "계산할 수 없습니다: " + ", ".join(empty + small),
                      "0행이거나 최소 표본 미만입니다. 적재가 실패했거나 파일이 잘렸습니다."))
    elif drift:
        out.append(_r("행 수", "warn",
                      "기준선과 다릅니다: " + ", ".join(drift),
                      "원본이 갱신되었을 수 있습니다. mydomain/notes/ 의 실측값과 "
                      "달라지므로, 리포트에 인용하기 전에 measure.py 를 다시 돌리십시오."))
    else:
        out.append(_r("행 수", "ok", " · ".join(fine)))

    # ── 규칙 2. 필수 컬럼 ─────────────────────────────────────────
    # 근거: 계산에 쓰는 컬럼이 없으면 값이 틀리는 게 아니라 아예 안 돈다. 무조건 차단.
    missing, checked = [], 0
    for name, cols in REQUIRED_COLS.items():
        if name not in t:
            continue
        have = set(t[name].columns)
        checked += len(cols)
        missing += [f"{name}.{c}" for c in cols if c not in have]
    out.append(_r("필수 컬럼", "block" if missing else "ok",
                  (f"{len(missing)}개 없습니다: " + ", ".join(missing)) if missing
                  else f"필수 컬럼 {checked}개가 모두 있습니다",
                  "정제되지 않은 원본을 넣었을 수 있습니다. GRASNotices 는 "
                  "measure.py 로 정제한 parquet 이어야 합니다." if missing else ""))

    # ── 규칙 3. 날짜 범위 ─────────────────────────────────────────
    # 근거: 테이블마다 **자기 기대 범위(span)** 를 벗어나면 데이터가 손상된 것이다 -> block.
    #        실측  span == PERIOD. 벗어나면 원본이 갱신된 것이고 지표 정의서가 무효가 된다
    #        합성  span == 생성 설계 범위. 벗어나면 누가 날짜를 옮겼거나 다시 생성한 것이다
    #      span 안에 있으면서 PERIOD 만 넘는 합성은 **설계상 정상**이다 -> warn.
    p_lo, p_hi = pd.Timestamp(C.PERIOD[0]), pd.Timestamp(C.PERIOD[1])
    real_bad, syn_bad, overhang, in_range = [], [], [], []
    for name, spec in DATE_SPEC.items():
        col = spec["col"]
        if name not in t or col not in t[name].columns:
            continue
        d = to_dt(t[name][col]).dropna()
        if d.empty:
            continue
        s_lo, s_hi = pd.Timestamp(spec["span"][0]), pd.Timestamp(spec["span"][1])
        n_span = int(((d < s_lo) | (d > s_hi)).sum())
        seen = f"{name} {d.min().date()}~{d.max().date()}"
        if n_span:
            (real_bad if spec["real"] else syn_bad).append(
                f"{seen} (기대 {spec['span'][0]}~{spec['span'][1]}), {n_span:,}건")
            continue
        n_period = int(((d < p_lo) | (d > p_hi)).sum())
        if n_period:
            overhang.append(f"{seen}, {n_period:,}건")
        else:
            in_range.append(seen)

    if real_bad or syn_bad:
        detail = []
        if real_bad:
            detail.append(f"실측: config.PERIOD({C.PERIOD[0]} ~ {C.PERIOD[1]})는 "
                          "실측 데이터의 유효구간입니다. 벗어났다면 원본이 갱신된 "
                          "것이고, 지표 정의서의 유효구간부터 다시 조회해야 합니다.")
        if syn_bad:
            detail.append("합성: 생성 설계 범위를 벗어났습니다. 날짜가 손상됐거나 "
                          "generate_mydata.py 를 바꿔 다시 만든 것입니다. "
                          "후자라면 validate.DATE_SPEC 의 span 을 함께 고치십시오.")
        out.append(_r("날짜 범위", "block",
                      "기대 범위를 벗어났습니다: " + ", ".join(real_bad + syn_bad),
                      " / ".join(detail)))
    elif overhang:
        out.append(_r("날짜 범위", "warn",
                      "합성 데이터가 PERIOD 를 넘어갑니다(설계상 정상): "
                      + ", ".join(overhang),
                      "합성 데이터는 제출 이후 심사 기간을 미래로 시뮬레이션하도록 "
                      "설계되어 있습니다. 생성 설계 범위 안에는 들어 있으므로 값이 "
                      "틀린 것이 아니라, 실측과 섞어 읽지 않으면 됩니다. "
                      "→ 리포트 7장 한계로 옮깁니다."))
    else:
        out.append(_r("날짜 범위", "ok",
                      "모든 테이블이 기대 범위 안에 있습니다",
                      " · ".join(in_range)))

    return out


def summarize(checks: list[dict]) -> dict:
    """통과·경고·차단을 센다. 차단이 하나라도 있으면 게이트를 못 넘는다.

    **그대로 쓴다.**
    """
    n = {"ok": 0, "warn": 0, "block": 0}
    for c in checks:
        n[c["level"]] += 1
    return {**n, "total": len(checks), "can_pass": n["block"] == 0}


# ══════════════════════════════════════════════════════════════════
# 참고 — 통신사 데이터에서 쓴 검증 12건
#
# **이 함수는 호출되지 않는다.** 읽고 필요한 것만 위 run_checks() 로 옮긴다.
# 대부분은 통신사 테이블·컬럼에 묶여 있어서 그대로는 안 돌아간다.
#
# 눈여겨볼 것은 규칙 자체가 아니라 **무엇을 block 으로 두고 무엇을 warn 으로
# 뒀는가**이다.
#
#   block  기간 정합성 · 퍼널 순서 · 신규 고객 일치 · 배정 중복 ·
#          중도절단 · 참조 무결성        ← 깨지면 계산이 틀린다
#   warn   월 커버리지 · 결측률 2건 · 응답률 · 표본 수 · 배정 균형
#                                        ← 정상일 수도 있다. 사람이 판단한다
# ══════════════════════════════════════════════════════════════════
def reference_checks_telecom(t: dict) -> list[dict]:
    out = []
    lo, hi = pd.Timestamp(C.PERIOD[0]), pd.Timestamp(C.PERIOD[1])
    cu, se, fe = t["customers"], t["sessions"], t["funnel_events"]
    um, asg, ad = t["usage_monthly"], t["experiment_assignments"], t["ad_spend"]

    # 1. 기간 — 기간이 어긋나면 조인에 구멍이 생긴다
    bad = []
    for label, s in [("sessions", se.session_date), ("funnel_events", fe.event_date),
                     ("ad_spend", ad.spend_date)]:
        d = to_dt(s)
        if d.min() < lo or d.max() > hi:
            bad.append(f"{label} {d.min().date()}~{d.max().date()}")
    out.append(_r("기간 정합성", "block" if bad else "ok",
                  "기간을 벗어난 테이블이 있습니다" if bad else
                  f"모든 테이블이 {C.PERIOD[0]} ~ {C.PERIOD[1]} 안에 있습니다",
                  "; ".join(bad)))

    # 2. 월 커버리지 — 빠진 달이 있어도 정상일 수 있다
    m = sorted(um.year_month.astype(str).unique())
    out.append(_r("월 커버리지", "ok" if len(m) == 12 else "warn",
                  f"{m[0]} ~ {m[-1]} ({len(m)}개월)"))

    # 3. 퍼널 역행 — 앞 단계를 안 거치고 뒤 단계에 온 대상
    piv = (fe.pivot_table(index="visitor_id", columns="step_order",
                          values="event_id", aggfunc="count").fillna(0) > 0)
    cols = sorted(piv.columns)
    viol = sum(int(((~piv[a]) & piv[b]).sum()) for a, b in zip(cols, cols[1:]))
    out.append(_r("퍼널 순서", "block" if viol else "ok",
                  f"단계 역행 {viol}건" if viol else "단계 역행 없음"))

    # 4. 신규 고객 = 최종 통과자
    paid = set(fe.loc[fe.funnel_step == C.FUNNEL_STEPS[-1], "visitor_id"])
    newc = set(cu.loc[cu.visitor_id.notna(), "visitor_id"])
    out.append(_r("신규 고객 일치", "ok" if newc == paid else "block",
                  f"신규 {len(newc):,}명 / 최종 통과 {len(paid):,}명"))

    # 5. 실험 배정 중복 — 한 대상이 두 번 배정되면 결과를 못 믿는다
    dup = int(asg.duplicated(["experiment_id", "visitor_id"]).sum())
    out.append(_r("배정 중복", "block" if dup else "ok",
                  f"중복 {dup}건" if dup else "중복 없음"))

    # 6. 중도절단 — 떠난 뒤의 기록이 있으면 데이터가 잘못됐다
    ch = cu[cu.is_churned][["customer_id", "churn_date"]].copy()
    ch["cm"] = to_dt(ch.churn_date).dt.strftime("%Y-%m")
    mg = um.merge(ch, on="customer_id", how="inner")
    after = int((mg.year_month.astype(str) > mg.cm).sum())
    out.append(_r("중도절단", "block" if after else "ok",
                  f"이탈 이후 사용 기록 {after}건" if after else
                  "이탈 이후 사용 기록 없음"))

    # 7. 참조 무결성 — 끊어진 참조가 있으면 조인에서 조용히 사라진다
    fk_bad = []
    if not set(um.customer_id) <= set(cu.customer_id):
        fk_bad.append("usage_monthly")
    if not set(fe.session_id) <= set(se.session_id):
        fk_bad.append("funnel_events")
    out.append(_r("참조 무결성", "block" if fk_bad else "ok",
                  f"끊어진 참조: {', '.join(fk_bad)}" if fk_bad else "모든 참조 정상"))

    # 8. 결측 — 경고로만 낸다. **구조적 결측은 오류가 아니다.**
    nn = int(cu.visitor_id.isna().sum())
    if nn:
        out.append(_r("visitor_id 결측", "warn",
                      f"고객 {len(cu):,}명 중 {nn:,}명({nn/len(cu)*100:.0f}%)이 "
                      f"퍼널 이력이 없습니다",
                      "기존 고객은 이번 기간 퍼널을 거치지 않았으므로 정상일 수 있습니다. "
                      "다만 퍼널 테이블과 INNER JOIN하면 이 인원이 전부 사라집니다."))

    # 9. 캠페인 결측 — 자연 유입은 캠페인이 없다
    cn = int(se.campaign_id.isna().sum())
    if cn:
        out.append(_r("campaign_id 결측", "warn",
                      f"세션 {len(se):,}건 중 {cn:,}건({cn/len(se)*100:.0f}%)에 "
                      f"캠페인이 없습니다",
                      "자연 유입(검색·직접 방문)은 캠페인이 없으므로 정상일 수 있습니다."))

    # 10. 응답률 — 응답자 평균은 전체 평균이 아니다
    st_ = t["support_tickets"]
    resp = st_.satisfaction_score.notna().mean()
    if resp < 0.5:
        out.append(_r("만족도 응답률", "warn",
                      f"응답률 {resp*100:.1f}% — 응답자 평균은 전체 만족도가 아닙니다",
                      "극단적 경험을 한 쪽이 더 많이 응답하는 경향이 있습니다. "
                      "이 경고는 리포트 7장 한계로 옮깁니다."))

    # 11. 표본 크기
    small = []
    for _, e in t["experiments"].iterrows():
        n = int((asg.experiment_id == e.experiment_id).sum())
        if n < C.MIN_SAMPLE:
            small.append(f"{e.experiment_id}({n:,})")
    out.append(_r("실험 표본", "warn" if small else "ok",
                  f"표본 부족: {', '.join(small)}" if small else
                  "모든 실험이 최소 표본을 넘습니다"))

    # 12. SRM — 실험 결과를 보기 전에 반드시 확인
    from core.metrics import srm_check
    broken = []
    for _, e in t["experiments"].iterrows():
        s = srm_check(asg, e.experiment_id)
        if not s["ok"]:
            broken.append(f"{e.experiment_id} ({s['ratio'][0]*100:.1f}:"
                          f"{s['ratio'][1]*100:.1f}, p={s['p']:.1e})")
    out.append(_r("실험 배정 균형(SRM)", "warn" if broken else "ok",
                  f"배정이 깨진 실험: {', '.join(broken)}" if broken else
                  "모든 실험의 배정이 균형입니다",
                  "배정이 깨진 실험은 어떤 효과가 나와도 해석할 수 없습니다. "
                  "결과를 쓰지 말고 재실험해야 합니다." if broken else ""))

    return out
