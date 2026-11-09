"""一键生成实验报告（Word）：把一次对话里的提问、智能体的操作步骤、回测指标、稳健性检验结论和分析整理成文档，
末尾留出"我的结论"由学生自己填写。学生可以直接拿去交作业。"""

from __future__ import annotations

import io
import json
import re
from datetime import datetime
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from sqlmodel import Session, select

from . import auth, services
from .db import Assignment, ChatMessage, ChatSession, ClassRoom, User, engine

BLUE = RGBColor(0x1E, 0x3A, 0x8A)
GREY = RGBColor(0x64, 0x74, 0x8B)


def _pct(v: Any) -> str:
    return "—" if v is None else f"{v * 100:.1f}%"


def _num(v: Any) -> str:
    return "—" if v is None else f"{v:.2f}"


def _font(doc: Document) -> None:
    st = doc.styles["Normal"]
    st.font.name = "微软雅黑"
    st.font.size = Pt(10.5)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")
    for name in ("Heading 1", "Heading 2", "Heading 3", "Title"):
        s = doc.styles[name]
        s.font.name = "微软雅黑"
        s.element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")
        s.font.color.rgb = BLUE


def _markdown(doc: Document, text: str) -> None:
    """把智能体回复里常见的 Markdown（标题、列表、加粗、表格）转成 Word 段落。"""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            i += 1
            continue
        if line.lstrip().startswith("|"):  # 表格
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                    rows.append(cells)
                i += 1
            if rows:
                n = max(len(r) for r in rows)
                t = doc.add_table(rows=len(rows), cols=n)
                t.style = "Light Grid Accent 1"
                for r, row in enumerate(rows):
                    for c in range(n):
                        t.cell(r, c).text = re.sub(r"\*\*(.+?)\*\*", r"\1", row[c] if c < len(row) else "")
            continue
        m = re.match(r"^(#{1,4})\s+(.*)", line)
        if m:
            doc.add_heading(re.sub(r"\*\*(.+?)\*\*", r"\1", m.group(2)), level=3)
            i += 1
            continue
        m = re.match(r"^\s*([-*•]|\d+[.、])\s+(.*)", line)
        para = doc.add_paragraph(style="List Bullet" if m and not m.group(1)[0].isdigit() else
                                 "List Number" if m else None)
        body = m.group(2) if m else line.lstrip("> ")
        for k, part in enumerate(re.split(r"\*\*(.+?)\*\*", body)):  # 奇数段是加粗内容
            run = para.add_run(part.replace("`", ""))
            run.bold = k % 2 == 1
        i += 1


def _metric_table(doc: Document, cards: list[dict[str, Any]]) -> None:
    head = ["回测", "调整的参数", "区间", "总收益", "年化", "最大回撤", "夏普", "胜率", "交易次数", "沪深300 年化"]
    t = doc.add_table(rows=1, cols=len(head))
    t.style = "Light Grid Accent 1"
    for c, h in enumerate(head):
        t.rows[0].cells[c].text = h
    for card in cards:
        m = card.get("metrics") or {}
        row = t.add_row().cells
        changed = card.get("changed") or {}
        vals = [card.get("title", ""), "，".join(f"{k}={v}" for k, v in changed.items()) or "默认", card.get("period", ""), _pct(m.get("total_return")), _pct(m.get("annual_return")),
                _pct(m.get("max_drawdown")), _num(m.get("sharpe")), _pct(m.get("win_rate")),
                str(m.get("trade_count", "—")), _pct(m.get("hs300_annual_return"))]
        for c, v in enumerate(vals):
            row[c].text = v


