# -*- coding: utf-8 -*-
"""대시보드 — 여기서 발견이 일어난다.

반복해서 보는 화면이므로 실행 절차를 지나치지 않고 바로 지표에 닿게 한다.

이 화면은 Day2~3에 걸쳐 살아난다.
  Day2  지표 카드 · 획득 퍼널 · 유지 퍼널
  Day3  분해 · 실험 카드
"""
import pandas as pd
import streamlit as st

from core import config as C, gates, load, metrics as M
from viz import charts, ui

st.set_page_config(page_title="대시보드", page_icon="📊", layout="wide",
                   initial_sidebar_state="expanded")
ui.css()
ui.sidebar_nav("dash")

if "run" not in st.session_state:
    st.session_state.run = None
# 대시보드는 반복해서 보는 화면이라, 이번 세션에서 아직 실행을 안 눌렀어도
# 저장된 실행 이력 중 가장 최근 것을 "마지막 실행"으로 보여준다. 표시용일 뿐이고
# 게이트 진행 상태(session_state.run)를 대신하지 않는다 — 그건 실행 화면에서만 쓴다.
_bar_run = st.session_state.run
if _bar_run is None:
    _past = gates.load_all()
    _bar_run = _past[0] if _past else None
ui.context_bar(_bar_run)

t = ui.guard(load.load_all)
if t is None:
    st.stop()

st.markdown('<div style="font-size:24px;font-weight:800;margin-bottom:4px">'
            '대시보드</div>', unsafe_allow_html=True)
st.caption("지표 카드 — 실측 GRASNotices 1,336건 · 그레인 GRN 1건")

# ── 지표 카드 (st.metric) ───────────────────────────────────────
# 기존 렌더는 viz/ui.py 의 kpi_card() 에 그대로 있다 — 비교용으로 남겨둠.
# 화면에 띄울 이름만 바꾼다. **키(name)는 그대로 둔다** — config.THRESHOLDS 와
# metrics.status_of() 가 이 키로 임계값을 찾는다. 여기서 이름을 바꾸면 색이 안 붙는다.
#   평균 처리 일수: 접수일이 2017년 이후 비공개라 2018년이 마지막 값이다.
#   다른 셋과 같은 모양으로 나란히 두면 지금도 감시되는 지표로 읽힌다.
_LABEL = {"평균 처리 일수": "평균 처리 일수 (~2018)"}

# 스냅샷 연도(PERIOD 끝)는 아직 반년치뿐이라 delta 비교에서 뺀다.
_CUR_YEAR = C.PERIOD[1][:4]

