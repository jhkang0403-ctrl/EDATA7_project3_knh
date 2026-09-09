# -*- coding: utf-8 -*-
"""리포트 — 남에게 보내는 문서.

8장 중 5장은 자동으로 쓰고, **3장(배경·해석·제안)은 사람이 쓴다.**
자동 생성 문장은 인과를 단정하지 않는지 스스로 검사한다.
"""
import streamlit as st

from core import config as C, gates, load, metrics as M
from report import proposal as P, sections as S, to_pdf
from viz import pdf_charts, ui

st.set_page_config(page_title="리포트", page_icon="📄", layout="wide",
                   initial_sidebar_state="expanded")
ui.css()
ui.sidebar_nav("report")

if "run" not in st.session_state:
    st.session_state.run = None
if "proposal_human" not in st.session_state:
    st.session_state.proposal_human = {}
if "human" not in st.session_state:
    st.session_state.human = {}
ui.context_bar(st.session_state.run)

t = ui.guard(load.load_all)
if t is None:
    st.stop()
secs = S.build(t, st.session_state.human)

# ★ 리포트 차트에 쓸 분해 축. 대시보드 DIMS 와 같은 컬럼(cases_synthetic).
DIM = "host_identified"


# ── 탭 ────────────────────────────────────────────────────────────
# 제안서는 오늘 **임시 자리**다. 기능을 먼저 만들고 자리는 내일 정한다 —
# 자리를 먼저 정하면 아직 없는 메뉴에 맞춰 코드를 짜게 된다. (Day2 판단 기준 5)
tab_report, tab_proposal = st.tabs(["리포트", "제안서(임시)"])

with tab_report:
    st.markdown('<div style="font-size:24px;font-weight:800;margin-bottom:16px">'
                '리포트</div>', unsafe_allow_html=True)

    nav, body = st.columns([1, 3.4])

    with nav:
        titles = [s["title"] for s in secs]
        pick = st.radio("목차", titles, label_visibility="collapsed")
        st.divider()
        done = sum(1 for s in secs if s["kind"] == "human" and s["body"].strip())
        need = sum(1 for s in secs if s["kind"] == "human")
        left = sum(1 for s in secs if s["kind"] == "todo")
        st.caption(f"사람 작성 {done}/{need}장")
        st.progress(done / need if need else 0)
        if left:
            st.caption(f"아직 안 만든 장 {left}개")

    sec = next(s for s in secs if s["title"] == pick)

    with body:
        kind = {"auto": "자동 생성", "human": "사람 작성",
                "todo": "아직 안 만듦"}[sec["kind"]]
        lvl = {"auto": "ok", "todo": "none"}.get(
            sec["kind"], "ok" if sec["body"].strip() else "warn")
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:10px">'
            f'<div style="font-size:19px;font-weight:700">{sec["title"]}</div>'
            f'{ui.badge(lvl, kind)}</div>', unsafe_allow_html=True)

        if sec["kind"] == "todo":
            ui.todo_card(sec["todo"])
        elif sec["kind"] == "auto":
            st.markdown(
                f'<div class="card"><div style="white-space:pre-line;'
                f'font-size:14px;line-height:1.75">{sec["body"]}</div></div>',
                unsafe_allow_html=True)
            bad = S.check_phrasing(sec["body"])
            if bad:
                ui.callout(f"자동 생성 문장에 인과를 단정하는 표현이 있습니다: "
                           f"<b>{', '.join(bad)}</b>. 관측 데이터로는 인과를 "
                           f"주장할 수 없습니다.")
            else:
                st.caption("✓ 인과 단정 표현 검사 통과")

            if "funnel" in sec.get("charts", []):
                f = M.funnel(t["funnel_events_synthetic"])
                st.image(pdf_charts.funnel_png(f), width="stretch")
            if "device" in sec.get("charts", []):
                f = M.funnel(t["funnel_events_synthetic"])
                bi = max(int(f.index[f.is_bottleneck][0]), 1)
                g = M.funnel_by(t["funnel_events_synthetic"], t["cases_synthetic"], DIM,
                                f.step.iloc[bi - 1], f.step.iloc[bi])
                g = g[g["사유"].isna()]          # 못 믿는 칸은 차트에 안 그린다
                st.image(pdf_charts.device_png(g), width="stretch")
            if "experiments" in sec.get("charts", []):
                st.image(pdf_charts.experiments_png(M.experiment_results(t)),
                         width="stretch")
        else:
            st.caption(sec["placeholder"])
            if sec.get("hint"):
                ui.callout(sec["hint"], "info")
            txt = st.text_area("본문", value=sec["body"], height=280,
                               key=f"h_{sec['title']}", label_visibility="collapsed")
            # 사람이 쓴 장에도 인과 단정 표현 검사를 건다 — 자동 생성 장보다 여기서
            # "때문에" 류가 더 자주 나온다 (Day4 실습 B).
            bad = S.check_phrasing(txt)
            if bad:
                ui.callout(f"인과를 단정하는 표현이 있습니다: <b>{', '.join(bad)}</b>. "
                           f"관측 데이터로는 인과를 주장할 수 없습니다.")
            elif txt.strip():
                st.caption("✓ 인과 단정 표현 검사 통과")
            if st.button("저장", type="primary"):
                st.session_state.human[sec["title"]] = txt
                st.rerun()

    # ── 내보내기 ──────────────────────────────────────────────────────
    st.divider()
    ui.section("내보내기")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**PDF** — 표지 · 목차 · 차트 포함")
        if st.button("PDF 만들기", type="primary"):
            with st.spinner("차트를 그리고 PDF를 조립하는 중..."):
                f = M.funnel(t["funnel_events_synthetic"])
                bi = max(int(f.index[f.is_bottleneck][0]), 1)
                g = M.funnel_by(t["funnel_events_synthetic"], t["cases_synthetic"], DIM,
                                f.step.iloc[bi - 1], f.step.iloc[bi])
                g = g[g["사유"].isna()]          # 못 믿는 칸은 차트에 안 그린다
                charts = {
                    "funnel": pdf_charts.funnel_png(f),
                    "device": pdf_charts.device_png(g),
                    "experiments": pdf_charts.experiments_png(M.experiment_results(t)),
                }
                pdf = to_pdf.build_pdf(secs, charts)
            st.session_state.pdf = pdf
            st.success(f"생성 완료 · {len(pdf)/1024:.0f}KB")
        if st.session_state.get("pdf"):
            st.download_button("PDF 내려받기", st.session_state.pdf,
                               file_name=f"성장리포트_{C.PERIOD[0][:7]}.pdf",
                               mime="application/pdf")

    with c2:
        st.markdown("**이메일 초안** — 실제로 보내지 않습니다")
        draft = S.email_draft(t, secs)
        st.text_input("받는 사람", draft["to"], disabled=True)
        st.text_input("제목", draft["subject"], disabled=True)
        with st.expander("본문 미리보기"):
            st.markdown(draft["html"], unsafe_allow_html=True)

        run = st.session_state.run
        if run and gates.is_passed(run, 2):
            st.markdown('<div class="gate final" style="margin-top:12px">'
                        '<div class="q">게이트 3 · 발송</div>'
                        '<div style="font-size:12.5px;color:#9f1239;margin-top:6px">'
                        '<b>되돌릴 수 없습니다.</b> 통과시키면 발송 기록이 남습니다.</div>'
                        '</div>', unsafe_allow_html=True)
            if gates.is_passed(run, 3):
                st.success("게이트 3 통과 기록됨 · 실제 발송은 하지 않았습니다.")
            else:
                ok = st.text_input('확인 문구로 "발송"을 입력하십시오', key="g3")
                if st.button("확정", disabled=(ok != "발송")):
                    gates.pass_gate(run, 3, "초안 확정 (실제 발송 없음)")
                    gates.save(run)
                    st.rerun()
        else:
            st.caption("게이트 2를 통과해야 발송 확정 단계가 열립니다.")


