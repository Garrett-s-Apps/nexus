"""
NEXUS Document Generator

Creates docx, pptx, and pdf files based on CEO natural language requests.
Uses Claude to generate content, then python-docx/python-pptx/reportlab
to create the actual files. Uploads to Slack.
"""

import os
import json
import tempfile
import anthropic
from typing import Any


def _load_key(key_name: str) -> str | None:
    try:
        with open(os.path.expanduser("~/.nexus/.env.keys")) as f:
            for line in f:
                line = line.strip()
                if line.startswith(key_name + "="):
                    return line.split("=", 1)[1]
    except FileNotFoundError:
        pass
    return os.environ.get(key_name)


def _get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=_load_key("ANTHROPIC_API_KEY"))


def _ask_claude(prompt: str, system: str = "") -> str:
    client = _get_client()
    msg = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=system or "You are a content generator for NEXUS. Respond with exactly what is requested, no preamble.",
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


# ============================================
# DOCX
# ============================================

def create_docx(title: str, request: str, output_dir: str = None) -> str:
    """Generate a Word document based on the request."""
    from docx import Document
    from docx.shared import Inches, Pt, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    content = _ask_claude(
        f"Generate the full content for a professional document.\n\n"
        f"Title: {title}\n"
        f"Request: {request}\n\n"
        f"Return the content as JSON with this structure:\n"
        f'{{"title": "...", "subtitle": "...", "sections": [{{"heading": "...", "body": "..."}}, ...]}}\n\n'
        f"Only return the JSON, nothing else.",
        system="You generate document content as structured JSON. No markdown, no code fences, just JSON."
    )

    try:
        # Strip markdown fences if present
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
        content = content.strip()
        data = json.loads(content)
    except json.JSONDecodeError:
        data = {
            "title": title,
            "subtitle": "",
            "sections": [{"heading": "Content", "body": content}],
        }

    doc = Document()

    # Title
    title_para = doc.add_heading(data.get("title", title), level=0)
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Subtitle
    if data.get("subtitle"):
        sub = doc.add_paragraph(data["subtitle"])
        sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
        sub.style.font.size = Pt(14)

    doc.add_paragraph("")

    # Sections
    for section in data.get("sections", []):
        if section.get("heading"):
            doc.add_heading(section["heading"], level=1)
        if section.get("body"):
            for para in section["body"].split("\n\n"):
                if para.strip():
                    doc.add_paragraph(para.strip())

    output_dir = output_dir or tempfile.mkdtemp()
    safe_title = title[:50].replace(" ", "_").replace("/", "_")
    filepath = os.path.join(output_dir, f"{safe_title}.docx")
    doc.save(filepath)
    return filepath


# ============================================
# PPTX
# ============================================

def create_pptx(title: str, request: str, output_dir: str = None) -> str:
    """Generate a PowerPoint presentation based on the request."""
    from pptx import Presentation
    from pptx.util import Inches, Pt, Emu
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN

    content = _ask_claude(
        f"Generate content for a professional slide deck.\n\n"
        f"Title: {title}\n"
        f"Request: {request}\n\n"
        f"Return as JSON with this structure:\n"
        f'{{"title": "...", "subtitle": "...", "slides": [{{"title": "...", "bullets": ["...", "..."], "notes": "..."}}, ...]}}\n\n'
        f"Generate 6-12 slides. Only return the JSON, nothing else.",
        system="You generate presentation content as structured JSON. No markdown, no code fences, just JSON."
    )

    try:
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
        content = content.strip()
        data = json.loads(content)
    except json.JSONDecodeError:
        data = {
            "title": title,
            "subtitle": request,
            "slides": [{"title": "Content", "bullets": [request], "notes": ""}],
        }

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    # Color scheme
    bg_color = RGBColor(0x1A, 0x1A, 0x2E)
    accent_color = RGBColor(0x00, 0xD2, 0xFF)
    text_color = RGBColor(0xFF, 0xFF, 0xFF)
    subtitle_color = RGBColor(0xAA, 0xAA, 0xCC)

    def set_slide_bg(slide, color):
        background = slide.background
        fill = background.fill
        fill.solid()
        fill.fore_color.rgb = color

    # Title slide
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    set_slide_bg(slide, bg_color)

    txBox = slide.shapes.add_textbox(Inches(1), Inches(2.5), Inches(11), Inches(1.5))
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = data.get("title", title)
    p.font.size = Pt(44)
    p.font.bold = True
    p.font.color.rgb = text_color
    p.alignment = PP_ALIGN.CENTER

    if data.get("subtitle"):
        txBox2 = slide.shapes.add_textbox(Inches(1), Inches(4.2), Inches(11), Inches(1))
        tf2 = txBox2.text_frame
        tf2.word_wrap = True
        p2 = tf2.paragraphs[0]
        p2.text = data["subtitle"]
        p2.font.size = Pt(20)
        p2.font.color.rgb = subtitle_color
        p2.alignment = PP_ALIGN.CENTER

    # Accent line
    from pptx.util import Emu
    line = slide.shapes.add_shape(
        1, Inches(4), Inches(4), Inches(5), Pt(3)
    )
    line.fill.solid()
    line.fill.fore_color.rgb = accent_color
    line.line.fill.background()

    # Content slides
    for slide_data in data.get("slides", []):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        set_slide_bg(slide, bg_color)

        # Title
        txBox = slide.shapes.add_textbox(Inches(0.8), Inches(0.5), Inches(11.5), Inches(1))
        tf = txBox.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = slide_data.get("title", "")
        p.font.size = Pt(32)
        p.font.bold = True
        p.font.color.rgb = accent_color

        # Accent underline
        line = slide.shapes.add_shape(
            1, Inches(0.8), Inches(1.4), Inches(2), Pt(3)
        )
        line.fill.solid()
        line.fill.fore_color.rgb = accent_color
        line.line.fill.background()

        # Bullets
        bullets = slide_data.get("bullets", [])
        if bullets:
            txBox = slide.shapes.add_textbox(Inches(1), Inches(1.8), Inches(11), Inches(5))
            tf = txBox.text_frame
            tf.word_wrap = True

            for i, bullet in enumerate(bullets):
                if i == 0:
                    p = tf.paragraphs[0]
                else:
                    p = tf.add_paragraph()
                p.text = f"▸  {bullet}"
                p.font.size = Pt(20)
                p.font.color.rgb = text_color
                p.space_after = Pt(12)

        # Speaker notes
        if slide_data.get("notes"):
            slide.notes_slide.notes_text_frame.text = slide_data["notes"]

    output_dir = output_dir or tempfile.mkdtemp()
    safe_title = title[:50].replace(" ", "_").replace("/", "_")
    filepath = os.path.join(output_dir, f"{safe_title}.pptx")
    prs.save(filepath)
    return filepath