# 지표 정의 — (계산식, 임계값 근거). config.THRESHOLDS 주석에서 옮긴 요약.
_DEFS = {
    "최종 성공률": ("**주지표.** 그레인이 체인(재제출 묶음)이다 — 결론이 난 체인 중 "
                "no_questions 멤버가 하나라도 있는 체인의 비율. "
                "분모가 다르므로 아래 '최종 승인율'(GRN 기준)과 섞어 인용하지 않는다.",
                "임계값 없음 — 정의서가 사용자가 정할 것으로 남겨둔 칸이라 비워 두었다."),
    "재제출 필요 비율": ("**가드레일 ②.** 다건 체인 ÷ 전체 체인. 높을수록 나쁨.",
                   "임계값 없음 — 정의서가 사용자가 정할 것으로 남겨둔 칸이라 비워 두었다."),
    "신규 과제 수": ("GRASNotices 행 수 = 접수된 GRN 건수.",
                "임계값 없음 — 방향이 없는 카운트라 색 판정하지 않는다."),
    "최종 승인율": ("no_questions ÷ 전체 접수(Pending 포함).",
                "경고 75 = 95% CI 하단(76.8) 아래 · 위험 70 = 최근 10년 최저(71.2)도 안 간 선."),
    "평균 처리 일수": ("median(종결일 − 접수일). 접수일 있는 1998~2019 구간만.",
                  "경고 210 = 연도별 median 최댓값(2008년 208일) 위 · 위험 300 = 전체 P90(290일) 위."),
    "반려율": ("(no_basis + ceased) ÷ 전체 접수.",
             "경고 22 = 95% CI 상단(20.4) 위 · 위험 30 = 최근 10년 최고(29%) 초과."),
}
k = ui.guard(M.kpis, t)
if k:
    m = ui.guard(M.monthly, t)
    cols = st.columns(len(k))
    for col, (name, v) in zip(cols, k.items()):
        with col:
            lv = M.status_of(name, v["value"])

            # delta = monthly() 의 마지막 두 **완료된** 해의 차 (진행 중인 해 제외).
            # 두 해 중 하나라도 값이 없으면 만들지 않는다.
            delta, delta_help = None, None
            if m is not None and name in getattr(m, "columns", []):
                done = m[name][m[name].index < _CUR_YEAR]
                if (len(done) >= 2
                        and pd.notna(done.iloc[-1]) and pd.notna(done.iloc[-2])):
                    diff = done.iloc[-1] - done.iloc[-2]
                    unit = v["unit"]
                    delta = (f"{diff:+.1f}%p" if unit == "%"
                             else f"{diff:+,.0f}{unit}")
                    delta_help = f"{done.index[-2]} → {done.index[-1]}"

            st.metric(
                label=_LABEL.get(name, name),
                value=v["fmt"].format(v["value"]),
                delta=delta,
                delta_color=("inverse"
                             if C.THRESHOLDS.get(name, {}).get("높을수록_나쁨")
                             else "normal"),
                help=delta_help,
                border=True,
            )

            # 카드 밑 큰 추이선 — 연도별 값 3개 이상일 때만 (선 하나는 그릴 게 없다).
            # 판정 색을 그대로 써서 정상/경고/위험이 선 색으로도 드러나게 한다.
            if m is not None and name in getattr(m, "columns", []):
                series = m[name].dropna()
                if len(series) >= 3:
                    # 반려율은 판정과 무관하게 항상 주황 — "높을수록 나쁨" 지표임을
                    # 색으로도 표시해 달라는 요청. 나머지는 판정 색을 그대로 쓴다.
                    if name == "반려율":
                        spark_color = C.COLORS["warn"]
                    else:
                        spark_color = {"warn": C.COLORS["warn"],
                                      "block": C.COLORS["block"]}.get(
                                          lv, C.BRAND["primary"])
                    st.plotly_chart(
                        charts.spark(series, color=spark_color, height=104,
                                     show_edges=True),
                        width="stretch", config={"displayModeBar": False},
                        key=f"spark_{name}")

            # 지표 이름 옆 "정의" — 계산식과 임계값 근거를 함께. 클릭해야 보이던
            # 판정 과정 박스와, 상시 노출되던 캡션은 없앴다 — 여기 하나로 모은다.
            if name in _DEFS:
                with st.popover("정의", use_container_width=True):
                    st.markdown(f"**계산식** — {_DEFS[name][0]}")
                    st.markdown(f"**임계값 근거** — {_DEFS[name][1]}")
    if not C.THRESHOLDS:
        st.caption("config.THRESHOLDS 가 비어 있어 전부 정상으로 표시됩니다. "
                   "임계값을 채우면 색이 갈립니다.")

# ── 퍼널 (탭 + fragment) ───────────────────────────────────────
# 각 탭은 @st.fragment 안에서 그린다. 탭 안의 기간 필터를 바꾸면 그 fragment만
# 다시 실행되고 페이지 나머지는 그대로다 (맨 위 캡션 시각으로 확인).
def _year_range(dates, label):
    """데이터의 연도(YYYY) 목록으로 시작연도~끝연도 range 슬라이더. **화면 필터 전용.**

    이 도메인은 월 단위 표본이 얇다(월평균 4건 미만) — monthly()·THRESHOLDS 근거와
    같은 **연 단위**로만 본다. 반환은 (시작연도, 끝연도) 정수 또는 (None, None).
    """
    ys = sorted(pd.to_datetime(dates, errors="coerce").dropna()
                .dt.year.unique().tolist())
    if len(ys) < 2:
        return (int(ys[0]), int(ys[-1])) if ys else (None, None)
    lo, hi = st.select_slider(label, options=ys, value=(ys[0], ys[-1]))
    return int(lo), int(hi)