with tab_proposal:
    # ★ 카드는 **읽기만 한다.** 화면에서 고치기 시작하면 카드와 화면 중 어느 것이
    #   진짜인지 알 수 없게 된다. 값을 바꾸려면 제안카드.md 로 돌아간다. (교안 부록 A)
    cards = P.parse_cards()
    psecs = P.build(cards, st.session_state.proposal_human)

    st.markdown('<div style="font-size:24px;font-weight:800;margin-bottom:4px">'
                '제안서</div>', unsafe_allow_html=True)
    st.caption(f"카드 {len(cards['cards'])}장 · 읽기 전용 — "
               f"값을 고치려면 {cards['path']} 로 돌아갑니다")

    if not cards["cards"]:
        ui.callout("제안 카드가 없습니다. <b>/제안</b> 으로 먼저 카드를 만드십시오. "
                   "절 골격은 아래에 그대로 둡니다 — 왜 비었는지 보여야 합니다.")

    pnav, pbody = st.columns([1, 3.4])

    with pnav:
        ptitles = [s["title"] for s in psecs]
        ppick = st.radio("목차", ptitles, label_visibility="collapsed", key="p_nav")
        st.divider()
        pdone = sum(1 for s in psecs if s["kind"] == "human" and s["body"].strip())
        pneed = sum(1 for s in psecs if s["kind"] == "human")
        st.caption(f"사람 작성 {pdone}/{pneed}절")
        st.progress(pdone / pneed if pneed else 0)
        n_todo = sum(1 for c in cards["cards"]
                     for k in ("근거", "비용", "효과", "되돌림") if P.is_todo(c.get(k, "")))
        if n_todo:
            st.caption(f"카드에서 아직 안 채운 칸 {n_todo}개")

    psec = next(s for s in psecs if s["title"] == ppick)

    with pbody:
        pkind = {"auto": "자동 생성", "human": "사람 작성"}[psec["kind"]]
        plvl = "ok" if psec["kind"] == "auto" else ("ok" if psec["body"].strip() else "warn")
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:10px">'
            f'<div style="font-size:19px;font-weight:700">{psec["title"]}</div>'
            f'{ui.badge(plvl, pkind)}</div>', unsafe_allow_html=True)

        if psec["kind"] == "auto":
            # ★ 자동 절에는 입력창을 두지 않는다. 두는 순간 자동/사람 경계가 무너진다.
            st.markdown(
                f'<div class="card"><div style="white-space:pre-line;'
                f'font-size:14px;line-height:1.75">{psec["body"]}</div></div>',
                unsafe_allow_html=True)
            # 문장 검사 — **새로 만들지 않는다.** 리포트가 쓰는 그 함수를 그대로 부른다.
            # 화면에서 지키고 문서에서 안 지키면 의미가 없다. (Day2 판단 기준 4)
            pbad = P.check_phrasing(psec["body"])
            if pbad:
                ui.callout(f"자동 생성 문장에 인과를 단정하는 표현이 있습니다: "
                           f"<b>{', '.join(pbad)}</b>. 관측 데이터로는 인과를 "
                           f"주장할 수 없습니다.")
            else:
                st.caption("✓ 인과 단정 표현 검사 통과")
        else:
            # ★ 후보 목록은 **자동**이고 **읽기 전용**이다. 고르는 것과 쓰는 것만 사람이 한다.
            #   입력창(body) 밖에 그린다 — 안에 넣으면 사람이 기록을 고칠 수 있게 된다.
            cands = psec.get("candidates") or []
            if cands:
                st.caption("후보 — 판단기준.md 에서 자동으로 가져왔습니다 (읽기 전용)")
                rows = []
                for e in cands:
                    rows.append(f'<div style="font-size:12px;font-weight:700;'
                                f'color:{C.BRAND["muted"]};margin:6px 0 4px">'
                                f'{e["head"]}</div>')
                    for it in e["items"]:
                        rows.append(f'<div style="font-size:13px;line-height:1.65;'
                                    f'padding-left:10px">· {it}</div>')
                st.markdown('<div class="card">' + "".join(rows) + '</div>',
                            unsafe_allow_html=True)
                st.divider()
            st.caption(psec["placeholder"])
            ptxt = st.text_area("본문", value=psec["body"], height=280,
                                key=f"ph_{psec['title']}", label_visibility="collapsed")
            # ★ 사람이 쓴 절에도 같은 검사를 건다. **사람이 더 자주 쓴다.**
            #   리포트(사람 장)와 동작을 맞춘다 — 두 문서가 다르게 굴면 그게 더 헷갈린다.
            pbad_h = P.check_phrasing(ptxt)
            if pbad_h:
                ui.callout(f"인과를 단정하는 표현이 있습니다: "
                           f"<b>{', '.join(pbad_h)}</b>. "
                           f"관측 데이터로는 인과를 주장할 수 없습니다.")
            elif ptxt.strip():
                st.caption("✓ 인과 단정 표현 검사 통과")
            if st.button("저장", type="primary", key=f"pb_{psec['title']}"):
                st.session_state.proposal_human[psec["title"]] = ptxt
                st.rerun()

    # ── 내보내기 ──────────────────────────────────────────────────
    st.divider()
    ui.section("내보내기")
    st.caption("안 채워진 자리는 채우지 않고 그대로 내보냅니다 "
               "(문서에서 class=\"todo\" 로 남습니다).")
    pc1, pc2 = st.columns(2)
    with pc1:
        st.markdown("**HTML** — 수업자료 템플릿 그대로 · 단일 파일")
        st.download_button("제안서.html 내려받기",
                           P.to_html(psecs).encode("utf-8"),
                           file_name="제안서.html", mime="text/html",
                           key="dl_proposal_html")
    with pc2:
        st.markdown("**PDF** — 표지 · 목차 포함")
        # ⚠ 폰트에 없는 글자는 인쇄본에서 **경고 없이 사라진다.**
        #   바꿔치기 뒤에도 남은 것이 있으면 만들기 전에 알린다.
        left = P.missing_glyphs(psecs)
        if left:
            ui.callout("PDF 폰트에 없는 글자가 남아 있습니다: "
                       f"<b>{', '.join(left)}</b>. 인쇄본에서 사라집니다.")
        if st.button("PDF 만들기", type="primary", key="pdf_proposal_btn"):
            with st.spinner("제안서 PDF를 조립하는 중..."):
                st.session_state.proposal_pdf = P.build_pdf(psecs)
            st.success(f"생성 완료 · {len(st.session_state.proposal_pdf)/1024:.0f}KB")
        if st.session_state.get("proposal_pdf"):
            st.download_button("PDF 내려받기", st.session_state.proposal_pdf,
                               file_name="제안서.pdf", mime="application/pdf",
                               key="dl_proposal_pdf")
