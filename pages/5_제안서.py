# -*- coding: utf-8 -*-
"""제안서 — 결정을 요청하는 문서.

리포트와 다른 문서다. 읽는 사람이 다르다.

    리포트    같은 분석을 하는 사람이 읽는다. 계산 과정이 들어간다
    제안서    결정 권한을 가진 사람이 읽는다. 계산 과정을 넣지 않는다

읽고 나서 **승인 / 조건부 승인 / 보류** 중 하나가 나와야 한다.
읽고 "잘 봤다"로 끝나면 실패다.

⚠ **거르는 자리는 조립기(report.proposal.build) 한 곳뿐이다.** 이 화면에서 또 거르지
  않는다 — 두 곳에서 거르면 무엇이 왜 빠졌는지 추적이 안 된다.

절 목록·제목의 원본은 core/config.py (PROPOSAL_SECTIONS · PROPOSAL_WORDS) 다.
"""
import streamlit as st

from core import config as C, load, metrics as M
from report import proposal as P
from viz import ui

st.set_page_config(page_title="제안서", page_icon="📌", layout="wide",
                   initial_sidebar_state="expanded")
ui.css()
ui.sidebar_nav("proposal")

if "run" not in st.session_state:
    st.session_state.run = None
if "proposal_human" not in st.session_state:
    st.session_state.proposal_human = {}
ui.context_bar(st.session_state.run)

t = ui.guard(load.load_all)
if t is None:
    st.stop()

st.markdown('<div style="font-size:24px;font-weight:800;margin-bottom:4px">'
            '제안서</div>', unsafe_allow_html=True)
st.caption("읽고 나서 승인 · 조건부 승인 · 보류 중 하나가 나와야 합니다.")

topics = ui.guard(M.proposal_topics, t) or []
cards = P.parse_cards()

# ── ① 주제 고르기 ────────────────────────────────────────────────
#   기각된 후보를 목록에서 지우지 않는다 — 지우면 "안 봤다"와 "보고 아니었다"가
#   구분되지 않는다. 사유가 둘이라 라벨도 둘이다.
#: 기각 사유가 둘이라 라벨도 둘이다. 하나로 뭉치면 두 가지가 구분되지 않는다.
_REJECT_LABEL = {"미달": "(차이 없음)", "나빠지지": "(나빠지지 않음)"}


def _label(c: dict) -> str:
    size = c.get("규모_연간건수")
    # ⚠ 재지 않은 규모는 "연 —" 이다. 0 으로 쓰면 "작다"로 읽힌다.
    tail = f"연 {size}건" if size is not None else "연 —"
    why = c.get("기각사유") or ""
    for k, v in _REJECT_LABEL.items():
        if k in why:
            tail += "  " + v
            break
    return f"{c['제목']}  ·  {tail}"


ALL = "전체 — 주제를 고르십시오"
opts = [ALL] + [c["키"] for c in topics]
by_key = {c["키"]: c for c in topics}

pick = st.selectbox("주제", opts,
                    format_func=lambda k: ALL if k == ALL else _label(by_key[k]),
                    key="topic_pick")

if pick == ALL:
    # 문서를 만들지 않는다. topic 없이는 근거가 안 나온다 — 고르라고만 한다.
    ui.section("주제 후보", "규모가 큰 순서입니다. 순서가 우선순위를 뜻하지는 않습니다.")
    if not topics:
        ui.callout("주제 후보가 없습니다. 지표·축·임계값·추세 넷 어디에서도 "
                   "후보가 나오지 않았습니다.")
    st.dataframe(
        [{"갈래": c["갈래"], "제목": c["제목"],
          "규모(연 건)": c["규모_연간건수"] if c["규모_연간건수"] is not None else None,
          "격차(%p)": c["격차_%p"], "기각 사유": c["기각사유"] or ""}
         for c in topics],
        width="stretch", hide_index=True)
    st.caption("기각된 후보도 지우지 않고 남깁니다 — "
               "「안 봤다」와 「보고 아니었다」는 다릅니다.")
    st.stop()

topic = by_key[pick]
ev = ui.guard(M.topic_evidence, t, topic)
if ev is None:
    st.stop()
secs = P.build(topic, ev, cards, st.session_state.proposal_human)

# ── ② 근거 요약 한 줄 ────────────────────────────────────────────
st.divider()
st.markdown(f'<div style="font-size:19px;font-weight:700;margin-bottom:2px">'
            f'{topic["제목"]}</div>', unsafe_allow_html=True)
st.caption(topic["한줄"])
if topic.get("기각사유"):
    ui.callout(f"이 주제는 <b>{C.words('판정어', '기각')}</b> 후보입니다 — "
               f"{topic['기각사유']}. "
               f"문서는 만들되 그 사실이 함께 나갑니다.")