@st.fragment
def _tab_acquisition():
    ui.section("획득 퍼널", "연습용 합성 데이터 · 그레인을 먼저 확인한다")
    # 이 화면 한 장에 실측(위 지표 카드)과 합성(아래 퍼널·분해)이 같이 있다.
    # 표시가 없으면 읽는 사람은 둘 다 실측으로 읽는다.
    ui.callout(
        "아래 퍼널과 분해는 <b>연습용 합성 데이터</b>(2,000건)로 그린 것입니다. "
        "위 지표 카드(실측 GRASNotices 1,336건)와 <b>다른 데이터</b>이므로 "
        "숫자를 섞어 읽지 마십시오 — 결론의 근거는 실측만 씁니다.", "info")
    fe = t["funnel_events_synthetic"]
    lo, hi = _year_range(fe["event_time"], "기간 (시작연도 ~ 끝연도)")
    if lo is not None:
        yr = pd.to_datetime(fe["event_time"], errors="coerce").dt.year
        fe = fe[(yr >= lo) & (yr <= hi)]
    f = ui.guard(M.funnel, fe)
    if f is None:
        return

    if not f.is_bottleneck.any():
        st.caption("이 기간에는 병목을 계산할 만한 데이터가 없습니다.")
    else:
        left, right = st.columns([1.15, 1])
        with left:
            st.plotly_chart(charts.funnel_bars(f), width="stretch",
                            config={"displayModeBar": False})
            bn = f[f.is_bottleneck].iloc[0]
            bi = max(int(f.index[f.label == bn.label][0]), 1)
            prev = f.iloc[bi - 1]
            ui.callout(
                f"<b>병목은 {prev.label} → {bn.label}</b> 구간입니다. "
                f"{prev.n:,} 중 {bn.n:,}만 넘어가 "
                f"<b>{(1 - bn.step_rate) * 100:.1f}%가 이탈</b>합니다.")
        with right:
            # ★ 분해 축은 **config 가 원본이다.** 여기서 새로 정하지 않는다.
            #   (9주차 Day3 에 화면 두 곳에 흩어져 있던 것을 config 로 올렸다)
            #   손 쓸 수 있는 축으로 고른다 — 숙주 식별은 제출 서류 완성도의 프록시,
            #   국가는 못 바꾸는 축(격차도 거의 없어 "안 갈린다"를 확인하는 용도).
            DIMS = {k: v["label"] for k, v in C.FUNNEL_DIMS.items()}

            # URL 쿼리 파라미터(?axis=)와 연결. 없거나 이상한 값이면 첫 후보로 떨어진다.
            _fallback = next(iter(DIMS))
            _qp = st.query_params.get("axis")
            _init = _qp if _qp in DIMS else _fallback

            dim = st.segmented_control(
                "분해 축", options=list(DIMS), format_func=DIMS.get,
                default=_init, key="axis_seg",
                label_visibility="collapsed") or _init

            # 바뀌면 URL 갱신 (같으면 안 건드림 — 리런 루프 방지).
            if st.query_params.get("axis") != dim:
                st.query_params["axis"] = dim

            # 현재 화면 링크 — 복사해서 공유.
            try:
                _base = st.context.url.split("?")[0]
            except Exception:
                _base = ""
            st.caption("현재 화면 링크")
            st.code(f"{_base}?axis={dim}" if _base else f"?axis={dim}",
                    language=None)

            i = st.selectbox(
                "구간", range(len(f) - 1),
                format_func=lambda i: f"{f.label.iloc[i]} → {f.label.iloc[i + 1]}",
                index=min(bi - 1, len(f) - 2))
            closing = f.step.iloc[i + 1] == C.FUNNEL_STEPS[1]   # 제출 → 종결 구간
            g = ui.guard(M.funnel_by, fe, t["cases_synthetic"], dim,
                         f.step.iloc[i], f.step.iloc[i + 1],
                         missing_is_pending=closing)
            if g is not None and len(g):
                # ★ Day3 실습 B — 판정은 funnel_by 안에서 계산 앞에 끝났다.
                #   못 믿을 칸은 전환율·비중이 NaN 이고 사유만 있다.
                dcol = g.columns[0]
                shown, hidden = g[g.사유.isna()], g[g.사유.notna()]

                # ★ Day3 실습 C — 이 축의 판정. 색은 배지에만 (제목·테두리 장식 금지).
                v = M.funnel_by_verdict(g)
                st.markdown(
                    ui.badge(v["color"], v["verdict"])
                    + f'<span style="font-size:11px;color:{C.BRAND["muted"]};'
                      f'margin-left:8px">{v["note"]}</span>',
                    unsafe_allow_html=True)

                if len(shown):
                    st.plotly_chart(charts.device_compare(shown), width="stretch",
                                    config={"displayModeBar": False})
                if v["verdict"] == "주목할 만함":
                    lo_n, lo_r = v["lo"]
                    hi_n, hi_r = v["hi"]
                    lo_row = shown.loc[shown[dcol] == lo_n].iloc[0]
                    ui.callout(
                        f"<b>{lo_n}</b>이(가) 전체의 "
                        f"<b>{lo_row.비중 * 100:.1f}%</b>인데 전환율은 "
                        f"<b>{lo_r * 100:.1f}%</b>로 "
                        f"{hi_n}({hi_r * 100:.1f}%)보다 "
                        f"<b>{v['gap'] * 100:.1f}%p 낮습니다.</b>")
                for _, r in hidden.iterrows():
                    st.markdown(
                        f'<div class="blocked"><b>✕ {r[dcol]} — 지표를 표시하지 않습니다'
                        f'</b><br>{r.사유}</div>', unsafe_allow_html=True)

    # 퍼널 표 — ProgressColumn 의 format 은 printf 그대로라 0.97 을 넣으면 "1.0%" 로
    # 뜬다. 그래서 값을 0~100 으로 올려 넘기고 max_value=100 으로 맞춘다.
    def _pct(c):
        mx = c.max(skipna=True)
        return c if (mx and mx > 1.5) else c * 100   # 이미 0~100 이면 그대로
    st.dataframe(
        pd.DataFrame({"단계": f.label, "도달 수": f.n,
                      "단계 전환율": _pct(f.step_rate), "누적 전환율": _pct(f.cum_rate)}),
        column_config={
            "단계": st.column_config.TextColumn("단계"),
            "도달 수": st.column_config.NumberColumn("도달 수", format="%,d"),
            "단계 전환율": st.column_config.ProgressColumn(
                "단계 전환율", min_value=0, max_value=100, format="%.1f%%"),
            "누적 전환율": st.column_config.ProgressColumn(
                "누적 전환율", min_value=0, max_value=100, format="%.1f%%"),
        },
        hide_index=True,
        width="stretch",
    )