# ============================================
# PDF
# ============================================

def create_pdf(title: str, request: str, output_dir: str = None) -> str:
    """Generate a PDF document based on the request."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

    content = _ask_claude(
        f"Generate the full content for a professional document.\n\n"
        f"Title: {title}\n"
        f"Request: {request}\n\n"
        f"Return as JSON with this structure:\n"
        f'{{"title": "...", "subtitle": "...", "sections": [{{"heading": "...", "body": "..."}}, ...]}}\n\n'
        f"Only return the JSON, nothing else.",
        system="You generate document content as structured JSON. No markdown, no code fences, just JSON."
    )

    try:
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
        content = content.strip()
        data = json.loads(content)
    except json.JSONDecodeError:
        data = {
            "title": title,
            "subtitle": "",
            "sections": [{"heading": "Content", "body": content}],
        }

    output_dir = output_dir or tempfile.mkdtemp()
    safe_title = title[:50].replace(" ", "_").replace("/", "_")
    filepath = os.path.join(output_dir, f"{safe_title}.pdf")

    doc = SimpleDocTemplate(
        filepath,
        pagesize=letter,
        rightMargin=inch,
        leftMargin=inch,
        topMargin=inch,
        bottomMargin=inch,
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="DocTitle",
        parent=styles["Title"],
        fontSize=28,
        spaceAfter=6,
        textColor=HexColor("#1a1a2e"),
    ))
    styles.add(ParagraphStyle(
        name="DocSubtitle",
        parent=styles["Normal"],
        fontSize=14,
        spaceAfter=20,
        textColor=HexColor("#666688"),
        alignment=1,
    ))
    styles.add(ParagraphStyle(
        name="SectionHead",
        parent=styles["Heading1"],
        fontSize=18,
        spaceBefore=16,
        spaceAfter=8,
        textColor=HexColor("#00d2ff"),
    ))
    styles.add(ParagraphStyle(
        name="BodyText2",
        parent=styles["Normal"],
        fontSize=11,
        spaceAfter=8,
        leading=16,
    ))

    story = []
    story.append(Paragraph(data.get("title", title), styles["DocTitle"]))

    if data.get("subtitle"):
        story.append(Paragraph(data["subtitle"], styles["DocSubtitle"]))

    story.append(Spacer(1, 12))

    for section in data.get("sections", []):
        if section.get("heading"):
            story.append(Paragraph(section["heading"], styles["SectionHead"]))
        if section.get("body"):
            for para in section["body"].split("\n\n"):
                if para.strip():
                    # Escape XML-sensitive characters
                    safe = para.strip().replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    story.append(Paragraph(safe, styles["BodyText2"]))

    doc.build(story)
    return filepath


# ============================================
# DISPATCHER
# ============================================

def detect_doc_request(message: str) -> dict | None:
    """Check if a message is asking for a document. Returns format info or None."""
    msg_lower = message.lower()

    format_map = {
        "docx": ["docx", "word doc", "word document", ".docx"],
        "pptx": ["pptx", "powerpoint", "slide deck", "slides", "presentation", ".pptx", "pitch deck"],
        "pdf": ["pdf", ".pdf"],
    }

    for fmt, keywords in format_map.items():
        for kw in keywords:
            if kw in msg_lower:
                return {"format": fmt}

    # Check for generic "document" or "report" — default to docx
    if any(w in msg_lower for w in ["document", "report", "memo", "letter", "write up", "writeup", "one-pager"]):
        return {"format": "docx"}

    return None


async def generate_document(message: str, doc_info: dict) -> dict:
    """Generate a document and return the filepath."""
    import asyncio

    fmt = doc_info["format"]

    # Extract a title from the message
    title = _ask_claude(
        f"Extract a short document title (3-8 words) from this request: {message}\n\nReturn only the title, nothing else.",
        system="You extract concise titles. Return only the title text."
    ).strip().strip('"').strip("'")

    output_dir = os.path.expanduser("~/.nexus/documents")
    os.makedirs(output_dir, exist_ok=True)

    # Run document creation in a thread pool (they're sync)
    loop = asyncio.get_event_loop()

    if fmt == "docx":
        filepath = await loop.run_in_executor(None, create_docx, title, message, output_dir)
    elif fmt == "pptx":
        filepath = await loop.run_in_executor(None, create_pptx, title, message, output_dir)
    elif fmt == "pdf":
        filepath = await loop.run_in_executor(None, create_pdf, title, message, output_dir)
    else:
        return {"error": f"Unsupported format: {fmt}"}

    return {
        "filepath": filepath,
        "title": title,
        "format": fmt,
        "filename": os.path.basename(filepath),
    }
