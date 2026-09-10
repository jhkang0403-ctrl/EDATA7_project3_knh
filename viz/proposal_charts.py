# -*- coding: utf-8 -*-
"""제안서에 들어갈 그림만 만든다. **인라인 SVG 문자열**을 돌려준다.

────────────────────────────────────────────────────────────────────
그림 하나에는 **그 그림이 증명하는 문장 하나**가 본문에 있어야 한다.
문장이 없는 그림은 장식이다. (Day3 판단 기준 3)

    절     본문의 주장                    그림
    현황   "여기서 가장 많이 걸러진다"      단계별 막대 — 병목 하나만 강조색
    원인   "이 집단과 저 집단이 다르다"     축별 가로 막대 — 최고·최저만 색
    규모   "이렇게 움직이고 있다"           연도별 꺾은선 — 임계선은 점선
────────────────────────────────────────────────────────────────────

이 파일이 지키는 것:

    1. 좌표를 **실제 값에서** 계산한다. 예시 숫자를 남기지 않는다
    2. **값이 없는 계열은 아예 그리지 않는다.** 0으로 그리지 않는다 —
       0은 "작다"로 읽히는데 실제로는 "못 믿어서 계산하지 않았다"다
    3. 색은 셋까지 — 강조 1 · 기본 1 · 회색 1
    4. 축 눈금과 값 라벨을 반드시 넣는다. 라벨 없는 막대는 못 읽는다
    5. **외부 CDN·이미지·폰트 링크를 쓰지 않는다.** 문자열 하나로 끝난다
    6. 그림 아래 caption 에 **무엇을 하나로 셌는지**를 한 줄 적는다
       ⚠ "그레인" 같은 분석 용어를 쓰지 않는다 — 팀 밖 사람이 모르는 말이다

⚠ viz/charts.py · viz/pdf_charts.py 는 건드리지 않는다. 저건 화면과 리포트 것이고
  이건 제안서 것이다. 쓰는 곳이 다르면 파일을 나눈다.
"""
from __future__ import annotations

import html as _html

from core import config as C

# ── 색 셋 ─────────────────────────────────────────────────────────
# ⚠ config.COLORS 는 상태 색 넷(ok/warn/block/none)이고 의미가 고정이다.
#   그림에는 그중 둘(강조·회색)만 쓰고, 기본색은 BRAND 에서 가져온다.
#   **셋을 넘기지 않는다.** 넷째 색이 생기면 강조가 강조가 아니게 된다.
ACCENT = C.COLORS["block"]      # 강조 — 병목 / 낮은 쪽 칸
BASE = C.BRAND["primary"]       # 기본 — 나머지 계열
GREY = C.COLORS["none"]         # 회색 — 비교에서 빠진 칸
INK = C.BRAND["ink"]
MUTED = C.BRAND["muted"]
LINE = C.BRAND["line"]

_FONT = ("font-family=\"'Malgun Gothic','Apple SD Gothic Neo',"
         "system-ui,sans-serif\"")


def _e(s) -> str:
    return _html.escape(str(s), quote=True)


def _txt(x, y, s, size=11.5, fill=MUTED, anchor="start", weight="400") -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" {_FONT} font-size="{size}" '
            f'fill="{fill}" text-anchor="{anchor}" font-weight="{weight}">'
            f"{_e(s)}</text>")


def _wrap(w: int, h: int, body: str, caption: str) -> str:
    """캡션까지 포함해 **문자열 하나**로 닫는다. 외부 자원을 쓰지 않는다."""
    cap_y = h - 6
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" '
            f'role="img" xmlns="http://www.w3.org/2000/svg">'
            f"{body}"
            f"{_txt(0, cap_y, caption, 10.5, MUTED)}"
            f"</svg>")