@st.fragment
def _tab_retention():
    ui.section("유지 퍼널", "실측 GRASNotices · 데려온 대상이 남는가")
    if not C.RETENTION_STEPS:
        st.caption("config.RETENTION_STEPS 가 비어 있습니다. "
                   "7주차에 정한 유지·이탈의 정의를 옮기면 여기에 그려집니다.")
        return
    g = t["GRASNotices"]
    lo, hi = _year_range(g["closure_date"], "기간 (종결 시작연도 ~ 끝연도)")
    tt = t
    if lo is not None:
        yr = pd.to_datetime(g["closure_date"], errors="coerce").dt.year
        tt = {**t, "GRASNotices": g[(yr >= lo) & (yr <= hi)]}
    rf = ui.guard(M.retention_funnel, tt)
    if rf is None or not len(rf) or rf.n.iloc[0] == 0:
        st.caption("이 기간에 회사 데이터가 없습니다.")
        return
    if "is_bottleneck" not in rf.columns:
        rf = rf.assign(is_bottleneck=False)
    c1, c2 = st.columns([1.15, 1])
    with c1:
        st.plotly_chart(charts.funnel_bars(rf), width="stretch",
                        config={"displayModeBar": False})
    with c2:
        ui.callout(
            "유지는 <b>관측 기간이 대상마다 다릅니다.</b> "
            "먼저 들어온 대상은 오래 관측됐고 나중에 들어온 대상은 짧게 관측됐습니다. "
            "<b>누적값으로 비교하면 기간의 그림자를 효과로 착각합니다.</b> "
            "비율(단위 기간당)로 바꾸거나 같은 시점에 시작한 것끼리 묶으십시오.",
            "info")


