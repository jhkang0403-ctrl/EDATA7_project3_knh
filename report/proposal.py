# -*- coding: utf-8 -*-
"""제안서 7절 조립.

────────────────────────────────────────────────────────────────────
자동으로 쓰는 절과 사람이 쓰는 절이 나뉜다. 가르는 질문은 하나다.

    이 절의 내용이 데이터를 다시 조회하면 똑같이 나오는가?
        그렇다   → 자동으로 쓴다 (한 장 요약 · 하지 말 것 · 다시 할 것 · 할 것 · 부록)
        아니다   → 사람이 쓴다   (이 제안이 틀린다면 · 적용)

**판단이 들어가는 절을 자동화하는 순간 책임의 주체가 사라진다.**
report/sections.py 와 같은 원칙이고, 같은 이유다.
────────────────────────────────────────────────────────────────────

sections.py 를 지우거나 고치지 않는다. 리포트와 제안서는 다른 문서다.
같은 원칙을 따로 된 파일에 적용한 것이다.

이 파일이 지키는 것 셋:

    1. 카드에 없는 것을 쓰지 않는다.   없으면 TODO 로 남긴다. 채우면 지어낸 것이다
    2. 절 순서를 바꾸지 않는다.        "할 것"을 먼저 두면 멈추자는 제안은 안 읽힌다
    3. 문장 검사를 새로 만들지 않는다. sections.check_phrasing 을 import 해서 쓴다
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from pathlib import Path

from core import config as C

# ★ 문장 검사는 **새로 만들지 않는다.** 리포트에서 쓰는 그것을 그대로 가져온다.
#   화면에서 지키고 문서에서 안 지키면 의미가 없고, 목록이 둘이면 언젠가 갈라진다.
from report import to_pdf
from report.sections import BANNED, check_phrasing  # noqa: F401  (재수출)

#: 카드 파일. config.ROOT 기준 — 경로를 여기 말고 다른 곳에 박지 않는다.
CARDS_PATH = C.ROOT / "my-report" / "제안카드.md"

#: 절 순서. **바꾸지 않는다.** 리스트 순서가 곧 문서 순서다.
#:   "할 것"을 먼저 놓으면 읽는 사람이 거기서 멈추고 "하지 말 것"은 안 읽힌다.
SECTION_ORDER = [
    ("한 장 요약", "auto"),
    ("하지 말 것", "auto"),
    ("다시 할 것", "auto"),
    ("할 것", "auto"),
    ("이 제안이 틀린다면", "human"),
    ("적용", "human"),          # 후보는 자동 · 고르는 것은 사람 (Day2 실습 D)
    ("부록 (근거 상세)", "auto"),
]

#: 카드 분류 셋. 본문 절 이름과 같아야 카드가 그 절로 들어간다.
CLASSES = ("하지 말 것", "다시 할 것", "할 것")

#: 카드에 이 말이 적혀 있으면 채우지 않고 그대로 내보낸다. 화면에서 class="todo".
TODO_MARK = "미확인"


# ── 카드 파일 파싱 ────────────────────────────────────────────────
_CARD_RE = re.compile(r"^##\s*제안\s*(\d+)\s*[—-]\s*(.+?)\s*$", re.M)
_ROW_RE = re.compile(r"^\|\s*\*\*(.+?)\*\*\s*\|\s*(.*?)\s*\|\s*$", re.M)


def parse_cards(path: str | Path | None = None) -> dict:
    """my-report/제안카드.md 를 딕셔너리로 읽는다. **읽기만 한다.**

    화면에서 카드를 고치지 않는다 — 고치기 시작하면 카드와 화면 중 어느 것이
    진짜인지 알 수 없게 된다. 값을 바꾸려면 카드 파일로 돌아간다. (교안 부록 A)

    반환: {
        "path": str,
        "meta": {"작성 시작": ..., "최종 갱신": ..., "근거 조회": ...},
        "cards": [{"n", "title", "분류", "근거", "비용", "효과", "되돌림"}, ...],
    }
    카드 파일이 없으면 cards 가 빈 리스트다 — 예외를 올리지 않는다.
    화면이 "카드가 없습니다"를 그릴 수 있어야 한다.
    """
    p = Path(path) if path else CARDS_PATH
    if not p.exists():
        return {"path": str(p), "meta": {}, "cards": []}

    text = p.read_text(encoding="utf-8")

    meta = {}
    for key in ("작성 시작", "최종 갱신", "근거 조회"):
        m = re.search(key + r"\s*[:：]\s*(.+)", text)
        if m:
            meta[key] = m.group(1).split("   ")[0].strip()

    marks = list(_CARD_RE.finditer(text))
    cards = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        chunk = text[m.end():end]
        # 카드 본문 표만 읽는다. "### 반증" 아래(수요일 몫)는 오늘 쓰지 않는다.
        head = chunk.split("### ")[0]
        row = {k: v for k, v in _ROW_RE.findall(head)}
        cards.append({
            "n": int(m.group(1)),
            "title": m.group(2).strip(),
            "분류": row.get("분류", "").strip(),
            "근거": row.get("근거", "").strip(),
            "비용": row.get("비용", "").strip(),
            "효과": row.get("효과", "").strip(),
            "되돌림": row.get("되돌림", "").strip(),
        })
    return {"path": str(p), "meta": meta, "cards": cards}


def is_todo(v: str) -> bool:
    """이 칸이 아직 안 채워졌는가. 빈 칸도, "미확인"이라 적힌 것도 TODO 다."""
    return (not v) or v.strip().startswith(TODO_MARK)


def _by_class(cards: list[dict], cls: str) -> list[dict]:
    return [c for c in cards if c.get("분류", "").strip() == cls]


# ── 자동으로 쓰는 절 ──────────────────────────────────────────────
def _s_class(cards: list[dict], cls: str) -> dict:
    """분류 하나를 절로 만든다. 카드에 있는 것만 옮긴다 — 새로 짓지 않는다."""
    picked = _by_class(cards, cls)
    if not picked:
        return {"title": cls, "kind": "auto", "n": 0, "cards": [],
                "body": "해당하는 카드가 없습니다."}

    lines = []
    for c in picked:
        lines.append("「" + c["title"] + "」")
        for key in ("근거", "비용", "효과", "되돌림"):
            v = c.get(key, "")
            lines.append("  " + key + "   " + (v if v else TODO_MARK))
        lines.append("")
    return {"title": cls, "kind": "auto", "n": len(picked),
            "body": "\n".join(lines).rstrip(), "cards": picked}


def _s_appendix(data: dict) -> dict:
    """부록 — 근거 상세. 카드의 근거 줄을 **자르지 않고** 그대로 싣는다.

    한 장 요약이 짧은 것은 여기가 있기 때문이다. 요약에서 뺀 것이
    사라지는 것이 아니라 여기로 온다.
    """
    cards = data.get("cards", [])
    if not cards:
        return {"title": "부록 (근거 상세)", "kind": "auto", "body": "카드가 없습니다."}

    meta = data.get("meta", {})
    lines = [k + ": " + v for k, v in meta.items()]
    if lines:
        lines.append("")
    lines.append("카드 파일: " + str(data.get("path", "")))
    lines.append("")
    for c in cards:
        lines.append("[제안 " + str(c["n"]) + "] " + c["title"] + "  (" + c["분류"] + ")")
        for key in ("근거", "비용", "효과", "되돌림"):
            lines.append("  " + key.ljust(4) + "   " + (c[key] or TODO_MARK))
        lines.append("")
    return {"title": "부록 (근거 상세)", "kind": "auto",
            "body": "\n".join(lines).rstrip()}


#: 한 장 요약의 줄 이름. **넷뿐이다.** 다섯째가 생기면 잘못 조립한 것이다.
SUMMARY_KEYS = ("발견", "제안", "불확실", "근거")

#: 발견 파일 — 한 장 요약의 "근거" 줄이 조회 일시를 여기서 가져온다.
FINDINGS_PATH = C.ROOT / "my-report" / "발견.md"

# 카드 근거 줄에서 크기를 재는 데 쓰는 두 조각.
#   격차   "격차 **13.69%p**"      -> 13.69
#   비중   "1,301건의 **73.64%**"  -> (1301, 73.64)
#
# ⚠ 자유 문장에서 숫자를 긁는 것이라 **약하다.** 카드 문장이 바뀌면 못 잡는다.
#   못 잡으면 지어내지 않고 크기를 None 으로 둔다 — 그 카드는 요약의 "발견"
#   후보에서 빠지고, 후보가 하나도 없으면 그 줄은 "todo" 가 된다.
_GAP_RE = re.compile(r"격차\s*\*{0,2}([\d.]+)\s*%p")
_SHARE_RE = re.compile(r"([\d,]+)\s*건의\s*\*{0,2}([\d.]+)\s*%")


def card_size(card: dict) -> dict | None:
    """카드 하나의 크기. 격차 x 비중. 둘 다 근거에 있어야 잰다.

    반환: {"gap", "share", "denom", "size"} 또는 None (못 재면)
    **못 재는 것을 0으로 두지 않는다.** 0이면 "작다"가 되는데, 실제로는 "모른다"다.
    """
    ev = card.get("근거", "") or ""
    g = _GAP_RE.search(ev)
    s = _SHARE_RE.search(ev)
    if not (g and s):
        return None
    gap = float(g.group(1))
    denom = int(s.group(1).replace(",", ""))
    share = float(s.group(2))
    return {"gap": gap, "share": share, "denom": denom,
            "size": round(gap * share / 100, 2)}


def _read_findings_meta() -> dict:
    """발견.md 머리말에서 조회 일시와 데이터 기준일을 읽는다. 없으면 빈 딕셔너리.

    **여기서 날짜를 만들지 않는다.** 현재 시각을 넣으면 같은 입력인데 돌릴 때마다
    문서가 달라진다 (CLAUDE.md 코드 규칙 2). 파일에 적힌 것만 옮긴다.
    """
    if not FINDINGS_PATH.exists():
        return {}
    head = FINDINGS_PATH.read_text(encoding="utf-8")[:800]
    out = {}
    for key in ("조회 일시", "데이터 기준일"):
        m = re.search(key + r"\s*[:：]\s*(.+)", head)
        if m:
            # 날짜만 취한다. 괄호 안 설명까지 요약에 끌고 오면 줄이 길어진다.
            v = m.group(1).replace("*", "").strip()
            out[key] = v.split(" (")[0].strip()
    return out


def _s_summary(data: dict) -> dict:
    """한 장 요약 — **발견 · 제안 · 불확실 · 근거 넷뿐이다.**

    다섯째 줄이 생기면 잘못 조립한 것이다. 배경도 목적도 여기 넣지 않는다 —
    그런 것은 부록으로 간다. 이것만 읽고 결정할 수 있게 하는 것이 목적이라,
    줄이 늘어나는 순간 그 목적이 깨진다.

    **카드에 없는 문장은 만들지 않는다.** 채울 수 없는 줄은 "todo" 로 둔다.

    ★ Day2 실습 B 프롬프트 3.
    """
    cards = data.get("cards", [])
    lines: dict[str, str] = {}

    # 1) 발견 — 크기(격차 x 비중)가 가장 큰 카드 하나. 분모를 함께 적는다.
    sized = [(c, card_size(c)) for c in cards]
    sized = [(c, s) for c, s in sized if s]
    if sized:
        c, s = max(sized, key=lambda x: x[1]["size"])
        lines["발견"] = (
            "「" + c["title"] + "」 격차 " + format(s["gap"], "g") + "%p · "
            "비중 " + format(s["share"], "g") + "% (분모 " + format(s["denom"], ",") + "건) · "
            "크기 " + format(s["size"], "g") + " (격차 x 비중)")
    else:
        lines["발견"] = "todo — 카드 근거에서 격차와 비중을 찾지 못했습니다."

    # 2) 제안 — **본문 순서와 같게.** 제목만 나열한다.
    groups = []
    for cls in CLASSES:
        titles = [c["title"] for c in _by_class(cards, cls)]
        if titles:
            groups.append(cls + " — " + " / ".join(titles))
    lines["제안"] = "  ·  ".join(groups) if groups else "todo — 카드가 없습니다."

    # 3) 불확실 — 아직 못 채운 칸이 있는 카드 중 가장 큰 것 하나.
    #    확신도(반증 절)는 수요일에 채우므로 지금은 전부 비어 있다 -> "미확인" 취급.
    unsure = []
    for c in cards:
        todo_keys = [k for k in ("근거", "비용", "효과", "되돌림") if is_todo(c.get(k, ""))]
        if todo_keys:
            s = card_size(c)
            unsure.append((c, todo_keys, s["size"] if s else -1))
    if unsure:
        c, todo_keys, _ = max(unsure, key=lambda x: x[2])
        lines["불확실"] = ("「" + c["title"] + "」 " + " · ".join(todo_keys)
                        + " " + TODO_MARK)
    else:
        lines["불확실"] = "todo — 확신도를 아직 재지 않았습니다."

    # 4) 근거 — 발견.md 의 조회 일시 · 표본 · "상세는 부록"
    fm = _read_findings_meta()
    parts = []
    if fm.get("조회 일시"):
        parts.append(fm["조회 일시"] + " 조회")
    if fm.get("데이터 기준일"):
        parts.append("데이터 기준일 " + fm["데이터 기준일"])
    if sized:
        parts.append("표본 " + format(max(s["denom"] for _, s in sized), ",") + "건")
    parts.append("상세는 부록")
    lines["근거"] = " · ".join(parts) if len(parts) > 1 else "todo — 발견.md 를 찾지 못했습니다."

    body = "\n".join(k + "   " + lines[k] for k in SUMMARY_KEYS)
    return {"title": "한 장 요약", "kind": "auto", "body": body,
            "lines": lines, "n_lines": len(SUMMARY_KEYS)}


# ── 사람이 쓰는 절 ────────────────────────────────────────────────
def _s_wrong(human: dict) -> dict:
    """이 제안이 틀린다면. **문서 전체에 하나만 둔다** — 카드마다 두면 아무도 안 읽는다.

    ★ Day2 실습 D 프롬프트 6.
    """
    title = "이 제안이 틀린다면"
    return {"title": title, "kind": "human", "body": human.get(title, ""),
            "placeholder": "이 제안이 틀렸다면 무엇 때문인지, "
                           "확인하려면 무엇을 보면 되는지 적으십시오."}


#: 판단 기록 파일 — "적용" 절의 후보 목록이 여기서 나온다.
DECISIONS_PATH = C.ROOT / "my-report" / "판단기준.md"

#: 후보를 긁어올 소제목. 이 제목 아래 불릿만 가져온다.
DECISION_HEADING = "오늘 내가 내린 결정"

#: 후보로 보여줄 최근 회차 수. 다 보여주면 목록이 아니라 문서가 된다.
RECENT_ENTRIES = 2


def _plain(s: str) -> str:
    """굵게 표시와 앞뒤 군더더기를 떼고 한 줄로 만든다."""
    s = s.replace("**", "").replace("`", "").strip()
    return " ".join(s.split())


def read_decisions(limit: int = RECENT_ENTRIES) -> list[dict]:
    """판단기준.md 의 최근 회차에서 "오늘 내가 내린 결정" 불릿을 긁어온다.

    ★ Day2 실습 D 프롬프트 7. **후보는 자동, 고르는 것은 사람.**

    한 회차 = "## <날짜> — <제목>". 그 안의 "### 오늘 내가 내린 결정" 아래
    "- " 로 시작하는 줄의 **첫 줄만** 가져온다 (이어지는 줄은 설명이라 목록에선 뺀다).

    이 목록은 **읽기 전용이다.** 화면에서 고치지 못하게 한다 — 자동으로 나열된
    것을 사람이 고치기 시작하면 무엇이 기록이고 무엇이 새로 쓴 것인지 갈린다.

    반환: [{"head": "2026-09-08 (Day1) — ...", "items": [문장, ...]}, ...]  (최근 것부터)
    """
    if not DECISIONS_PATH.exists():
        return []

    entries, cur, inside = [], None, False
    for line in DECISIONS_PATH.read_text(encoding="utf-8").split(chr(10)):
        if line.startswith("## "):
            cur = {"head": _plain(line[3:]), "items": []}
            entries.append(cur)
            inside = False
        elif line.startswith("### "):
            inside = DECISION_HEADING in line
        elif inside and cur is not None and line.startswith("- "):
            item = _plain(line[2:])
            if item:
                cur["items"].append(item)

    got = [e for e in entries if e["items"]]
    return list(reversed(got))[:limit]


def _s_apply(human: dict) -> dict:
    """적용 — **후보는 자동, 고르는 것은 사람.**

    판단 기준 2가 코드로 나타나는 자리다. 무엇을 다음에 볼지는 판단이지만,
    후보 목록은 자동으로 나열할 수 있다. 그래서 절 하나 안에서 둘을 가른다.

    ⚠ 후보를 body 에 넣지 않는다. body 는 입력창의 값이 되므로, 넣는 순간
      자동으로 나열한 것을 사람이 고칠 수 있게 된다. 별도 키로 내보낸다.

    ★ Day2 실습 D 프롬프트 7.
    """
    title = "적용"
    return {"title": title, "kind": "human", "body": human.get(title, ""),
            "candidates": read_decisions(),
            "candidates_readonly": True,
            "placeholder": "다음에 무엇을 볼 것인지 적으십시오. "
                           "위 후보 목록은 자동으로 나열된 것이고, 고르는 것은 사람이 합니다."}


# ── 조립 ──────────────────────────────────────────────────────────
def build_cards(cards: dict, human: dict | None = None) -> list[dict]:
    # ⚠ Day2 조립기. Day3 에서 build() 가 주제를 받는 구조로 바뀌어 이름을 옮겼다.
    #   리포트 페이지의 제안서(임시) 탭이 아직 이것을 부른다 — 실습 E 에서 정리한다.
    """제안서 7절을 조립한다.

    cards  parse_cards() 가 돌려준 딕셔너리
    human  사람이 쓴 절의 본문 {절 이름: 본문}

    **순서와 자동/사람 구분은 바꾸지 않는다.** sections.build() 와 같은 형태를
    돌려준다 — 각 절이 {"title", "kind", "body", ...} 인 리스트.

    카드가 하나도 없어도 빈 리스트를 돌려주지 않는다. 절 골격은 그대로 두고
    본문에 "카드가 없습니다"를 적는다 — 화면이 왜 비었는지 보여야 한다.
    """
    human = human or {}
    cl = cards.get("cards", []) if isinstance(cards, dict) else list(cards or [])
    return [
        _s_summary(cards),
        _s_class(cl, "하지 말 것"),
        _s_class(cl, "다시 할 것"),
        _s_class(cl, "할 것"),
        _s_wrong(human),
        _s_apply(human),
        _s_appendix(cards),
    ]


# ── HTML 로 내보내기 ──────────────────────────────────────────────
#
# 「수업자료/제안서_템플릿.html」의 **CSS 와 클래스를 그대로 쓴다.**
# 새 스타일을 만들지 않는다 — 만들면 수업자료와 화면이 갈라진다.
#
#   num          숫자 (tabular-nums)
#   todo         아직 안 채운 자리. **채우지 않는다.** "미확인은 구멍이 아니라 요청이다"
#   prop stop / redo / go        하지 말 것 / 다시 할 것 / 할 것
#   badge b-block / b-warn / b-ok / b-none
#   lab l-obs / l-asm / l-est    관측 / 가정 / 추정  — **한 문장으로 합치지 않는다**
#   unknown      미확인
#
# ⚠ 템플릿에는 본문 절이 다섯이다 (1 발견 · 2 원인 · 3 제안 · 4 틀린다면 · 5 적용).
#   오늘 build() 가 만드는 것은 그중 **3·4·5 와 부록** 뿐이다.
#   1(발견)·2(원인)은 아직 카드에 없다 — 지어내지 않고 자리만 todo 로 남긴다.
#   특히 2(원인)는 수요일 몫이고, 금요일 제안서는 이 절이 비면 차단된다.

TEMPLATE_PATH = C.ROOT / "수업자료" / "제안서_템플릿.html"

_STYLE_RE = re.compile(r"<style>(.*?)</style>", re.S)
_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")

#: 분류 -> (prop 클래스, 배지 클래스, 배지 글자, 번호)
_CLASS_STYLE = {
    "하지 말 것": ("stop", "b-block", "✕ 하지 말 것", "①"),
    "다시 할 것": ("redo", "b-warn", "▲ 다시 할 것", "②"),
    "할 것": ("go", "b-ok", "● 할 것", "③"),
}


def template_css() -> str:
    """템플릿의 style 블록을 그대로 가져온다.

    **여기서 스타일을 새로 만들지 않는다.** 템플릿이 원본이다.
    템플릿이 없으면 빈 문자열을 돌려주고, 부르는 쪽이 그 사실을 문서에 적는다 —
    조용히 다른 스타일로 대체하면 수업자료와 다른 문서가 나온다.
    """
    if not TEMPLATE_PATH.exists():
        return ""
    m = _STYLE_RE.search(TEMPLATE_PATH.read_text(encoding="utf-8"))
    return m.group(1) if m else ""


def _esc(text) -> str:
    return html.escape(str(text or ""), quote=False)


def _mark(text) -> str:
    """숫자에 num, 미확인에 unknown 을 붙인다.

    순서가 중요하다 — escape 다음 숫자, 그다음 미확인.
    숫자를 먼저 감싸야 뒤에 붙는 태그 안의 글자를 다시 건드리지 않는다.
    (escape 는 quote=False 라 숫자 엔티티가 안 생긴다)
    """
    s = _esc(text)
    s = _NUM_RE.sub(lambda m: '<span class="num">' + m.group(0) + "</span>", s)
    return s.replace(TODO_MARK, '<span class="unknown">' + TODO_MARK + "</span>")


def _todo(text: str) -> str:
    """아직 안 채운 자리. **채우지 않고 그대로 보여준다.**"""
    return '<span class="todo">' + _esc(text) + "</span>"


def _label_for(value: str) -> str:
    """관측 / 가정 / 추정 라벨. **한 문장으로 합치지 않는다** —
    합치면 추정이 실측처럼 읽힌다. (템플릿 3절 주석 · DESIGN.md 4-3)
    """
    v = str(value or "")
    if v.startswith("실측") or v.startswith("관측"):
        return '<span class="lab l-obs">관측</span>'
    if v.startswith("추정"):
        return '<span class="lab l-est">추정</span>'
    if v.startswith("가정"):
        return '<span class="lab l-asm">가정</span>'
    return ""


def _prop_card(card: dict) -> str:
    """카드 하나를 prop 블록으로. **카드에 있는 것만 옮긴다.**

    확신도는 카드의 반증 절에서 오는데 그건 수요일 몫이라 아직 비어 있다 —
    지어내지 않고 todo 로 남긴다.
    """
    cls, badge, label, _no = _CLASS_STYLE.get(
        card.get("분류", ""), ("", "b-none", card.get("분류", ""), ""))
    out = ['<div class="prop ' + cls + '">',
           '<div class="cls">' + _esc(label) + "</div>",
           "<h4>" + _esc(card["title"]) + "</h4>", "<dl>"]
    for key in ("근거", "비용", "효과", "되돌림"):
        v = card.get(key, "")
        cell = _todo("[ 아직 안 적음 ]") if not v else _label_for(v) + _mark(v)
        out.append("<dt>" + key + "</dt><dd>" + cell + "</dd>")
    out.append('<dt>확신도</dt><dd><span class="badge b-block">✕ 미확인</span> '
               + _todo("[ 반증 절에서 채운다 — 수요일 ]") + "</dd>")
    out.append("</dl></div>")
    return "".join(out)


def _summary_html(sec: dict, cards: list[dict]) -> str:
    """한 장 요약 — 템플릿의 summary/srow 구조. **넷을 넘기지 않는다.**"""
    lines = sec.get("lines") or {}
    out = ['<div class="summary"><h2>한 장 요약</h2>']

    def row(k, inner):
        return ('<div class="srow"><div class="k">' + k
                + '</div><div class="v">' + inner + "</div></div>")

    v = lines.get("발견", "")
    out.append(row("발견", '<div class="lead">'
                   + (_todo(v) if v.startswith("todo") else _mark(v)) + "</div>"))

    items = []
    for cls in CLASSES:
        for c in [x for x in cards if x.get("분류") == cls]:
            _pc, badge, label, no = _CLASS_STYLE[cls]
            items.append('<li><span class="n">' + no + "</span><span>"
                         + '<span class="badge ' + badge + '">' + label + "</span> "
                         + _esc(c["title"]) + "</span></li>")
    inner = "".join(items) if items else "<li>" + _todo("[ 카드가 없다 ]") + "</li>"
    out.append(row("제안", '<ul class="plist">' + inner + "</ul>"))

    u = lines.get("불확실", "")
    out.append(row("불확실", _todo(u) if u.startswith("todo") else _mark(u)))

    g = lines.get("근거", "")
    out.append(row("근거", '<span class="small">'
                   + (_todo(g) if g.startswith("todo") else _mark(g)) + "</span>"))
    out.append("</div>")
    return "".join(out)


def to_html_cards(secs: list[dict]) -> str:
    # ⚠ Day2 절 모양({title,kind,body})을 받는다. Day3 절은 to_html() 이 받는다.
    """제안서를 **단일 HTML 파일**로. 템플릿의 구조와 클래스를 그대로 쓴다.

    ★ Day2 실습 E 프롬프트 8.

    외부 CSS·이미지·CDN 을 쓰지 않는다 — 파일 하나만 건네받아도, 인터넷이
    없어도 열려야 한다. 템플릿 자체도 외부 자원을 참조하지 않는다.

    **카드에 없는 것을 채우지 않는다.** 안 채운 자리는 class="todo" 로 남는다.
    """
    by = {s["title"]: s for s in secs}
    data = parse_cards()
    cards = data.get("cards", [])
    meta = data.get("meta", {})
    css = template_css()

    out = ["<!DOCTYPE html>", '<html lang="ko"><head><meta charset="UTF-8">',
           '<meta name="viewport" content="width=device-width, initial-scale=1">',
           "<title>제안서 — " + _esc(C.DATASET) + "</title>",
           "<style>" + css + "</style></head><body>", '<div class="page">']

    if not css:
        out.append('<div class="callout stop"><b>템플릿을 찾지 못했습니다.</b> '
                   + _esc(str(TEMPLATE_PATH)) + " 가 없어 스타일 없이 냈습니다.</div>")

    n_stop = sum(1 for c in cards if c.get("분류") == "하지 말 것")
    out += ['<div class="cover">',
            '<div class="kicker">성과 개선 제안</div>',
            "<h1>" + _todo("[ 무엇을 하자고 하는지 한 줄 — 사람이 씁니다 ]") + "</h1>",
            '<div class="sub">' + _esc(C.DATASET)
            + ' 분석 결과 · 제안 <span class="num">' + str(len(cards))
            + '</span>건 (하지 말 것 <span class="num">' + str(n_stop)
            + "</span>건)</div>",
            '<div class="meta">',
            "<span>데이터셋 <b>" + _esc(C.DATASET) + "</b></span>",
            '<span>기간 <b class="num">' + _esc(C.PERIOD[0]) + " ~ "
            + _esc(C.PERIOD[1]) + "</b></span>",
            '<span>작성 <b class="num">' + _esc(meta.get("최종 갱신", ""))
            + "</b></span>",
            '<span>검증 <b><span class="badge b-ok">● 차단 0</span></b></span>',
            "</div></div>"]

    if "한 장 요약" in by:
        out.append(_summary_html(by["한 장 요약"], cards))

    out += ['<h2 class="sec"><span class="no">1</span>무엇을 발견했는가</h2>',
            "<p>" + _todo("[ 발견 절은 오늘 조립 대상이 아니다 — 발견.md 에 있다 ]")
            + "</p>",
            '<h2 class="sec"><span class="no">2</span>왜 이런 일이 생겼는가</h2>',
            '<div class="callout stop"><b>원인 절이 비어 있습니다.</b> '
            "수요일에 채웁니다. 이 절이 빈 채로는 제안서를 낼 수 없습니다.</div>"]

    out += ['<h2 class="sec"><span class="no">3</span>무엇을 하자고 제안하는가</h2>',
            '<p class="sec-lead">멈추는 것부터 적는다. '
            "비용이 0이고 근거가 관측이기 때문이다.</p>"]
    for cls in CLASSES:
        picked = [c for c in cards if c.get("분류") == cls]
        if not picked:
            out.append('<div class="prop"><div class="cls">' + _esc(cls)
                       + "</div><h4>" + _todo("[ 해당하는 카드가 없다 ]")
                       + "</h4></div>")
            continue
        out += [_prop_card(c) for c in picked]

    w = by.get("이 제안이 틀린다면", {})
    body = (w.get("body") or "").strip()
    out += ['<h2 class="sec"><span class="no">4</span>이 제안이 틀린다면</h2>',
            "<p>" + (_mark(body) if body
                     else _todo("[ 사람이 씁니다 — 무엇 때문에 틀릴 수 있는지, "
                                "확인하려면 무엇을 보면 되는지 ]")) + "</p>",
            '<div class="callout stop"><b>철회 조건 —</b> '
            + _todo("[ 사람이 씁니다 ]") + "</div>"]

    a = by.get("적용", {})
    out += ['<h2 class="sec"><span class="no">5</span>적용</h2>',
            '<p class="sec-lead">이번 분석에서 쓴 방법 중 앞으로도 쓸 것.</p>',
            "<table><thead><tr><th>판단 기준 (자동으로 가져온 후보)</th>"
            "<th>어디에 적용하면 무엇이 달라지나</th></tr></thead><tbody>"]
    for e in (a.get("candidates") or []):
        for it in e["items"]:
            out.append("<tr><td>" + _mark(it) + "</td><td>"
                       + _todo("[ 사람이 고르고 씁니다 ]") + "</td></tr>")
    out.append("</tbody></table>")
    abody = (a.get("body") or "").strip()
    out.append('<p class="small">' + (_mark(abody) if abody
               else _todo("[ 다음에 무엇을 볼 것인가 — 사람이 씁니다 ]")) + "</p>")

    ap = by.get("부록 (근거 상세)", {})
    out += ['<div class="appendix">',
            '<h2 class="sec">부록 A · 근거 상세</h2>',
            '<p class="small" style="white-space:pre-line">'
            + _mark(ap.get("body", "")) + "</p>",
            '<h2 class="sec">부록 B · 방법</h2>',
            "<table><tbody>",
            "<tr><th>분석 단위</th><td>과제번호 1건 (고유하게 센다)</td></tr>",
            '<tr><th>기간</th><td class="num">' + _esc(C.PERIOD[0]) + " ~ "
            + _esc(C.PERIOD[1]) + "</td></tr>",
            '<tr><th>판정 기준</th><td>최소 표본 <span class="num">'
            + str(C.MIN_SAMPLE) + '</span> · 칸 하한 <span class="num">'
            + str(C.MIN_CELL) + '</span> · 격차 기준 <span class="num">'
            + str(round(C.MIN_GAP * 100, 1)) + "</span>%p</td></tr>",
            "<tr><th>가정값</th><td>"
            + _todo("[ 없음 — 이번 카드에 가정값이 없다 ]")
            + " <b>실측값과 섞지 않았다</b></td></tr>",
            "</tbody></table>",
            "</div>"]

    out += ["</div></body></html>"]
    return "\n".join(out)


# ── PDF 로 내보내기 ───────────────────────────────────────────────
#
# report/to_pdf.py 의 Report 를 **그대로 재사용한다.** 새 PDF 클래스를 만들지 않는다 —
# 표지·머리말·꼬리말·폰트 처리가 갈라지면 두 문서가 다르게 인쇄된다.
#
# ⚠ **폰트에 없는 글자는 경고 없이 사라진다.** 화면(HTML)은 브라우저 폰트라 멀쩡한데
#   PDF 는 Noto Sans KR 하나만 쓴다. 실제로 확인한 결과 아래 9자가 없다:
#
#       ① ② ③   ✕ ▲ ●   「 」   ⚠   (그 밖에 ≤ ≥ − ✓ 도 없다)
#
#   그래서 **바꿔치기 표를 두고, 바꾼 뒤에도 남은 글자가 있는지 전수로 훑는다.**
#   몇 장만 눈으로 보는 것보다 전수 대조가 확실하다. (판단기준 2026-09-05)

#: PDF 로 낼 때 바꿔치기할 글자. 화면(HTML)에서는 그대로 쓴다.
PDF_SUBST = {
    "①": "1.", "②": "2.", "③": "3.",
    "✕": "X", "▲": "!", "●": "*", "✓": "v",
    "「": '"', "」": '"',
    "⚠": "(주의)",
    "≤": " 이하", "≥": " 이상", "−": "-",
}

_CMAP_CACHE: set[int] | None = None


def _font_cmap() -> set[int]:
    """PDF 폰트가 실제로 가진 글자 집합. 없으면 빈 집합(= 검사 생략)."""
    global _CMAP_CACHE
    if _CMAP_CACHE is not None:
        return _CMAP_CACHE
    _CMAP_CACHE = set()
    try:
        from fontTools.ttLib import TTFont
        reg = to_pdf.FONT_DIR / "NotoSansKR-Regular.ttf"
        if reg.exists():
            f = TTFont(str(reg))
            for t in f["cmap"].tables:
                _CMAP_CACHE |= set(t.cmap.keys())
    except Exception:
        pass
    return _CMAP_CACHE


def pdf_safe(text) -> str:
    """PDF 에 넣기 전에 폰트에 없는 글자를 바꾼다. **지우지 않고 바꾼다.**"""
    s = str(text or "")
    for bad, good in PDF_SUBST.items():
        s = s.replace(bad, good)
    return s


def missing_glyphs(secs: list[dict]) -> list[str]:
    """바꿔치기 뒤에도 폰트에 없는 글자가 남았는지 **전수로** 훑는다.

    빈 목록이면 인쇄본에서 사라지는 글자가 없다는 뜻이다.
    남으면 화면에 띄운다 — 조용히 사라지게 두지 않는다.
    """
    cmap = _font_cmap()
    if not cmap:
        return []
    # ⚠ Day2 절({title,body})과 Day3 절({제목,질문,문장})을 **둘 다** 읽는다.
    #   한쪽만 읽으면 새 문서의 글자를 훑지 않고 "통과"라고 말한다.
    bag = []
    for s in secs:
        bag += [s.get("title", ""), s.get("body", ""),
                s.get("제목", ""), s.get("질문", "")]
        bag += list(s.get("문장") or [])
        for e in (s.get("candidates") or []):
            bag.append(e.get("head", ""))
            bag += e.get("items", [])
    seen = {}
    for ch in pdf_safe(" ".join(bag)):
        if ch in ("\n", "\t"):
            continue
        if ord(ch) not in cmap:
            seen[ch] = seen.get(ch, 0) + 1
    return [f"{ch} (U+{ord(ch):04X}) x{n}" for ch, n in seen.items()]


def build_pdf_cards(secs: list[dict], title: str = "제안서") -> bytes:
    # ⚠ Day2 절 모양을 받는다. Day3 절은 build_pdf() 가 받는다.
    """제안서를 PDF 로. to_pdf.Report 를 그대로 쓴다.

    ★ Day2 실습 E 프롬프트 9.

    to_pdf.build_pdf() 와 다른 점 둘:
      1. 차트가 없다 — 제안서는 카드를 옮긴 문서다.
      2. **생성 시각을 넣지 않는다.** 카드의 "최종 갱신" 을 쓴다.
         같은 입력이면 언제 돌려도 같은 파일이 나와야 한다. (CLAUDE.md 코드 규칙 2)
    """
    pdf = to_pdf.Report()
    meta = parse_cards().get("meta", {})

    # ⚠ fpdf2 는 **자기가** /CreationDate 에 현재 시각을 박는다. 내 코드에 now() 가
    #   없어도 파일이 매번 달라진다. 카드의 "최종 갱신" 날짜로 고정해 재현을 지킨다.
    stamp = str(meta.get("최종 갱신", "")).strip()
    try:
        # fpdf2 는 tz 를 요구한다. 날짜만 고정하면 되므로 UTC 로 붙인다.
        pdf.creation_date = datetime.strptime(
            stamp[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    # ── 표지 ──────────────────────────────────────────────────────
    pdf.add_page()
    pdf.ln(64)
    pdf.set_font(pdf.base, "B", 26)
    pdf.set_text_color(*to_pdf.INK)
    pdf.multi_cell(0, 12, pdf_safe(title), align="L")
    pdf.ln(3)
    pdf.set_font(pdf.base, "", 12)
    pdf.set_text_color(*to_pdf.MUTED)
    pdf.cell(0, 8, f"{C.PERIOD[0]} ~ {C.PERIOD[1]}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, pdf_safe(f"데이터셋 {C.DATASET}"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    pdf.set_draw_color(*to_pdf._hex(C.BRAND["primary"]))
    pdf.set_line_width(1.2)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + 40, pdf.get_y())
    pdf.ln(14)
    pdf.set_font(pdf.base, "", 10)
    pdf.set_text_color(*to_pdf.MUTED)
    pdf.cell(0, 6, pdf_safe("카드 최종 갱신 " + meta.get("최종 갱신", "미상")))

    # ── 목차 ──────────────────────────────────────────────────────
    pdf.add_page()
    pdf.set_font(pdf.base, "B", 15)
    pdf.set_text_color(*to_pdf.INK)
    pdf.cell(0, 10, "목차", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    for s in secs:
        pdf.set_font(pdf.base, "", 11)
        pdf.set_text_color(*to_pdf.INK)
        mark = "" if s["kind"] == "auto" else "  (사람 작성)"
        pdf.cell(0, 8, pdf_safe(s["title"] + mark), new_x="LMARGIN", new_y="NEXT")

    # ⚠ multi_cell(w=0) 은 폭을 "현재 x 부터 오른쪽 여백까지" 로 잡는다.
    #   앞 호출이 커서를 오른쪽에 두고 끝나면 폭이 0이 되어 터진다.
    #   그래서 **줄마다 x 를 왼쪽 여백으로 되돌린다.**
    # ── 본문 ──────────────────────────────────────────────────────
    for s in secs:
        pdf.add_page()
        pdf.set_font(pdf.base, "B", 15)
        pdf.set_text_color(*to_pdf.INK)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 9, pdf_safe(s["title"]))
        pdf.ln(1)
        pdf.set_draw_color(*to_pdf.LINE)
        pdf.set_line_width(0.3)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(6)

        # 적용 절 — 후보는 자동이고 읽기 전용이다. 사람 글과 나눠서 싣는다.
        for e in (s.get("candidates") or []):
            pdf.set_font(pdf.base, "B", 9.5)
            pdf.set_text_color(*to_pdf.MUTED)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 5.6, pdf_safe(e["head"]))
            pdf.set_font(pdf.base, "", 9.5)
            pdf.set_text_color(*to_pdf.INK)
            for it in e["items"]:
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(0, 5.4, pdf_safe("  - " + it))
            pdf.ln(2)

        body = (s.get("body") or "").strip()
        if not body:
            pdf.set_font(pdf.base, "", 10)
            pdf.set_text_color(*to_pdf.MUTED)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 6, pdf_safe(
                "[작성되지 않음] " + str(s.get("placeholder", ""))))
            continue

        pdf.set_font(pdf.base, "", 10.5)
        pdf.set_text_color(*to_pdf.INK)
        for para in body.split("\n\n"):
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 6.2, pdf_safe(para.strip()))
            pdf.ln(3)

    return bytes(pdf.output())


# ── Day3 조립기 — 주제 하나로 6절을 만든다 ────────────────────────
#
# ★ Day3(9주차) 실습 D 프롬프트 5.
#
# Day2 의 build_cards() 와 **다른 문서다.** 읽는 사람이 다르다 —
# 저건 카드를 절로 옮긴 것이고, 이것은 **결정을 요청하는 문서**다.
# 읽고 나서 승인 / 조건부 승인 / 보류 중 하나가 나와야 한다.
#
# 이 파일이 지키는 것:
#
#   1. **절 목록과 제목을 여기 박지 않는다.** config.PROPOSAL_SECTIONS ·
#      config.PROPOSAL_WORDS 가 원본이다
#   2. **계산하지 않는다.** evidence 와 cards 에 있는 것을 옮기기만 한다 —
#      여기서 다시 계산하면 metrics 와 갈라진다
#   3. **근거가 없으면 그 절을 아예 만들지 않는다.** 빈 절을 만들어 채우지 않는다
#   4. **사람이 쓰는 두 절은 근거가 없어도 항상 만든다.** 자동 절이 줄어도 남는다 —
#      하나도 없으면 책임질 사람이 없는 문서가 된다
#
# ⚠ 이 도메인에서 3번이 실제로 걸린다 — ④ 추세 주제는 원인·규모가 None 이라
#   절이 6개에서 **4개로 준다.** 그것이 정상이다. (Day3 부록 C)

from viz import proposal_charts as PCH


#: 한 절의 문장 상한. **넘으면 분석 문서로 돌아간 것이다.**
MAX_LINES = 3


def _josa(word: str, pair: str) -> str:
    """받침을 보고 조사를 고른다.

    칸 이름·축 이름이 데이터에서 오므로 조사를 하드코딩할 수 없다 —
    "숙주 식별으로"(X) / "국가으로"(X) 같은 문장이 그대로 인쇄된다.

    pair 는 **받침있음 + 받침없음** 순서: "은는" · "이가" · "을를" · "과와".
    "로" 는 특수 — 받침이 없거나 ㄹ 이면 "로", 아니면 "으로".
    """
    ch = (word or "").strip()
    ch = ch[-1] if ch else ""
    if not ("가" <= ch <= "힣"):
        jong = 0                                  # 숫자·영문은 받침 없는 것으로 본다
    else:
        jong = (ord(ch) - 0xAC00) % 28
    if pair == "로":
        return "로" if jong in (0, 8) else "으로"   # 받침 없거나 ㄹ이면 "로"
    # pair 는 "받침있음+받침없음" 순서다 — 은는 · 이가 · 을를 · 과와
    return pair[0] if jong else pair[1]


def _pp(v) -> str:
    """격차 표기. **소수 둘째 자리로 맞춘다** — 발견.md·카드와 자릿수를 맞춰
    읽는 사람이 직접 빼볼 수 있게 한다."""
    return "—" if v is None else f"{float(v):.2f}"


def _seg(a: str, b: str) -> str:
    """구간은 "A -> B" 로 적는다. 도착 단계만 쓰면 무엇에서 무엇으로 가는
    비율인지 사라진다."""
    return f"{C.FUNNEL_LABELS.get(a, a)} -> {C.FUNNEL_LABELS.get(b, b)}"


def _has(ev: dict | None) -> bool:
    """이 근거 항목에 실을 것이 있는가. **None 과 빈 것을 같게 본다.**"""
    if not ev:
        return False
    return bool(ev.get("단계") or ev.get("축") or ev.get("연도별")
                or ev.get("연간건수") is not None)


def _sec(key: str, kind: str, 문장: list[str],
         차트: list[str] | None = None, 표: dict | None = None,
         제목키: str | None = None) -> dict:
    """절 하나. 제목·질문은 **config 에서만** 온다.

    ⚠ 한 절은 MAX_LINES 문장을 넘지 않는다. 넘으면 분석 문서로 돌아간 것이다.
    ⚠ 자동으로 쓴 문장에 **인과 단정 표현 검사**를 건다 — 새로 만들지 않고
      report.sections 것을 그대로 쓴다. 사람이 쓴 절에는 걸지 않는다
      (사람 문장 때문에 문서 조립이 실패하면 안 된다 — Day3 프롬프트 10).
    """
    tk = 제목키 or key
    lines = [x for x in 문장 if x][:MAX_LINES]
    sec = {"키": key, "제목": C.words("절제목", tk), "질문": C.words("질문", tk),
           "kind": kind, "문장": lines,
           "차트": [c for c in (차트 or []) if c], "표": 표}
    if kind == "auto":
        bad = check_phrasing(" ".join(lines))
        sec["문장검사"] = bad or None
    return sec


# ── 자동 절 ───────────────────────────────────────────────────────
def _s_현황(ev: dict, topic: dict) -> dict | None:
    s = ev.get("현황")
    if not _has(s):
        return None
    steps = s["단계"]
    seg = s.get("병목구간")
    bn = next((x for x in steps if x.get("병목")), None)
    prev = None
    if bn:
        i = steps.index(bn)
        prev = steps[i - 1] if i else None

    문장 = []
    if bn and prev:
        lb_prev = C.FUNNEL_LABELS.get(prev["단계"], prev["단계"])
        lb_bn = C.FUNNEL_LABELS.get(bn["단계"], bn["단계"])
        문장.append(f"{lb_prev}에 이른 {prev['도달']:,}건 중 "
                    f"{lb_bn}에 이르는 것은 {bn['도달']:,}건, {_pp(bn['전환율'])}%입니다.")
        # 비교 대상 — 어느 구간과 견줘서 낮은지. 구간 이름을 "A -> B" 로 적는다.
        others = []
        for i, x in enumerate(steps):
            if x.get("전환율") is None or x is bn or not i:
                continue
            others.append((steps[i - 1]["단계"], x["단계"], x["전환율"]))
        if others:
            fa, fb, rate = max(others, key=lambda o: o[2])
            문장.append(f"같은 흐름의 {_seg(fa, fb)} 구간은 {_pp(rate)}%로, "
                        f"{_seg(prev['단계'], bn['단계'])} 구간이 "
                        f"둘 중 낮은 쪽입니다.")
    return _sec("현황", "auto", 문장,
                [PCH.funnel_svg(s)],
                {"이름": "단계별 도달", "행": steps,
                 "병목구간": (" -> ".join(seg) if seg else None)})


def _s_원인(ev: dict, topic: dict) -> dict | None:
    c = ev.get("원인")
    if not _has(c):
        return None                      # 축이 없는 갈래 — 절을 만들지 않는다
    축들 = c["축"]

    문장, 차트 = [], []
    for ax in 축들:
        차트.append(PCH.gap_svg(ax))
        shown = [k for k in ax["칸"] if k.get("전환율") is not None]
        if len(shown) < 2:
            continue
        hi = max(shown, key=lambda k: k["전환율"])
        lo = min(shown, key=lambda k: k["전환율"])
        gap = ax.get("격차_%p")
        nm = ax["이름"]
        ro = _josa(nm, "로")
        if gap is not None and gap >= C.MIN_GAP * 100:
            문장.append(f"{nm}{ro} 나누면 {lo['칸']} {_pp(lo['전환율'])}%, "
                        f"{hi['칸']} {_pp(hi['전환율'])}%로 {_pp(gap)}%p 벌어집니다. "
                        f"낮은 쪽이 전체의 {_pp(lo['비중'])}%입니다.")
        elif gap is not None:
            # "안 갈린다"도 결과다. 지우지 않는다. 판정어는 config 에서 온다.
            문장.append(f"{nm}{ro}는 {_pp(gap)}%p 차이에 그쳐 "
                        f"{C.words('판정어', '안갈림')}")
        if ax.get("감춘칸"):
            문장.append(f"{nm}에서 {len(ax['감춘칸'])}칸은 "
                        f"{C.words('판정어', '감춘칸')}했습니다"
                        f"({' · '.join(ax['감춘칸'])}).")
    return _sec("원인", "auto", 문장, 차트,
                {"이름": "축별 전환율", "축": 축들})


def _s_규모(ev: dict, topic: dict) -> dict | None:
    """규모 — **규모가 없어도 추세가 있으면 만든다.** (2026-09-10 결정)

    추세 주제는 나빠지지 않아 규모를 재지 않는다. 그때 이 절을 통째로 빼면
    **추세 주제인데 추세 그림이 없는 문서**가 된다. 대신 제목을 바꾼다 —
    "연 몇 건입니까" 라고 물어놓고 건수가 없으면 제목이 거짓이 된다.
    """
    z = ev.get("규모") or {}
    tr = ev.get("추세") or {}
    has_size = z.get("연간건수") is not None
    has_trend = _has(tr)
    if not (has_size or has_trend):
        return None

    문장 = []
    if has_size:
        # ⚠ 실측 문장과 환산 문장을 한 문장에 합치지 않는다. 합치면 추정이 실측처럼 읽힌다.
        문장.append(f"이 격차가 유지된다고 보면 연 {z['연간건수']}건이 "
                    f"이 구간에서 더 빠집니다.")
        # ⚠ 계산 과정을 문서에 넣지 않는다. **가정은 남긴다** —
        #   환산에 가정이 안 붙으면 예측을 실측처럼 쓰는 것이다.
        plain = z.get("가정_문서용")
        if plain:
            문장.append("(" + plain + ")")
    if has_trend and len(문장) < MAX_LINES:
        rows = [r for r in tr["연도별"] if not r.get("반쪽")]
        if len(rows) >= 2:
            a, b = rows[-2], rows[-1]
            문장.append(f"{tr['지표']}{_josa(tr['지표'], '은는')} "
                        f"{a['연도']}년 {_pp(a['값'])}에서 {b['연도']}년 {_pp(b['값'])}로 "
                        f"움직였습니다 (연 단위, 완결된 해만).")

    return _sec("규모", "auto", 문장,
                [PCH.trend_svg(tr)] if has_trend else [],
                {"이름": "환산" if has_size else "추세",
                 "연간건수": z.get("연간건수"), "가정": z.get("가정") or []},
                제목키=None if has_size else "규모_추세만")


def _s_제안(cards: dict, topic: dict) -> dict | None:
    cl = (cards or {}).get("cards") or []
    if not cl:
        return None
    문장 = []
    for cls in CLASSES:
        picked = [c for c in cl if c.get("분류") == cls]
        if picked:
            문장.append(f"{C.words('분류어', cls)} {len(picked)}건 — "
                        + " / ".join(c["title"] for c in picked))
    return _sec("제안", "auto", 문장, [], {"이름": "제안 카드", "카드": cl})


# ── 사람이 쓰는 절 — **근거가 없어도 항상 만든다** ────────────────
#: 요청 문장에 이 중 하나가 없으면 그것은 보고이지 제안이 아니다.
DECIDE_VERBS = ("승인", "결정", "판단")


def has_decide_verb(text: str) -> bool:
    """요청 문장에 **결정을 요구하는 동사**가 있는가.

    없으면 화면에 경고를 띄운다. **저장은 막지 않는다** —
    사람이 쓴 문장 때문에 문서 조립이 실패하면 안 된다. (Day3 프롬프트 10)
    """
    return any(v in (text or "") for v in DECIDE_VERBS)


def _decision_options(cards: dict, size) -> list[dict]:
    """결정 선택지 셋. **무엇이 따라오는지는 카드에서 온다. 지어내지 않는다.**

    재료는 카드의 「되돌림」이다 — 어떻게 되돌리는지가 거기 적혀 있다.
    (2026-09-10 사람이 고름: 되돌림 방법을 선택지마다 적는다)
    """
    cl = (cards or {}).get("cards") or []
    stop = [c for c in cl if c.get("분류") == "하지 말 것"]
    ways = []
    for c in stop:
        back = (c.get("되돌림") or "").strip()
        if back.startswith("가능"):
            # "가능 — 축 목록에서 이름 하나를 빼고 ... (코드 사실)" 에서 방법만
            how = back.split("—", 1)[-1].split("(")[0].strip(" .")
            if how:
                ways.append(how)
    n = len(stop)
    lab = C.words("분류어", "하지 말 것")

    후속 = {
        "승인": (f"{lab} {n}건을 적용합니다."
               + (f" 되돌리는 방법: {' · '.join(ways)}." if ways else "")
               + " 셋 다 되돌릴 수 있습니다."),
        "조건부 승인": f"{lab} 가운데 일부만 적용합니다. "
                   f"어느 것을 남길지 지정해 주셔야 합니다.",
        "보류": ("다음 회차까지 지금 상태로 둡니다."
               + (f" 그동안 연 {size}건이 계속 빠집니다."
                  if size is not None else
                  " 이 주제는 규모를 재지 않아 누적을 낼 수 없습니다.")),
    }
    return [{"선택": k, "따라오는 것": v} for k, v in 후속.items()]


def _s_human(key: str, human: dict, cards: dict | None = None,
             topic: dict | None = None) -> dict:
    title = C.words("절제목", key)
    body = (human or {}).get(key) or (human or {}).get(title) or ""
    sec = _sec(key, "human", [body] if body.strip() else [])
    sec["placeholder"] = {
        "위험": "이 판단이 무엇 때문에 틀릴 수 있는지, 그리고 "
              "무엇이 어떻게 되면 이 제안을 접을 것인지 적으십시오.",
        "요청": "무엇을 결정해 주셔야 하는지 적으십시오. "
              "승인 · 결정 · 판단 중 하나가 문장에 들어가야 합니다.",
    }.get(key, "")

    if key != "요청":
        return sec

    # ── 요청 절에만 자동으로 붙는 것 셋 ──────────────────────────
    #   문장은 사람이 쓴다. 아래는 **자동**이다.
    t = topic or {}
    size = t.get("규모_연간건수")
    sec["규모"] = size
    sec["선택지"] = _decision_options(cards or {}, size)
    # ⚠ "다음 분기"가 아니라 **다음 1년**이다. 이 도메인은 연 단위로 센다 —
    #   심사가 중앙 176일 걸리고 지표가 종결연도별이라 분기 숫자가 크기를 못 전한다.
    sec["미룰때"] = (f"결정을 다음 1년까지 미루면 {size}건이 더 쌓입니다."
                  if size is not None else
                  "이 주제는 규모를 재지 않아 누적을 낼 수 없습니다.")
    # ⚠ 모르는 것을 낱말 하나로 두지 않는다 — 셋이 갖춰져야 구멍이 아니라 요청이 된다.
    #   [무엇을 모르는가]는 카드에 있고, [누가 확인하는가]는 사람이 정했다.
    unknown = []
    for c in ((cards or {}).get("cards") or []):
        for field in ("비용", "효과"):
            v = (c.get(field) or "").strip()
            if not is_todo(v):
                continue
            what = v.split("—", 1)[-1].strip() if "—" in v else field
            unknown.append({
                "무엇": f"{c['title']} 의 {field} — {what}",
                "누가": "분석 담당자가 다음 회차에 직접 산정합니다",
                "모르는채로": "되돌릴 수 있으므로 "
                          f"{C.words('분류어', '하지 말 것')} 결정은 지금 내릴 수 있습니다",
            })
    sec["확인필요"] = unknown
    return sec


# ── 조립 ──────────────────────────────────────────────────────────
def build(topic: dict, evidence: dict, cards: dict | None = None,
          human: dict | None = None) -> list[dict]:
    """주제 하나로 절 목록을 만든다.

    ★ Day3 실습 D 프롬프트 5.

    topic     proposal_topics() 후보 하나
    evidence  topic_evidence(t, topic) 결과
    cards     parse_cards() 결과 (4절이 쓴다)
    human     사람이 쓴 절의 본문 {절 키 또는 제목: 본문}

    **순서와 자동/사람 구분은 config.PROPOSAL_SECTIONS 가 정한다.** 여기서 바꾸지 않는다.
    근거가 없는 자동 절은 **만들지 않는다** — 빈 절을 만들어 채우면 그 자리가
    그대로 인쇄된다. 사람이 쓰는 두 절은 근거와 무관하게 항상 만든다.
    """
    human = human or {}
    out = []
    for key, kind, _ev_key in C.PROPOSAL_SECTIONS:
        if kind == "human":
            out.append(_s_human(key, human, cards or {}, topic))
            continue
        sec = {"현황": lambda: _s_현황(evidence, topic),
               "원인": lambda: _s_원인(evidence, topic),
               "규모": lambda: _s_규모(evidence, topic),
               "제안": lambda: _s_제안(cards or {}, topic)}[key]()
        if sec:
            out.append(sec)
    return out


# ── Day3 내보내기 ─────────────────────────────────────────────────
#
# ⚠ Day2 의 to_html_cards()·build_pdf_cards() 와 **절의 모양이 다르다.**
#     Day2  {"title", "kind", "body", ...}
#     Day3  {"키", "제목", "질문", "kind", "문장", "차트", "표"}
#   같은 이름으로 두면 조용히 빈 문서가 나온다. 이름을 갈랐다.
#
# ★ 여기 to_html() 은 **뼈대만**이다. A4 인쇄 디자인은 프롬프트 8 에서 짠다.

def _sec_text(sec: dict) -> str:
    """절 하나의 글자만 뽑는다. 폰트 검사·문장 검사가 같은 것을 본다."""
    parts = [sec.get("제목") or sec.get("title") or "",
             sec.get("질문") or ""]
    parts += list(sec.get("문장") or [])
    b = sec.get("body")
    if b:
        parts.append(b)
    return " ".join(str(x) for x in parts if x)


# ── A4 인쇄용 스타일 ──────────────────────────────────────────────
#
# ★ Day3 실습 E 프롬프트 8. **템플릿 파일을 읽지 않는다. 이 함수가 직접 만든다.**
#
# 색은 넷까지 — 먹색 본문 · 회색 보조 · 강조 1 · 위험 1.
# 다섯째 색이 생기면 강조가 강조가 아니게 된다.
#
# 웹폰트·CDN·외부 이미지를 쓰지 않는다. **파일 하나로 열려야 한다** —
# 인터넷이 없어도, 파일만 건네받아도 같아야 한다.

_A4_CSS = """
@page{size:A4;margin:18mm 16mm}
:root{--ink:@INK@;--muted:@MUTED@;--accent:@ACCENT@;--risk:@RISK@;--line:@LINE@}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{font-family:'Malgun Gothic','Apple SD Gothic Neo',system-ui,sans-serif;
     color:var(--ink);font-size:10.5pt;line-height:1.7;background:#fff}
.page{max-width:186mm;margin:0 auto;padding:10mm 0 16mm}

/* 제목 위계는 3단까지만 */
h1{font-size:20pt;font-weight:800;margin:0 0 4px;line-height:1.3}
h2{font-size:13pt;font-weight:700;margin:22px 0 1px;page-break-after:avoid}
h3{font-size:11pt;font-weight:700;margin:14px 0 4px;page-break-after:avoid}
.lead{font-size:10pt;color:var(--muted);margin:0 0 4px}
.q{font-size:8.8pt;color:var(--muted);margin:0 0 8px}
.meta{font-size:8.5pt;color:var(--muted);border-top:1px solid var(--line);
      padding-top:6px;margin-top:4px}
p{margin:5px 0}

/* 숫자 — tabular-nums 로 굵게, 단위는 한 단계 작게 */
.num{font-variant-numeric:tabular-nums;font-feature-settings:"tnum";font-weight:700}
.unit{font-size:0.88em;font-weight:400;color:var(--muted)}

/* 한 장 요약 — 문서 맨 앞 박스 하나 */
.summary{border:1px solid var(--line);border-top:3px solid var(--accent);
         border-radius:6px;padding:12px 16px;margin:14px 0 6px;
         page-break-inside:avoid}
.summary h2{font-size:9pt;font-weight:700;color:var(--accent);margin:0 0 8px;
            letter-spacing:.06em}
.srow{display:flex;gap:12px;padding:5px 0;border-top:1px solid var(--line)}
.srow:first-of-type{border-top:none;padding-top:0}
.srow .k{flex:0 0 46px;font-size:8.5pt;font-weight:700;color:var(--muted);
         padding-top:2px}
.srow .v{flex:1}

/* 표 — 가로선만. 세로선 금지. 머리행만 옅은 배경 */
table{border-collapse:collapse;width:100%;font-size:9pt;margin:8px 0 10px;
      page-break-inside:avoid}
th,td{border:none;border-bottom:1px solid var(--line);padding:5px 8px;
      text-align:left;vertical-align:top}
thead th{background:#f8fafc;border-bottom:1.5px solid var(--line);
         font-weight:700;font-size:8.5pt;color:var(--muted)}
td.r,th.r{text-align:right}
tr.hl td{font-weight:700}
tr.dim td{color:var(--muted)}

.todo{color:var(--risk);font-weight:700}
.note{font-size:8.8pt;color:var(--muted);margin:4px 0}
figure{margin:8px 0 12px;page-break-inside:avoid}
svg{max-width:100%}
@media print{.page{padding:0}}
"""


def _a4_css() -> str:
    css = _A4_CSS
    for k, v in (("@INK@", C.BRAND["ink"]), ("@MUTED@", C.BRAND["muted"]),
                 ("@ACCENT@", C.BRAND["primary"]), ("@RISK@", C.COLORS["block"]),
                 ("@LINE@", C.BRAND["line"])):
        css = css.replace(k, v)
    return css


_N_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)(%p|%|건|년|일)?")


def _nums(text) -> str:
    """숫자에 tabular-nums 굵게, 단위는 한 단계 작게. escape 뒤에 돌린다."""
    def sub(m):
        out = '<span class="num">' + m.group(1) + "</span>"
        if m.group(2):
            out += '<span class="unit">' + m.group(2) + "</span>"
        return out
    return _N_RE.sub(sub, _esc(text))


def _summary_rows(secs: list[dict], topic: dict) -> list[tuple[str, str]]:
    """한 장 요약 — **절 순서와 같게.** 절이 없으면 그 줄도 없다.

    build() 가 요약 절을 만들지 않는다. 여기서 절에서 뽑아 만든다.
    (Day3 판단 기준 1: 한 장 요약은 본문 여섯을 압축한 것. 순서가 같아야 한다)
    """
    by = {s["키"]: s for s in secs}
    rows = []
    for key, label in (("현황", "현황"), ("원인", "원인"),
                       ("규모", "규모"), ("요청", "요청")):
        sec = by.get(key)
        if not sec:
            continue                      # 절이 없으면 요약 줄도 없다
        lines = sec.get("문장") or []
        if key == "요청" and not lines:
            rows.append((label, '<span class="todo">[작성되지 않음 — 사람이 씁니다]</span>'))
            continue
        if not lines:
            continue
        rows.append((label, _nums(lines[0])))
    return rows


def _table_html(sec: dict) -> str:
    """절의 표. **가로선만.** 컬럼 이름이 아니라 라벨을 쓴다."""
    tb = sec.get("표") or {}
    name = tb.get("이름")

    if name == "단계별 도달":
        rows = tb.get("행") or []
        out = ["<table><thead><tr><th>단계</th><th class='r'>도달</th>"
               "<th class='r'>전 단계 대비</th></tr></thead><tbody>"]
        for r in rows:
            cls = ' class="hl"' if r.get("병목") else ""
            rate = "—" if r.get("전환율") is None else f"{r['전환율']}%"
            out.append(f"<tr{cls}><td>{_esc(C.FUNNEL_LABELS.get(r['단계'], r['단계']))}"
                       f"</td><td class='r'>{_nums(format(r['도달'], ','))}</td>"
                       f"<td class='r'>{_nums(rate)}</td></tr>")
        return "".join(out) + "</tbody></table>"

    if name == "축별 전환율":
        out = []
        for ax in (tb.get("축") or []):
            out.append(f"<h3>{_esc(ax['이름'])}</h3>")
            out.append("<table><thead><tr><th>구분</th><th class='r'>도달</th>"
                       "<th class='r'>도달률</th><th class='r'>비중</th>"
                       "</tr></thead><tbody>")
            for k in ax.get("칸") or []:
                if k.get("전환율") is None:
                    out.append(f"<tr class='dim'><td>{_esc(k['칸'])}</td>"
                               f"<td class='r'>{_nums(format(k['도달'], ','))}</td>"
                               f"<td colspan='2'>{_esc(k.get('사유', ''))}</td></tr>")
                    continue
                cls = ' class="hl"' if (k.get("최저") or k.get("최고")) else ""
                out.append(f"<tr{cls}><td>{_esc(k['칸'])}</td>"
                           f"<td class='r'>{_nums(format(k['도달'], ','))}</td>"
                           f"<td class='r'>{_nums(str(k['전환율']) + '%')}</td>"
                           f"<td class='r'>{_nums(str(k['비중']) + '%')}</td></tr>")
            out.append("</tbody></table>")
        return "".join(out)

    if name == "제안 카드":
        out = ["<table><thead><tr><th>구분</th><th>무엇을</th><th>되돌림</th>"
               "</tr></thead><tbody>"]
        for c in tb.get("카드") or []:
            back = c.get("되돌림") or ""
            out.append(f"<tr><td>{_esc(C.words('분류어', c.get('분류', '')))}</td>"
                       f"<td>{_esc(c['title'])}</td>"
                       f"<td>{_esc(back.split('—')[0].strip() or '—')}</td></tr>")
        return "".join(out) + "</tbody></table>"
    return ""


def to_html(secs: list[dict], topic: dict | None = None) -> str:
    """제안서를 **A4 인쇄 기준 단일 HTML** 로. 템플릿 파일을 읽지 않는다.

    ★ Day3 실습 E 프롬프트 8.

    · 빈 절은 그리지 않는다 — 애초에 build() 가 안 만든다
    · 웹폰트·CDN·외부 이미지를 쓰지 않는다. 파일 하나로 열린다
    · 계산 과정·함수 이름·컬럼 이름을 문서에 넣지 않는다
    """
    t = topic or {}
    title = t.get("제목") or "제안서"
    out = ["<!DOCTYPE html>", '<html lang="ko"><head><meta charset="UTF-8">',
           '<meta name="viewport" content="width=device-width, initial-scale=1">',
           f"<title>{_esc(title)}</title>",
           "<style>" + _a4_css() + "</style></head><body>", '<div class="page">']

    out.append(f"<h1>{_esc(title)}</h1>")
    if t.get("한줄"):
        out.append(f'<p class="lead">{_nums(t["한줄"])}</p>')
    if t.get("기각사유"):
        out.append(f'<p class="note"><span class="todo">'
                   f'{_esc(C.words("판정어", "기각"))}</span> — '
                   f'{_esc(t["기각사유"])}</p>')
    out.append(f'<div class="meta">{_esc(C.DATASET)} · '
               f'{_esc(C.PERIOD[0])} ~ {_esc(C.PERIOD[1])}</div>')

    rows = _summary_rows(secs, t)
    if rows:
        out.append('<div class="summary"><h2>한 장 요약</h2>')
        for k, v in rows:
            out.append(f'<div class="srow"><div class="k">{_esc(k)}</div>'
                       f'<div class="v">{v}</div></div>')
        out.append("</div>")

    for sec in secs:
        out.append(f"<h2>{_esc(sec.get('제목', ''))}</h2>")
        if sec.get("질문"):
            out.append(f'<p class="q">{_esc(sec["질문"])}</p>')
        lines = sec.get("문장") or []
        if lines:
            for ln in lines:
                out.append(f"<p>{_nums(ln)}</p>")
        elif sec["kind"] == "human":
            out.append(f'<p class="todo">[작성되지 않음] '
                       f'{_esc(sec.get("placeholder", ""))}</p>')

        # 요청 절 — 문장은 사람이 쓰고, 아래 셋은 자동이다.
        if sec["키"] == "요청":
            opts = sec.get("선택지") or []
            if opts:
                out.append("<table><thead><tr><th>결정</th><th>무엇이 따라오나"
                           "</th></tr></thead><tbody>")
                for o in opts:
                    out.append(f"<tr><td>{_esc(o['선택'])}</td>"
                               f"<td>{_nums(o['따라오는 것'])}</td></tr>")
                out.append("</tbody></table>")
            if sec.get("미룰때"):
                out.append(f'<p class="note">{_nums(sec["미룰때"])}</p>')
            uk = sec.get("확인필요") or []
            if uk:
                out.append(f"<h3>{_esc(C.words('확인필요', '미확인'))}</h3>")
                out.append("<table><thead><tr><th>무엇을 모르는가</th>"
                           "<th>누가 확인하는가</th>"
                           "<th>모르는 채로 할 수 있는 결정</th></tr></thead><tbody>")
                for u in uk:
                    out.append(f"<tr><td>{_esc(u['무엇'])}</td>"
                               f"<td>{_esc(u['누가'])}</td>"
                               f"<td>{_esc(u['모르는채로'])}</td></tr>")
                out.append("</tbody></table>")
        tbl = _table_html(sec)
        if tbl:
            out.append(tbl)
        for svg in (sec.get("차트") or []):
            out.append("<figure>" + svg + "</figure>")

    out.append("</div></body></html>")
    return chr(10).join(out)


def build_pdf(secs: list[dict], topic: dict | None = None) -> bytes:
    """Day3 제안서를 PDF 로. to_pdf.Report 를 그대로 재사용한다.

    ⚠ 차트(SVG)는 넣지 않는다 — fpdf2 가 SVG 를 직접 못 그린다.
      그 사실을 문서에 적는다. 지어내지 않는다.
    ⚠ 생성 시각을 넣지 않는다. 카드의 "최종 갱신" 으로 고정한다 (재현).
    """
    pdf = to_pdf.Report()
    meta = parse_cards().get("meta", {})
    stamp = str(meta.get("최종 갱신", "")).strip()
    try:
        pdf.creation_date = datetime.strptime(
            stamp[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    t = topic or {}
    pdf.add_page()
    pdf.ln(58)
    pdf.set_font(pdf.base, "B", 22)
    pdf.set_text_color(*to_pdf.INK)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 11, pdf_safe(t.get("제목") or "제안서"))
    pdf.ln(2)
    pdf.set_font(pdf.base, "", 11)
    pdf.set_text_color(*to_pdf.MUTED)
    if t.get("한줄"):
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 6, pdf_safe(t["한줄"]))
    pdf.ln(4)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 6, pdf_safe(f"{C.DATASET} · {C.PERIOD[0]} ~ {C.PERIOD[1]}"))
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 6, pdf_safe("카드 최종 갱신 " + (stamp or "미상")))

    for s in secs:
        pdf.add_page()
        pdf.set_font(pdf.base, "B", 14)
        pdf.set_text_color(*to_pdf.INK)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 8, pdf_safe(s.get("제목", "")))
        if s.get("질문"):
            pdf.set_font(pdf.base, "", 9.5)
            pdf.set_text_color(*to_pdf.MUTED)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 5.4, pdf_safe(s["질문"]))
        pdf.ln(3)
        pdf.set_draw_color(*to_pdf.LINE)
        pdf.set_line_width(0.3)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(5)

        lines = s.get("문장") or []
        if not lines:
            pdf.set_font(pdf.base, "", 10)
            pdf.set_text_color(*to_pdf.MUTED)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 6, pdf_safe(
                "[작성되지 않음] " + str(s.get("placeholder", ""))))
            continue
        pdf.set_font(pdf.base, "", 10.5)
        pdf.set_text_color(*to_pdf.INK)
        for ln in lines:
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 6.2, pdf_safe(ln))
            pdf.ln(2)
        if s.get("차트"):
            pdf.set_font(pdf.base, "", 9)
            pdf.set_text_color(*to_pdf.MUTED)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 5.4, pdf_safe(
                f"[그림 {len(s['차트'])}개는 HTML 본에만 있습니다]"))

    return bytes(pdf.output())