# ── 1) 현황 — 단계별 도달 막대 ────────────────────────────────────
def funnel_svg(현황: dict) -> str | None:
    """단계별 도달 막대. **병목 구간 하나만** 강조색.

    현황 = topic_evidence(...)["현황"]

    ⚠ 값이 없으면 None 을 돌려준다. 빈 그림을 그리지 않는다 —
      부르는 쪽이 "그림이 없다"를 알아야 한다.
    """
    steps = (현황 or {}).get("단계") or []
    steps = [s for s in steps if s.get("도달") is not None]
    if len(steps) < 2:
        return None

    top = max(s["도달"] for s in steps)
    if not top:
        return None

    lb_w, bar_w, row_h, pad_t = 92, 400, 30, 14
    val_x = lb_w + bar_w + 12
    w, h = val_x + 190, pad_t + row_h * len(steps) + 30

    body = []
    # 축 눈금 — 0 과 최댓값
    for frac in (0.0, 0.5, 1.0):
        gx = lb_w + bar_w * frac
        body.append(f'<line x1="{gx:.1f}" y1="{pad_t - 6}" x2="{gx:.1f}" '
                    f'y2="{pad_t + row_h * len(steps) - 8}" '
                    f'stroke="{LINE}" stroke-width="1"/>')
        body.append(_txt(gx, pad_t - 10, f"{int(top * frac):,}", 10, MUTED, "middle"))

    for i, s in enumerate(steps):
        y = pad_t + row_h * i
        bw = bar_w * (s["도달"] / top)
        fill = ACCENT if s.get("병목") else BASE
        body.append(_txt(lb_w - 8, y + 15, s["단계"], 11.5, INK, "end", "600"))
        body.append(f'<rect x="{lb_w}" y="{y + 4}" width="{bw:.1f}" height="17" '
                    f'rx="3" fill="{fill}"/>')
        val = f"{s['도달']:,}건"
        if s.get("전환율") is not None:
            val += f"  전 단계의 {s['전환율']}%"
        if s.get("병목"):
            val += "  ← 병목"
        body.append(_txt(val_x, y + 17, val, 11.5,
                         ACCENT if s.get("병목") else INK, "start",
                         "700" if s.get("병목") else "400"))

    return _wrap(w, h, "".join(body),
                 "1건 = 과제번호 1개로 셌습니다 (중복 없이). 실제 심사 기록")


# ── 2) 원인 — 축별 전환율 가로 막대 ───────────────────────────────
def gap_svg(축: dict) -> str | None:
    """한 축의 칸별 전환율 가로 막대. **최고·최저만 색, 나머지는 회색.**

    축 = topic_evidence(...)["원인"]["축"] 의 원소 하나

    ⚠ **못 믿어 감춘 칸(전환율이 None)은 아예 그리지 않는다.** 0으로도 그리지 않는다 —
      0으로 그리면 "전환율 0%"로 읽힌다. 대신 몇 칸을 뺐는지 캡션에 적는다.
    """
    cells = (축 or {}).get("칸") or []
    drawn = [c for c in cells if c.get("전환율") is not None]
    hidden = [c for c in cells if c.get("전환율") is None]
    if len(drawn) < 2:
        return None

    top = max(c["전환율"] for c in drawn)
    if not top:
        return None

    lb_w, bar_w, row_h, pad_t = 92, 360, 30, 14
    val_x = lb_w + bar_w + 12
    w, h = val_x + 210, pad_t + row_h * len(drawn) + 30

    body = []
    for frac in (0.0, 0.5, 1.0):
        gx = lb_w + bar_w * frac
        body.append(f'<line x1="{gx:.1f}" y1="{pad_t - 6}" x2="{gx:.1f}" '
                    f'y2="{pad_t + row_h * len(drawn) - 8}" '
                    f'stroke="{LINE}" stroke-width="1"/>')
        body.append(_txt(gx, pad_t - 10, f"{top * frac:.0f}%", 10, MUTED, "middle"))

    # 낮은 쪽이 강조다 — 손을 쓸 수 있는 쪽이라서.
    for i, c in enumerate(sorted(drawn, key=lambda x: -x["전환율"])):
        y = pad_t + row_h * i
        bw = bar_w * (c["전환율"] / top)
        fill = ACCENT if c.get("최저") else (BASE if c.get("최고") else GREY)
        body.append(_txt(lb_w - 8, y + 15, c["칸"], 11.5, INK, "end", "600"))
        body.append(f'<rect x="{lb_w}" y="{y + 4}" width="{bw:.1f}" height="17" '
                    f'rx="3" fill="{fill}"/>')
        val = (f"{c['전환율']}%  ({c['전환']:,}/{c['도달']:,})"
               f"  비중 {c['비중']}%")
        body.append(_txt(val_x, y + 17, val, 11.5,
                         ACCENT if c.get("최저") else INK, "start",
                         "700" if c.get("최저") else "400"))

    cap = "1건 = 과제번호 1개로 셌습니다 (중복 없이). 실제 심사 기록"
    seg = 축.get("구간")
    if seg:
        cap += f" · 구간 {seg[0]} -> {seg[1]}"
    if hidden:
        cap += f" · 못 믿어 뺀 칸 {len(hidden)}개 (" + ", ".join(
            f"{c['칸']} {c.get('사유', '')}" for c in hidden) + ")"
    return _wrap(w, h, "".join(body), cap)