_ftabs = st.tabs(["획득 퍼널", "유지 퍼널"])
with _ftabs[0]:
    _tab_acquisition()
with _ftabs[1]:
    _tab_retention()

# ── vintage (제출 시점별 전환) ───────────────────────────────────
ui.section("제출 시점별 전환",
           "실측 GRASNotices · 최근 값이 낮으면 성과 문제인지, 아직 갈 시간이 없어서인지")
vf = ui.guard(M.funnel_by_vintage, t)
if vf is not None and len(vf):
    st.caption("시작 시점 프록시 = GRN 번호(제출 순 부여, 종결일 순위와 상관 0.999). "
               "최근 6개 묶음만 50건씩, 그 이전은 한 줄로 합침.")
    vv = M.vintage_verdict(vf)
    show = vf.merge(vv[["묶음", "판정"]], on="묶음").rename(columns={
        "제출_종결": "제출→종결 %", "종결_성공": "종결→성공 %", "누적_성공": "누적 성공 %"})
    st.dataframe(show, width="stretch", hide_index=True)
    for _, r in vv[vv.판정 != "정상"].iterrows():
        kind = "info" if r.판정 == "관측 중단" else "warn"
        ui.callout(f"<b>{r.묶음} — {r.판정}.</b> {r.근거}", kind)

# ── 실험 ──────────────────────────────────────────────────────────
ui.section("실험 결과", "믿을 수 있는지 먼저 보고, 그 다음에 지표를 본다")
res = ui.guard(M.experiment_results, t)
if res is not None and not res:
    st.caption("실험이 없습니다. 전후 비교로 대신하되 "
               "**인과를 주장할 수 없다**를 카드에 남기십시오.")