# ── ③ 절별 미리보기 ──────────────────────────────────────────────
st.divider()
n_auto = sum(1 for s in secs if s["kind"] == "auto")
n_human = sum(1 for s in secs if s["kind"] == "human")
ui.section("절", f"{len(secs)}개 · 자동 {n_auto} · 사람 {n_human}")
st.caption("주제에 따라 절 수가 달라집니다. 근거가 없는 절은 만들지 않습니다 — "
           "빈 절을 두면 그 자리가 그대로 인쇄됩니다.")

for sec in secs:
    kind_ko = {"auto": "자동 생성", "human": "사람 작성"}[sec["kind"]]
    lvl = "ok" if (sec["kind"] == "auto" or sec["문장"]) else "warn"
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:12px;'
        f'margin:18px 0 2px">'
        f'<div style="font-size:17px;font-weight:700">{sec["제목"]}</div>'
        f'{ui.badge(lvl, kind_ko)}</div>', unsafe_allow_html=True)
    st.caption(sec["질문"])

    if sec["kind"] == "auto":
        if sec["문장"]:
            st.markdown(
                '<div class="card"><div style="font-size:14px;line-height:1.75">'
                + "".join(f"<div>{x}</div>" for x in sec["문장"])
                + "</div></div>", unsafe_allow_html=True)
        if sec.get("문장검사"):
            ui.callout("자동 생성 문장에 인과를 단정하는 표현이 있습니다: "
                       f"<b>{', '.join(sec['문장검사'])}</b>.")
        for svg in sec["차트"]:
            st.markdown(svg, unsafe_allow_html=True)
    else:
        st.caption(sec.get("placeholder", ""))
        txt = st.text_area("본문", value=(sec["문장"][0] if sec["문장"] else ""),
                           height=150, key=f"h3_{sec['키']}",
                           label_visibility="collapsed")
        # ⚠ 사람이 쓴 문장에는 조립을 막는 검사를 걸지 않는다.
        #   사람 문장 때문에 문서가 안 나오면 안 된다 (Day3 프롬프트 10).
        if sec["키"] == "요청" and txt.strip() and not P.has_decide_verb(txt):
            ui.callout("요청 문장에 <b>결정을 요구하는 동사</b>가 없습니다 — "
                       "승인 · 결정 · 판단 중 하나가 들어가야 합니다. "
                       "저장은 됩니다.")
        if st.button("저장", type="primary", key=f"b3_{sec['키']}"):
            st.session_state.proposal_human[sec["키"]] = txt
            st.rerun()

        # 요청 절 — 아래 셋은 자동이다. 사람이 쓴 문장과 나눠서 보여준다.
        if sec["키"] == "요청":
            opts = sec.get("선택지") or []
            if opts:
                st.markdown("**결정 선택지**")
                st.table([{"결정": o["선택"], "무엇이 따라오나": o["따라오는 것"]}
                          for o in opts])
            if sec.get("미룰때"):
                st.caption(sec["미룰때"])
            uk = sec.get("확인필요") or []
            if uk:
                with st.expander(f"{C.words('확인필요', '미확인')} {len(uk)}건"):
                    st.table([{"무엇을 모르는가": u["무엇"],
                               "누가 확인하는가": u["누가"],
                               "모르는 채로 할 수 있는 결정": u["모르는채로"]}
                              for u in uk])

# ── ④ 내보내기 ───────────────────────────────────────────────────
st.divider()
ui.section("내보내기")
c1, c2 = st.columns(2)
with c1:
    st.markdown("**HTML** — 파일 하나로 열립니다")
    st.download_button("제안서.html 내려받기",
                       P.to_html(secs, topic).encode("utf-8"),
                       file_name="제안서.html", mime="text/html",
                       key="dl3_html")
with c2:
    st.markdown("**PDF** — 표지 · 절별 · 그림은 HTML 본에만")
    left = P.missing_glyphs(secs)
    if left:
        ui.callout("PDF 폰트에 없는 글자가 남아 있습니다: "
                   f"<b>{', '.join(left)}</b>. 인쇄본에서 사라집니다.")
    if st.button("PDF 만들기", type="primary", key="pdf3_btn"):
        with st.spinner("제안서 PDF를 조립하는 중..."):
            st.session_state.proposal_pdf = P.build_pdf(secs, topic)
        st.success(f"생성 완료 · {len(st.session_state.proposal_pdf)/1024:.0f}KB")
    if st.session_state.get("proposal_pdf"):
        st.download_button("PDF 내려받기", st.session_state.proposal_pdf,
                           file_name="제안서.pdf", mime="application/pdf",
                           key="dl3_pdf")
