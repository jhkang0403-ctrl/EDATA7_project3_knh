# -*- coding: utf-8 -*-
"""리포트 8장 조립.

────────────────────────────────────────────────────────────────────
자동으로 쓰는 장과 사람이 쓰는 장이 나뉜다. 가르는 질문은 하나다.

    이 문장이 틀렸을 때 누가 책임지는가?
        사람이 진다        → 사람이 쓴다   (2 배경 · 6 해석 · 8 제안)
        사실이 틀린 것뿐   → 자동으로 쓴다 (1 요약 · 3 방법 · 4 결과 · 5 실험 · 7 한계)

**해석과 제안을 자동화하는 순간 책임이 사라진다.** 그것이 이 수업의 결론이다.
────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from core import config as C, metrics as M, validate as V

# ★ 자동 생성 문장에 인과를 단정하는 말을 쓰지 않는다.
#   관측 데이터로는 인과를 주장할 수 없는데, 방심하면 자동 문장이 인과를 쓴다.
#   내 도메인에만 있는 단정 표현이 있으면 여기에 더한다.
#   아래 다섯은 이 도메인(규제 심사)에서 더한 것 — "제출 미비로 지연을 초래했다" 류의
#   표현을 잡으려는 것이다. (Day4 실습 B)
BANNED = ["때문에", "덕분에", "효과로", "입증되었", "증명되었", "확실히",
          "인해", "기인한다", "초래했다", "야기했다", "달성했다"]

_VERDICT_KO = {"ok": "정상", "warn": "경고", "block": "위험"}


def check_phrasing(text: str) -> list[str]:
    """자동 생성 문장에 인과 단정 표현이 섞였는지 스스로 검사한다.

    **그대로 쓴다.** 사람이 쓴 장에도 걸어라 — 사람이 더 자주 쓴다.
    """
    return [w for w in BANNED if w in text]


def _fmt(n, unit=""):
    return f"{n:,.0f}{unit}"


# ── 자동으로 쓰는 장 ──────────────────────────────────────────────
def _s1_summary(t: dict) -> dict:
    """1. 요약

    수치는 쓰되 인과는 쓰지 않는다. "A가 낮다"는 되고 "B 때문에 A가 낮다"는 안 된다.
    원인은 넣지 않는다 — 왜 낮은지는 6장(해석, 사람이 쓴다) 몫이다.

    반환: {"title": "1. 요약", "kind": "auto", "body": "..."}
    """
    k = M.kpis(t)
    appr, rej, lead, intake = (k["최종 승인율"], k["반려율"],
                               k["평균 처리 일수"], k["신규 과제 수"])
    lv_appr = _VERDICT_KO[M.status_of("최종 승인율", appr["value"])]
    lv_rej = _VERDICT_KO[M.status_of("반려율", rej["value"])]
    lv_lead = _VERDICT_KO[M.status_of("평균 처리 일수", lead["value"])]

    body = (
        f"기간 {C.PERIOD[0]} ~ {C.PERIOD[1]}(종결일 기준) · 데이터 {C.DATASET} "
        f"(GRASNotices, 실측). 전체 접수 {intake['value']:,.0f}건 중 최종 승인율은 "
        f"{appr['value']:.1f}%({lv_appr}), 반려율은 {rej['value']:.1f}%({lv_rej})다. "
        f"접수일이 있는 건 기준 처리 일수 중앙값은 {lead['value']:,.0f}일({lv_lead})이다.\n\n"
        f"가장 최근 제출 묶음은 아직 미결 비율이 높아 종결 여부를 판정할 수 없다 — "
        f"근거는 4장·7장에 있다."
    )
    return {"title": "1. 요약", "kind": "auto", "body": body}


def _s3_method(t: dict) -> dict:
    """3. 방법

    분석 단위(그레인)를 반드시 밝힌다. 읽는 사람이 숫자를 다시 세어볼 수 있어야 한다.
    무엇을 어떻게 셌는지, 무엇을 뺐는지, 어떤 기준으로 판정했는지만 적는다 — 결과(숫자)는
    4장 몫이라 여기 넣지 않는다.
    """
    steps = " → ".join(C.FUNNEL_LABELS.get(s, s) for s in C.FUNNEL_STEPS)
    retention = " → ".join(name for name, _ in C.RETENTION_STEPS)
    body = (
        f"분석 단위(그레인) — 과제번호(GRN) 1건을 하나로 센다. 고유하게 센다(nunique), "
        f"행을 세지 않는다.\n\n"
        f"데이터 — 결론의 근거는 실측 GRASNotices만 쓴다. cases_synthetic·"
        f"funnel_events_synthetic은 연습용 합성 데이터라 결론에 쓰지 않는다.\n\n"
        f"퍼널 단계 — {steps}. 각 단계는 앞 단계 통과를 강제하지 않고 독립해서 센다; "
        f"이 데이터에서는 순서 위반 0건으로 확인됐다.\n\n"
        f"유지 퍼널 — 그레인은 통지자(Notifier, 회사) 1곳. {retention}. 관측 기간(코호트) "
        f"필터는 두지 않는다 — 이 편향은 7장 한계에 적는다.\n\n"
        f"지표 — 최종 승인율 = no_questions ÷ 전체 접수(Pending 포함). 반려율 = "
        f"(no_basis + ceased) ÷ 전체 접수. 평균 처리 일수 = median(종결일 빼기 접수일), "
        f"접수일이 있는 건만(1998~2019). 임계값 근거는 core/config.py THRESHOLDS 주석에 "
        f"있다.\n\n"
        f"무엇을 뺐는가 — 처리 일수가 0일 이하인 건(접수일이 종결일로 백필된 것으로 "
        f"보이는 데이터)은 처리 일수 계산에서 뺐다. "
        f"최소 표본(MIN_SAMPLE={C.MIN_SAMPLE})·최소 칸(MIN_CELL={C.MIN_CELL}) 기준 미만인 "
        f"분해 칸은 계산하지 않고 사유만 남겼다.\n\n"
        f"검정 — 이 분석에는 무작위 배정 실험이 없어 p값·신뢰구간을 쓰지 않는다. 분해 축 "
        f"비교는 격차 크기(기준 {C.MIN_GAP * 100:.0f}%p)로만 판정한다."
    )
    return {"title": "3. 방법", "kind": "auto", "body": body}


def _s4_results(t: dict) -> dict:
    """4. 결과

    숫자를 나열하되 **해석하지 않는다.** 해석은 6장이고 사람이 쓴다.
    "낮다"까지가 결과이고 "왜 낮은가"는 해석이라 여기 넣지 않는다.

    분해 결과는 아직 실측(GRASNotices)으로 계산하지 못한다 — GRASNotices를 단계별
    이벤트 로그로 바꾸는 어댑터가 없다(미정). 그래서 화면과 같은 연습용 합성 데이터로
    trust_check 판정 메커니즘만 보여준다. 실제 값이 아니므로 결론에 쓰지 않는다는
    점을 그대로 문장에 남긴다 (자세한 사정은 7장).
    """
    k = M.kpis(t)
    lines = ["[지표] (GRASNotices 실측, 그레인 = GRN 1건)"]
    for name in ("신규 과제 수", "최종 승인율", "반려율", "평균 처리 일수"):
        v = k[name]
        lv = _VERDICT_KO[M.status_of(name, v["value"])]
        lines.append(f"- {name}: {v['fmt'].format(v['value'])} ({lv}, n={v['n']:,})")

    rf = M.retention_funnel(t)
    if len(rf):
        lines.append("")
        lines.append("[유지 퍼널] (통지자 그레인, 코호트 필터 없음 — 한계는 7장)")
        for _, r in rf.iterrows():
            rate = (f", 단계 전환율 {r.step_rate * 100:.1f}%"
                    if pd.notna(r.step_rate) else "")
            lines.append(f"- {r.label}: {r.n:,}곳{rate}")

    vf = M.funnel_by_vintage(t)
    if len(vf):
        vv = M.vintage_verdict(vf)
        ab = vv[vv.판정 != "정상"]
        lines.append("")
        lines.append("[제출 시점별 묶음 판정] (GRN 번호 순)")
        if len(ab):
            for _, r in ab.iterrows():
                lines.append(f"- {r.묶음}: {r.판정} — {r.근거}")
        else:
            lines.append("- 모든 묶음이 정상 범위다.")

    charts = []
    fe, se = t.get("funnel_events_synthetic"), t.get("cases_synthetic")
    if fe is not None and se is not None:
        f = M.funnel(fe)
        if f.is_bottleneck.any():
            bi = max(int(f.index[f.is_bottleneck][0]), 1)
            sf, sto = f.step.iloc[bi - 1], f.step.iloc[bi]
            closing = sto == C.FUNNEL_STEPS[1]
            lines.append("")
            lines.append(
                f"[분해 결과] (연습용 합성 데이터로 확인한 메커니즘 — 결론 근거 아님, "
                f"{C.FUNNEL_LABELS.get(sf, sf)} → {C.FUNNEL_LABELS.get(sto, sto)} 구간)")
            for dim in ("host_identified", "country"):
                g = M.funnel_by(fe, se, dim, sf, sto, missing_is_pending=closing)
                v = M.funnel_by_verdict(g)
                lines.append(
                    f"- {dim}: {v['verdict']} (표시 {v['n_shown']}칸, "
                    f"감춤 {v['n_hidden']}칸)")

            # 차트는 이미지 안에 제목을 못 넣는다(viz/ 는 도메인이 아니라 안 고친다).
            # 그래서 차트 바로 위 문단이 라벨 역할을 한다 — 잘라내도 오해가 없게 문장을
            # 이 위치에 둔다.
            charts = ["funnel", "device"]
            lines.append("")
            lines.append(
                "※ 아래 차트 둘(퍼널·분해)은 모두 연습용 합성 데이터"
                "(funnel_events_synthetic · cases_synthetic)로 그린 것이다. "
                "실측 결론이 아니다 — 위 [지표]·[유지 퍼널]·[제출 시점별 묶음 판정]만 "
                "실측(GRASNotices)이다.")

    return {"title": "4. 결과", "kind": "auto", "body": "\n".join(lines),
            "charts": charts}


def _s5_experiments(t: dict) -> dict:
    """5. 실험

    무효 판정된 실험은 사유만 적고 수치를 쓰지 않는다 — 화면에서 감춘 숫자를 리포트에
    쓰면 감춘 의미가 없다. metrics.experiment_results() 의 verdict 를 보고 분기한다.

    이 도메인엔 실험이 없다 (t 에 "experiments" 테이블이 없어 experiment_results() 가
    빈 목록을 돌려준다 — 무작위 배정을 만들 수 있는 데이터가 아니다). 그래서
    전후 비교(제출 시점별 묶음)로 대신하되, **인과를 주장할 수 없다는 문장을 본문
    첫 문단에** 둔다.
    """
    res = M.experiment_results(t)
    if res:
        lines = []
        for r in res:
            if r["verdict"] == "무효":
                lines.append(f"- {r['id']} {r['name']}: 무효 — {r['reason']} "
                              f"(수치는 표시하지 않는다)")
            else:
                lines.append(f"- {r['id']} {r['name']}: {r['verdict']}")
        return {"title": "5. 실험", "kind": "auto", "body": "\n".join(lines)}

    lines = [
        "이 도메인에는 무작위 배정 실험이 없다. 인과를 주장할 수 없다 — 아래는 제출 "
        "시점별 묶음을 비교한 것일 뿐, 실험이 아니다.",
        "",
        "제출 시점별 묶음 비교 (참고용, GRN 번호 순):",
    ]
    vf = M.funnel_by_vintage(t)
    vv = M.vintage_verdict(vf) if len(vf) else None
    if vv is not None and len(vv):
        ab = vv[vv.판정 != "정상"]
        if len(ab):
            for _, r in ab.iterrows():
                lines.append(f"- {r.묶음}: {r.판정} — {r.근거}")
        else:
            lines.append("- 모든 묶음이 정상 범위라 남길 것이 없다.")
    else:
        lines.append("- 계산할 데이터가 없다.")
    return {"title": "5. 실험", "kind": "auto", "body": "\n".join(lines)}


def _s7_limits(t: dict) -> dict:
    """7. 한계 — 검증 경고에서 조립한다

    사람이 매번 쓰는 것이 아니라 경고를 그대로 옮긴다. 검증에서 경고가 났는데 한계에
    안 적히면 그 경고는 사라진 것과 같다.

    한계는 세 곳에서 온다.

        검증 경고        validate.run_checks() 에서 level == "warn" 인 것
        못 한 것         표본이 모자라 판정 못 한 것 · 어댑터가 없어 못 본 것
        찾았는데 없던 것  "없음"도 결과다

    이 도메인엔 가정값(CHANNEL_CAC 등)이 없어 "가정값 기반" 문구는 해당 없다.
    """
    lines = ["[검증 경고]"]
    warns = [c for c in V.run_checks(t) if c["level"] == "warn"]
    if warns:
        for c in warns:
            lines.append(f"- {c['name']}: {c['msg']}"
                         + (f" — {c['detail']}" if c["detail"] else ""))
    else:
        lines.append("- 없음")

    # 표본이 모자라 판정하지 않은 항목 — 실측(GRASNotices) 분해 어댑터가 아직 없어
    # 화면과 같은 연습용 합성 데이터로 trust_check 메커니즘만 확인했다.
    fe, se = t.get("funnel_events_synthetic"), t.get("cases_synthetic")
    hidden = []
    if fe is not None and se is not None:
        f = M.funnel(fe)
        if f.is_bottleneck.any():
            bi = max(int(f.index[f.is_bottleneck][0]), 1)
            sf, sto = f.step.iloc[bi - 1], f.step.iloc[bi]
            closing = sto == C.FUNNEL_STEPS[1]
            for dim in ("host_identified", "country"):
                g = M.funnel_by(fe, se, dim, sf, sto, missing_is_pending=closing)
                for _, r in g[g.사유.notna()].iterrows():
                    hidden.append(f"- (연습용 합성 데이터) {dim}={r[dim]}: {r.사유}")

    lines += ["", "[표본이 모자라 판정하지 않은 것]"]
    lines += hidden if hidden else ["- 없음 (현재 분해 칸은 모두 최소 칸 기준을 넘는다)"]
    lines.append("- 가드레일 2(재제출 필요 비율)의 경고·위험 임계값이 아직 없다. "
                  "정의서가 사용자가 정할 것으로 남겨둔 칸이다(core/config.py 참고).")

    lines += ["", "[찾았는데 없던 것]"]
    lines.append("- 국가(country)로 가르면 승인 여부가 갈리는지 확인했다 — 격차가 "
                 "정상 변동 폭 수준이라 이 축으로는 안 갈린다는 결론을 냈다.")

    lines += ["", "[이번 분석에서 확인하지 못한 것]"]
    lines.append("- GRASNotices를 단계별 이벤트 로그 모양으로 바꾸는 어댑터가 아직 "
                 "없어, 분해 축(bio·country) 전환율은 실측이 아니라 연습용 합성 "
                 "데이터로만 확인했다.")
    lines.append("- 유지 퍼널은 관측 기간이 다른 통지자를 코호트 없이 비교한다. "
                 "여기 나온 재방문율은 오래된 통지자가 유리한 값이고, 3년 고정창 "
                 "코호트로 편향을 걷으면 값이 달라진다(mydomain/notes/04_유지이탈.md).")
    lines.append("- 접수일이 2017년 이후 비공개라 평균 처리 일수 가드레일이 최근 "
                 "제출 건의 지연 여부를 아직 보여주지 못한다.")
    lines.append("- 화면(대시보드)의 퍼널·분해 수치는 연습용 합성 데이터로 그린 "
                 "것이라 이 리포트의 실측 결론과 값이 다르다 — 화면 값을 그대로 "
                 "인용하지 않는다.")

    lines += ["", "[항상 남기는 것]"]
    lines.append("- 관측 데이터이므로 인과를 주장할 수 없다.")
    lines.append(f"- 기간이 {C.PERIOD[0]}~{C.PERIOD[1]}이므로 그보다 긴 주기의 변화는 "
                 f"관측되지 않는다.")

    return {"title": "7. 한계", "kind": "auto", "body": "\n".join(lines)}


# ── 사람이 쓰는 장 (제공) ─────────────────────────────────────────
def _s2_background(human: dict) -> dict:
    return {
        "title": "2. 배경", "kind": "human",
        "body": human.get("2. 배경", ""),
        "placeholder": "이 분석을 왜 했는지, 어떤 의사결정을 앞두고 있는지 적으십시오.",
    }


def _s6_interpretation(human: dict) -> dict:
    return {
        "title": "6. 해석", "kind": "human",
        "body": human.get("6. 해석", ""),
        "placeholder": ("숫자가 무엇을 뜻하는지 적으십시오. "
                        "자동으로 쓰지 않습니다 — 해석은 사람의 책임입니다."),
    }


def _s8_proposal(human: dict) -> dict:
    return {
        "title": "8. 제안", "kind": "human",
        "body": human.get("8. 제안", ""),
        "placeholder": ("무엇을 할 것인지, 무엇을 하지 않을 것인지 적으십시오. "
                        "선택하지 않으면 제안이 아니라 보고입니다."),
    }


# ── 조립 ──────────────────────────────────────────────────────────
def _safe(title: str, fn, *args) -> dict:
    """아직 안 채운 장은 "todo" 종류로 돌려준다. 골격 전용."""
    from core.todo import NotYet
    try:
        return fn(*args)
    except NotYet as e:
        return {"title": title, "kind": "todo", "body": "", "todo": e}


def build(t: dict, human: dict | None = None) -> list[dict]:
    """8장을 조립한다. human 은 사람이 쓴 장의 본문 딕셔너리.

    **순서와 자동/사람 구분은 바꾸지 않는다.** 장 개수는 도메인에 맞게 줄여도 되지만,
    해석과 제안을 자동으로 돌리는 것만은 하지 않는다.
    """
    human = human or {}
    return [
        _safe("1. 요약", _s1_summary, t),
        _s2_background(human),
        _safe("3. 방법", _s3_method, t),
        _safe("4. 결과", _s4_results, t),
        _safe("5. 실험", _s5_experiments, t),
        _s6_interpretation(human),
        _safe("7. 한계", _s7_limits, t),
        _s8_proposal(human),
    ]


def email_draft(t: dict, sections: list[dict]) -> dict:
    """이메일 초안. **실제로 보내지 않는다.**

    그대로 쓴다. 이메일 HTML은 인라인 스타일과 표 레이아웃만 쓴다 —
    외부 CSS·자바스크립트·이미지는 대부분의 메일 클라이언트가 막는다.

    받을 사람이 없으면 초안까지만 만들고, 게이트 3은 "보냈다고 치고" 기록만 남긴다.
    """
    summary = next((s["body"] for s in sections if s["title"].startswith("1.")), "")
    subject = f"[성장 리포트] {C.PERIOD[0][:7]}~{C.PERIOD[1][:7]}"
    html = (
        f'<div style="font-family:sans-serif;color:#0f172a;max-width:640px">'
        f'<h2 style="font-size:18px">{subject}</h2>'
        f'<p style="font-size:14px;line-height:1.7;white-space:pre-line">'
        f'{summary}</p>'
        f'<p style="font-size:12px;color:#64748b;margin-top:20px">'
        f'자동 생성 · {datetime.now().strftime("%Y-%m-%d %H:%M")}</p></div>')
    return {"to": C.EMAIL_TO_EXAMPLE, "subject": subject, "html": html}