for r in (res or []):
    cls = r["color"]
    head = (f'<div class="exp {cls}">'
            f'<div style="display:flex;align-items:flex-start;gap:12px">'
            f'<div style="flex:1"><div class="id">{r["id"]}</div>'
            f'<div class="nm">{r["name"]}</div>'
            f'<div class="hy">{r["hypothesis"]}</div></div>'
            f'<div>{ui.badge(cls, r["verdict"])}</div></div>')

    if r["verdict"] == "무효":
        # 못 믿을 실험의 숫자는 보여주지 않는다.
        # 계산해 놓고 숨기는 것이 아니라 계산 자체를 하지 않았다.
        head += (f'<div class="blocked"><b>✕ 지표를 표시하지 않습니다</b><br>'
                 f'{r["reason"]}</div>')
        st.markdown(head + "</div>", unsafe_allow_html=True)
        continue

    if "rc" not in r:
        head += (f'<div style="margin-top:12px;font-size:13px;color:#64748b">'
                 f'{r.get("reason", "")}</div>')
        st.markdown(head + "</div>", unsafe_allow_html=True)
        continue

    head += (f'<div style="margin-top:14px;display:flex;gap:28px;'
             f'align-items:baseline;flex-wrap:wrap">'
             f'<div><div style="font-size:11px;color:#64748b">{r["primary"]}</div>'
             f'<div class="mv">{r["rc"]*100:.2f}% → {r["rt"]*100:.2f}%</div></div>'
             f'<div><div style="font-size:11px;color:#64748b">상대 효과</div>'
             f'<div class="mv">{r["lift"]*100:+.1f}%</div></div>'
             f'<div><div style="font-size:11px;color:#64748b">p값</div>'
             f'<div class="mv">{r["p"]:.4f}</div></div>'
             f'<div><div style="font-size:11px;color:#64748b">표본</div>'
             f'<div style="font-size:13px;color:#475569" class="num">'
             f'{r["nc"]:,} / {r["nt"]:,}</div></div></div>')
    st.markdown(head + "</div>", unsafe_allow_html=True)

    c1, c2 = st.columns([1, 1.1])
    with c1:
        st.caption("효과 크기와 95% 신뢰구간 (0을 지나면 유의하지 않음)")
        st.plotly_chart(charts.forest(r), width="stretch",
                        config={"displayModeBar": False}, key=f"fr_{r['id']}")
    with c2:
        if r.get("guard"):
            gd = r["guard"]
            bad = gd["delta"] < -0.03
            st.markdown(
                f'<div class="card tight" style="border-color:'
                f'{C.COLORS["warn"] if bad else C.BRAND["line"]}">'
                f'<div style="font-size:11px;color:#64748b">가드레일 · {gd["name"]}</div>'
                f'<div style="font-size:20px;font-weight:700;margin-top:4px" class="num">'
                f'{gd["control"]*100:.1f}% → {gd["treatment"]*100:.1f}% '
                f'<span style="color:{C.COLORS["warn"] if bad else C.COLORS["ok"]}">'
                f'({gd["delta"]*100:+.1f}%p)</span></div>'
                + ('<div class="note">주지표는 개선됐지만 가드레일이 무너졌습니다.</div>'
                   if bad else
                   '<div style="font-size:12px;color:#64748b;margin-top:6px">'
                   '이상 없음</div>')
                + '</div>', unsafe_allow_html=True)
        elif r.get("reason"):
            st.markdown(f'<div class="card tight">'
                        f'<div style="font-size:13px;color:#64748b">{r["reason"]}</div>'
                        f'</div>', unsafe_allow_html=True)

    # 기간을 쪼개야 드러나는 것 — 초기 효과가 남아 있는가
    w = M.weekly_effect(r, r["start"])
    if not w.empty and len(w) >= 3:
        with st.expander("기간을 쪼개서 보기 — 효과가 유지되는가"):
            st.plotly_chart(charts.effect_decay(w), width="stretch",
                            config={"displayModeBar": False})
            ui.callout(
                f"전체 평균은 <b>{r['lift']*100:+.1f}%</b>인데 "
                f"초반 <b>{w.lift.iloc[0]*100:+.0f}%</b>에서 "
                f"후반 <b>{w.lift.iloc[-1]*100:+.0f}%</b>로 갑니다. "
                f"기간 평균만 보면 안 보이는 것입니다.")

    # 그때 멈췄다면 무엇을 봤을까
    pc = M.peeking_curve(r, r["start"])
    if not pc.empty and len(pc) >= 3:
        with st.expander("만약 여기서 멈췄다면? — 조기 중단 시뮬레이터"):
            cuts = list(pc.cut.astype(int))
            sel = st.select_slider("실험 종료일", options=cuts, value=cuts[0],
                                   key=f"peek_{r['id']}")
            row = pc[pc.cut == sel].iloc[0]
            a, b = st.columns([1, 1.4])
            with a:
                lv = "warn" if row.sig else "none"
                st.markdown(
                    ui.kpi_card(f"{sel}일차에 종료했다면", f"{row.lift*100:+.1f}%",
                                "유의 — 성공으로 보고" if row.sig
                                else "유의하지 않음", lv),
                    unsafe_allow_html=True)
                st.caption(f"p = {row.p:.3f}")
            with b:
                st.plotly_chart(charts.peeking(pc, r["lift"]), width="stretch",
                                config={"displayModeBar": False})
            ui.callout("종료 시점은 실험을 **시작하기 전에** 정해야 합니다.")