# ── 3) 추세 — 연도별 꺾은선 ───────────────────────────────────────
def trend_svg(추세: dict, thresholds: dict | None = None) -> str | None:
    """**연도별** 꺾은선. 임계선이 있으면 점선으로.

    추세 = topic_evidence(...)["추세"]

    ⚠ 이 도메인엔 "최근 12개월"이 없다. monthly() 가 종결연도별이고
      월로 자르면 표본이 없다. **연 단위라는 것을 축 라벨에 적는다.**
    ⚠ 마지막 해는 반쪽이다. **빼지 않고 그리되 속 빈 점 + 점선**으로 구분한다 —
      채운 점과 같게 그리면 "역대 최고"로 읽힌다.
    """
    rows = (추세 or {}).get("연도별") or []
    rows = [r for r in rows if r.get("값") is not None]
    if len(rows) < 2:
        return None

    name = 추세.get("지표", "")
    th = (thresholds or C.THRESHOLDS).get(name) or {}
    marks = [(k, float(v)) for k, v in th.items()
             if k in ("경고", "위험") and isinstance(v, (int, float))]

    vals = [r["값"] for r in rows] + [v for _, v in marks]
    lo, hi = min(vals), max(vals)
    if hi == lo:
        hi = lo + 1
    pad = (hi - lo) * 0.12
    lo, hi = lo - pad, hi + pad

    left, right, top_y, plot_h = 46, 74, 16, 132
    plot_w = 560
    w, h = left + plot_w + right, top_y + plot_h + 52

    def X(i):
        return left + plot_w * (i / max(len(rows) - 1, 1))

    def Y(v):
        return top_y + plot_h * (1 - (v - lo) / (hi - lo))

    body = []
    # y 눈금 3개
    for frac in (0.0, 0.5, 1.0):
        v = lo + (hi - lo) * frac
        y = Y(v)
        body.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" '
                    f'y2="{y:.1f}" stroke="{LINE}" stroke-width="1"/>')
        body.append(_txt(left - 8, y + 3.5, f"{v:.0f}", 10, MUTED, "end"))

    # 임계선 — 점선
    for label, v in marks:
        if not (lo <= v <= hi):
            continue
        y = Y(v)
        body.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" '
                    f'y2="{y:.1f}" stroke="{ACCENT}" stroke-width="1.2" '
                    f'stroke-dasharray="5 4" opacity="0.75"/>')
        body.append(_txt(left + plot_w + 6, y + 3.5, f"{label} {v:g}", 10,
                         ACCENT, "start", "700"))

    # 완결된 구간은 실선, 반쪽 해로 가는 마지막 구간은 점선
    for i in range(len(rows) - 1):
        a, b = rows[i], rows[i + 1]
        dash = ' stroke-dasharray="4 4"' if b.get("반쪽") else ""
        body.append(f'<line x1="{X(i):.1f}" y1="{Y(a["값"]):.1f}" '
                    f'x2="{X(i + 1):.1f}" y2="{Y(b["값"]):.1f}" '
                    f'stroke="{BASE}" stroke-width="2"{dash}/>')

    for i, r in enumerate(rows):
        x, y = X(i), Y(r["값"])
        half = bool(r.get("반쪽"))
        if half:                                   # 속 빈 점 — 아직 안 찬 해
            body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#fff" '
                        f'stroke="{ACCENT}" stroke-width="2"/>')
        else:
            body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{BASE}"/>')
        # 값 라벨은 처음·끝·반쪽만 (다 붙이면 겹친다)
        if i in (0, len(rows) - 1) or half:
            body.append(_txt(x, y - 9, f"{r['값']:g}", 10.5,
                             ACCENT if half else INK, "middle", "700"))
        # x 눈금 — 처음·끝·반쪽만
        if i in (0, len(rows) - 1) or half:
            body.append(_txt(x, top_y + plot_h + 16,
                             r["연도"] + ("(반쪽)" if half else ""),
                             10, ACCENT if half else MUTED, "middle"))

    cap = (f"{name} · 종결연도별(연 단위, 월 아님) · 실측 · "
           f"{rows[0]['연도']}~{rows[-1]['연도']}")
    if any(r.get("반쪽") for r in rows):
        cap += " · 속 빈 점과 점선은 아직 안 찬 해 — 비교에 쓰지 않음"
    if marks:
        cap += " · 점선은 임계선"
    return _wrap(w, h, "".join(body), cap)