def build(session_id: str) -> tuple[str, bytes]:
    with Session(engine()) as s:
        cs = s.get(ChatSession, session_id)
        if not cs or (auth.enabled() and cs.user_id != auth.current_user_id()):
            raise services.NotFound("对话不存在")
        msgs = s.exec(select(ChatMessage).where(ChatMessage.session_id == cs.id).order_by(ChatMessage.id)).all()
        owner = s.get(User, cs.user_id) if cs.user_id else None
        room = s.get(ClassRoom, owner.class_id) if owner and owner.class_id else None
        hw = s.get(Assignment, cs.assignment_id) if cs.assignment_id else None

    doc = Document()
    _font(doc)
    title = doc.add_heading("量化策略实验报告", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    info = doc.add_paragraph()
    info.alignment = WD_ALIGN_PARAGRAPH.CENTER
    who = f"{owner.display_name or owner.username}" if owner else "（未登录使用）"
    run = info.add_run(f"实验主题：{cs.title}　　学生：{who}" + (f"　　班级：{room.name}" if room else "")
                       + f"　　生成时间：{datetime.now():%Y-%m-%d %H:%M}")
    run.font.color.rgb = GREY
    run.font.size = Pt(9.5)

    if hw:
        doc.add_heading("作业要求", level=1)
        doc.add_paragraph(f"{hw.title}" + (f"（截止 {hw.due}）" if hw.due else ""))
        if hw.task:
            doc.add_paragraph(hw.task)

    all_cards: list[dict] = []
    doc.add_heading("一、实验过程", level=1)
    n = 0
    for m in msgs:
        if m.role == "user":
            n += 1
            doc.add_heading(f"第 {n} 步：{m.content[:60]}{'…' if len(m.content) > 60 else ''}", level=2)
            if len(m.content) > 60:
                doc.add_paragraph(m.content)
            continue
        events = json.loads(m.events_json or "[]")
        steps = [e for e in events if e.get("kind") == "tool"]
        if steps:
            p = doc.add_paragraph()
            r = p.add_run("智能体执行的操作：")
            r.bold = True
            for e in steps:
                doc.add_paragraph(f"{'✓' if e.get('ok') else '✗'} {e.get('label', '')}"
                                  + ("" if e.get("ok") else f"（{e.get('error', '')}）"), style="List Bullet")
        cards = [e["card"] for e in steps if e.get("ok") and e.get("card", {}) and e["card"].get("kind") == "backtest"]
        if cards:
            all_cards += cards
            doc.add_paragraph().add_run("回测结果：").bold = True
            _metric_table(doc, cards)
        for e in steps:
            card = e.get("card") or {}
            if card.get("kind") == "robustness":
                doc.add_paragraph().add_run(f"稳健性检验（{card.get('metric_label', '')}，样本内 / 样本外以 {card.get('split')} 为界）：").bold = True
                for line in card.get("conclusions", []):
                    doc.add_paragraph(line, style="List Bullet")
        for e in events:
            if e.get("kind") == "phase" and e.get("name") == "reflect":
                doc.add_paragraph(f"【{e.get('label')}】{'目标已达成' if e.get('goal_met') else '尚未达成'}：{e.get('assessment', '')}")
        if m.content.strip():
            doc.add_paragraph().add_run("分析：").bold = True
            _markdown(doc, m.content.replace(services.DISCLAIMER, "").strip())

    if all_cards:
        doc.add_heading("二、全部回测汇总", level=1)
        _metric_table(doc, all_cards)

    doc.add_heading(("三" if all_cards else "二") + "、我的结论", level=1)
    hint = doc.add_paragraph("（请用自己的话回答：实验的假设是什么？结果支持还是否定了假设？为什么？有哪些局限（样本区间、过拟合、幸存者偏差、交易成本）？下一步想做什么实验？）")
    hint.runs[0].font.color.rgb = GREY
    for _ in range(6):
        doc.add_paragraph("")

    foot = doc.add_paragraph(services.DISCLAIMER)
    foot.runs[0].font.color.rgb = GREY
    foot.runs[0].font.size = Pt(9)
    buf = io.BytesIO()
    doc.save(buf)
    safe = re.sub(r'[\\/:*?"<>|\s]+', "_", cs.title)[:30] or "实验"
    return f"实验报告_{safe}.docx", buf.getvalue()
