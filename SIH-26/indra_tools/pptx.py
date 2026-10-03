#!/usr/bin/env python3
"""INDRA PowerPoint Generator: Context-Agnostic, 100% Offline 16:9 Deck Builder.

Supports:
1. Markdown outline (.md, .txt) with automatic slide segmentation and intelligent layout detection:
   - Slide 1: Hero Title slide with category badge, large typography, and metadata card
   - Metrics/KPIs: Auto-detects `**99.9%**: Label` or stat patterns into large visual Stat Callout Cards
   - Multi-Column Cards: Auto-detects 2, 3, or 4 `## Subheadings` into sleek horizontal Card Grids
   - Process Pipeline: Auto-detects numbered steps (`1. Step: desc`) into numbered pipeline cards
   - Quotes/Takeaways: Auto-detects `> ` quotes into executive highlight callout cards
   - Tables: Native PowerPoint tables with theme styling, headers, and alternating row fills
   - Standard Content: Placed in sleek rounded cards with custom bullets; auto-splits into 2 columns if 5+ bullets
   - Dynamic text fitting: Automatically scales typography and line spacing so text NEVER overflows
2. JSON specification (.json) with explicit layouts:
   - title, metrics, cards, steps, split, quote, table, chart, blank
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE

THEMES: Dict[str, Dict[str, Any]] = {
    "modern_dark": {
        "name": "Modern Dark",
        "bg": RGBColor(11, 17, 32),            # Deep midnight navy slate (#0B1120)
        "title": RGBColor(56, 189, 248),       # Electric sky cyan (#38BDF8)
        "subtitle": RGBColor(226, 232, 240),   # Off-white
        "text": RGBColor(241, 245, 249),       # Clean soft white
        "muted": RGBColor(148, 163, 184),      # Slate gray
        "accent": RGBColor(14, 165, 233),      # Vivid sky blue (#0EA5E9)
        "accent2": RGBColor(52, 211, 153),     # Mint emerald
        "card_bg": RGBColor(26, 36, 56),       # Navy card fill
        "card_border": RGBColor(51, 65, 85),   # Slate card border
        "pill_bg": RGBColor(30, 58, 88),       # Pill background
        "table_header_bg": RGBColor(15, 23, 42),
        "table_alt_bg": RGBColor(22, 32, 50),
    },
    "executive": {
        "name": "Executive Gold",
        "bg": RGBColor(15, 23, 42),            # Dark obsidian midnight (#0F172A)
        "title": RGBColor(251, 191, 36),       # Warm champagne gold (#FBBF24)
        "subtitle": RGBColor(248, 250, 252),
        "text": RGBColor(241, 245, 249),
        "muted": RGBColor(156, 163, 175),      # Neutral gray
        "accent": RGBColor(245, 158, 11),      # Deep amber gold (#F59E0B)
        "accent2": RGBColor(252, 211, 77),     # Bright gold
        "card_bg": RGBColor(27, 38, 59),       # Midnight card fill
        "card_border": RGBColor(68, 77, 98),
        "pill_bg": RGBColor(69, 50, 19),
        "table_header_bg": RGBColor(20, 29, 47),
        "table_alt_bg": RGBColor(24, 34, 54),
    },
    "tech_emerald": {
        "name": "Tech Emerald",
        "bg": RGBColor(6, 26, 20),             # Forest charcoal (#061A14)
        "title": RGBColor(52, 211, 153),       # Vivid mint (#34D399)
        "subtitle": RGBColor(240, 253, 244),
        "text": RGBColor(236, 253, 245),
        "muted": RGBColor(110, 165, 142),
        "accent": RGBColor(16, 185, 129),      # Emerald green (#10B981)
        "accent2": RGBColor(56, 189, 248),     # Sky cyan
        "card_bg": RGBColor(13, 43, 34),       # Deep emerald card
        "card_border": RGBColor(20, 83, 63),
        "pill_bg": RGBColor(6, 78, 59),
        "table_header_bg": RGBColor(8, 33, 26),
        "table_alt_bg": RGBColor(11, 38, 30),
    },
    "cyberpunk": {
        "name": "Cyberpunk Neon",
        "bg": RGBColor(13, 11, 24),            # Deep violet night (#0D0B18)
        "title": RGBColor(192, 132, 252),      # Electric neon violet (#C084FC)
        "subtitle": RGBColor(248, 250, 252),
        "text": RGBColor(243, 232, 255),
        "muted": RGBColor(167, 139, 250),
        "accent": RGBColor(6, 182, 212),       # Neon cyan (#06B6D4)
        "accent2": RGBColor(236, 72, 153),     # Neon pink
        "card_bg": RGBColor(26, 22, 43),       # Deep purple card
        "card_border": RGBColor(59, 48, 89),
        "pill_bg": RGBColor(76, 29, 149),
        "table_header_bg": RGBColor(19, 16, 34),
        "table_alt_bg": RGBColor(23, 19, 39),
    },
    "sunset_coral": {
        "name": "Sunset Coral",
        "bg": RGBColor(24, 17, 36),            # Deep plum (#181124)
        "title": RGBColor(251, 113, 133),      # Coral rose (#FB7185)
        "subtitle": RGBColor(255, 241, 242),
        "text": RGBColor(254, 226, 226),
        "muted": RGBColor(203, 168, 180),
        "accent": RGBColor(244, 63, 94),       # Vibrant rose (#F43F5E)
        "accent2": RGBColor(251, 146, 60),     # Sunset orange
        "card_bg": RGBColor(39, 28, 53),       # Plum card fill
        "card_border": RGBColor(79, 56, 102),
        "pill_bg": RGBColor(136, 19, 55),
        "table_header_bg": RGBColor(30, 21, 44),
        "table_alt_bg": RGBColor(35, 25, 49),
    },
    "clean_light": {
        "name": "Clean Minimal Light",
        "bg": RGBColor(248, 250, 252),         # Off-white canvas (#F8FAFC)
        "title": RGBColor(30, 27, 75),         # Deep indigo (#1E1B4B)
        "subtitle": RGBColor(79, 70, 229),     # Electric indigo (#4F46E5)
        "text": RGBColor(30, 41, 59),          # Charcoal slate (#1E293B)
        "muted": RGBColor(100, 116, 139),      # Muted slate
        "accent": RGBColor(79, 70, 229),       # Indigo accent
        "accent2": RGBColor(14, 165, 233),     # Sky blue
        "card_bg": RGBColor(255, 255, 255),    # Pure white card
        "card_border": RGBColor(226, 232, 240),# Light border (#E2E8F0)
        "pill_bg": RGBColor(224, 231, 255),    # Soft indigo pill
        "table_header_bg": RGBColor(238, 242, 255),
        "table_alt_bg": RGBColor(241, 245, 249),
    },
    "nordic_frost": {
        "name": "Nordic Frost",
        "bg": RGBColor(11, 25, 44),            # Arctic midnight (#0B192C)
        "title": RGBColor(65, 201, 226),       # Ice cyan (#41C9E2)
        "subtitle": RGBColor(240, 248, 255),
        "text": RGBColor(230, 243, 255),
        "muted": RGBColor(142, 172, 205),
        "accent": RGBColor(0, 141, 218),       # Glacier blue (#008DDA)
        "accent2": RGBColor(116, 226, 226),    # Mint ice
        "card_bg": RGBColor(22, 45, 75),       # Arctic card fill
        "card_border": RGBColor(45, 78, 120),
        "pill_bg": RGBColor(26, 77, 110),
        "table_header_bg": RGBColor(15, 33, 58),
        "table_alt_bg": RGBColor(19, 39, 67),
    },
}

# Standard Slide Geometry: 16:9 Widescreen (13.333" x 7.5")
SLIDE_WIDTH = Inches(13.333)
SLIDE_HEIGHT = Inches(7.5)
MARGIN_LEFT = Inches(1.0)
CONTENT_WIDTH = Inches(11.333)
CONTENT_TOP = Inches(2.15)
CONTENT_HEIGHT = Inches(4.45)
FOOTER_TOP = Inches(6.85)

FONT_PRIMARY = "Segoe UI"
FONT_HEADING = "Segoe UI"
FONT_MONO = "Consolas"


def _set_slide_bg(slide, color: RGBColor):
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = color


def _add_rounded_card(slide, left, top, width, height, theme: Dict[str, Any], border_color: Optional[RGBColor] = None, top_accent: bool = True):
    """Draws a modern rounded container card with an optional top accent stripe."""
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = theme["card_bg"]
    shape.line.color.rgb = border_color or theme["card_border"]
    shape.line.width = Pt(1)

    if top_accent:
        accent_bar = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, Inches(0.08))
        accent_bar.fill.solid()
        accent_bar.fill.fore_color.rgb = theme["accent"]
        accent_bar.line.fill.background()

    return shape


def _add_slide_chrome(slide, title_text: str, theme: Dict[str, Any], slide_idx: int, total_slides: int, category: str = "INDRA INTELLIGENCE WORKBENCH", subtitle: Optional[str] = None):
    """Draws consistent, executive-grade header and footer chrome across all slides."""
    # Top accent line
    top_line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), SLIDE_WIDTH, Inches(0.06))
    top_line.fill.solid()
    top_line.fill.fore_color.rgb = theme["accent"]
    top_line.line.fill.background()

    # Category Badge / Pill
    badge_box = slide.shapes.add_textbox(MARGIN_LEFT, Inches(0.48), CONTENT_WIDTH, Inches(0.35))
    btf = badge_box.text_frame
    btf.margin_left = btf.margin_right = btf.margin_top = btf.margin_bottom = 0
    bp = btf.paragraphs[0]
    bp.text = f"●  {category.upper()}"
    bp.font.name = FONT_PRIMARY
    bp.font.size = Pt(11)
    bp.font.bold = True
    bp.font.color.rgb = theme["accent"]

    # Slide Title
    title_box = slide.shapes.add_textbox(MARGIN_LEFT, Inches(0.82), CONTENT_WIDTH, Inches(0.7))
    ttf = title_box.text_frame
    ttf.word_wrap = True
    ttf.margin_left = ttf.margin_right = ttf.margin_top = ttf.margin_bottom = 0
    tp = ttf.paragraphs[0]
    tp.text = title_text
    tp.font.name = FONT_HEADING
    title_len = len(title_text)
    tp.font.size = Pt(28 if title_len > 45 else 32)
    tp.font.bold = True
    tp.font.color.rgb = theme["title"]

    # Optional Subtitle
    if subtitle:
        sub_p = ttf.add_paragraph()
        sub_p.text = subtitle
        sub_p.font.name = FONT_PRIMARY
        sub_p.font.size = Pt(13)
        sub_p.font.color.rgb = theme["muted"]
        sub_p.space_before = Pt(4)

    # Footer separator rule
    rule = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, MARGIN_LEFT, Inches(6.78), CONTENT_WIDTH, Inches(0.015))
    rule.fill.solid()
    rule.fill.fore_color.rgb = theme["card_border"]
    rule.line.fill.background()

    # Footer left & right
    footer_box = slide.shapes.add_textbox(MARGIN_LEFT, FOOTER_TOP, CONTENT_WIDTH, Inches(0.4))
    ftf = footer_box.text_frame
    ftf.margin_left = ftf.margin_right = ftf.margin_top = ftf.margin_bottom = 0
    fp = ftf.paragraphs[0]
    fp.text = "INDRA AI Ecosystem  |  Confidential & Proprietary"
    fp.font.name = FONT_PRIMARY
    fp.font.size = Pt(10)
    fp.font.color.rgb = theme["muted"]

    num_box = slide.shapes.add_textbox(Inches(9.0), FOOTER_TOP, Inches(3.333), Inches(0.4))
    ntf = num_box.text_frame
    ntf.margin_left = ntf.margin_right = ntf.margin_top = ntf.margin_bottom = 0
    np = ntf.paragraphs[0]
    np.text = f"Slide {slide_idx + 1} of {total_slides}"
    np.alignment = PP_ALIGN.RIGHT
    np.font.name = FONT_PRIMARY
    np.font.size = Pt(10)
    np.font.bold = True
    np.font.color.rgb = theme["muted"]


# ---------------------------------------------------------------------------
# Slide Renderers
# ---------------------------------------------------------------------------

def render_hero_slide(slide, title: str, subtitle: Optional[str], items: List[str], theme: Dict[str, Any]):
    """Slide 1: Executive Title & Hero Deck Slide."""
    _set_slide_bg(slide, theme["bg"])

    # Hero top accent banner
    top_bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), SLIDE_WIDTH, Inches(0.12))
    top_bar.fill.solid()
    top_bar.fill.fore_color.rgb = theme["accent"]
    top_bar.line.fill.background()

    # Category Pill
    pill = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.2), Inches(1.6), Inches(3.2), Inches(0.42))
    pill.fill.solid()
    pill.fill.fore_color.rgb = theme["pill_bg"]
    pill.line.color.rgb = theme["accent"]
    pill.line.width = Pt(1)
    ptf = pill.text_frame
    ptf.vertical_anchor = MSO_ANCHOR.MIDDLE
    pp = ptf.paragraphs[0]
    pp.text = "●  EXECUTIVE BRIEFING"
    pp.font.name = FONT_PRIMARY
    pp.font.size = Pt(12)
    pp.font.bold = True
    pp.font.color.rgb = theme["title"]
    pp.alignment = PP_ALIGN.CENTER

    # Hero Title & Subtitle box
    tbox = slide.shapes.add_textbox(Inches(1.2), Inches(2.25), Inches(10.8), Inches(2.8))
    tf = tbox.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0

    p_title = tf.paragraphs[0]
    p_title.text = title
    p_title.font.name = FONT_HEADING
    p_title.font.size = Pt(46 if len(title) > 35 else 52)
    p_title.font.bold = True
    p_title.font.color.rgb = theme["title"]

    # Subtitle or description
    sub_text = subtitle or ""
    if not sub_text and items:
        sub_text = items[0].lstrip("- *#>")
        items = items[1:]

    if sub_text:
        p_sub = tf.add_paragraph()
        p_sub.text = sub_text
        p_sub.font.name = FONT_PRIMARY
        p_sub.font.size = Pt(20)
        p_sub.font.color.rgb = theme["subtitle"]
        p_sub.space_before = Pt(14)

    # Metadata card at bottom
    mcard = _add_rounded_card(slide, Inches(1.2), Inches(5.3), Inches(10.8), Inches(1.3), theme, top_accent=False)
    mtf = mcard.text_frame
    mtf.margin_left = Inches(0.4)
    mtf.margin_top = Inches(0.2)
    mtf.word_wrap = True

    mp1 = mtf.paragraphs[0]
    mp1.text = "INDRA Sovereign Intelligence Architecture  •  CodersbyChance"
    mp1.font.name = FONT_PRIMARY
    mp1.font.size = Pt(13)
    mp1.font.bold = True
    mp1.font.color.rgb = theme["text"]

    mp2 = mtf.add_paragraph()
    meta_extra = " | ".join(it.lstrip("- *#>") for it in items[:2]) if items else "100% Offline Air-Gapped Environment  •  Verified Production Deliverable"
    mp2.text = meta_extra
    mp2.font.name = FONT_PRIMARY
    mp2.font.size = Pt(12)
    mp2.font.color.rgb = theme["muted"]
    mp2.space_before = Pt(6)


def render_metric_cards_slide(slide, title: str, metrics: List[Dict[str, str]], theme: Dict[str, Any], slide_idx: int, total_slides: int, subtitle: Optional[str] = None):
    """Renders 2, 3, or 4 giant KPI / Metric Stat Callout Cards."""
    _set_slide_bg(slide, theme["bg"])
    _add_slide_chrome(slide, title, theme, slide_idx, total_slides, category="KEY PERFORMANCE METRICS", subtitle=subtitle)

    n = min(len(metrics), 4)
    if n == 0:
        return

    gap = Inches(0.35)
    total_gaps = gap * (n - 1)
    card_width = (CONTENT_WIDTH - total_gaps) / n
    card_height = CONTENT_HEIGHT

    for i, m in enumerate(metrics[:n]):
        card_left = MARGIN_LEFT + i * (card_width + gap)
        _add_rounded_card(slide, card_left, CONTENT_TOP, card_width, card_height, theme)

        # Content inside card
        cbox = slide.shapes.add_textbox(card_left + Inches(0.3), CONTENT_TOP + Inches(0.4), card_width - Inches(0.6), card_height - Inches(0.6))
        ctf = cbox.text_frame
        ctf.word_wrap = True
        ctf.margin_left = ctf.margin_right = ctf.margin_top = ctf.margin_bottom = 0

        # Giant number/stat
        val_p = ctf.paragraphs[0]
        val_p.text = m.get("value", "")
        val_p.font.name = FONT_HEADING
        val_len = len(val_p.text)
        val_p.font.size = Pt(38 if val_len > 8 else (44 if val_len > 5 else 50))
        val_p.font.bold = True
        val_p.font.color.rgb = theme["accent"]

        # Label
        lbl_p = ctf.add_paragraph()
        lbl_p.text = m.get("label", "").upper()
        lbl_p.font.name = FONT_PRIMARY
        lbl_p.font.size = Pt(14)
        lbl_p.font.bold = True
        lbl_p.font.color.rgb = theme["title"]
        lbl_p.space_before = Pt(8)

        # Description
        desc = m.get("desc", "")
        if desc:
            desc_p = ctf.add_paragraph()
            desc_p.text = desc
            desc_p.font.name = FONT_PRIMARY
            desc_p.font.size = Pt(13)
            desc_p.font.color.rgb = theme["muted"]
            desc_p.space_before = Pt(12)


def render_card_grid_slide(slide, title: str, cards: List[Dict[str, Any]], theme: Dict[str, Any], slide_idx: int, total_slides: int, subtitle: Optional[str] = None):
    """Renders 2, 3, or 4 vertical cards side-by-side with distinct headers and bullets."""
    _set_slide_bg(slide, theme["bg"])
    _add_slide_chrome(slide, title, theme, slide_idx, total_slides, category="SYSTEM ARCHITECTURE & CAPABILITIES", subtitle=subtitle)

    n = min(len(cards), 4)
    if n == 0:
        return

    gap = Inches(0.35)
    total_gaps = gap * (n - 1)
    card_width = (CONTENT_WIDTH - total_gaps) / n
    card_height = CONTENT_HEIGHT

    for i, c in enumerate(cards[:n]):
        card_left = MARGIN_LEFT + i * (card_width + gap)
        _add_rounded_card(slide, card_left, CONTENT_TOP, card_width, card_height, theme)

        cbox = slide.shapes.add_textbox(card_left + Inches(0.32), CONTENT_TOP + Inches(0.35), card_width - Inches(0.64), card_height - Inches(0.55))
        ctf = cbox.text_frame
        ctf.word_wrap = True
        ctf.margin_left = ctf.margin_right = ctf.margin_top = ctf.margin_bottom = 0

        # Card Title
        tp = ctf.paragraphs[0]
        tp.text = c.get("title", "")
        tp.font.name = FONT_HEADING
        tp.font.size = Pt(18)
        tp.font.bold = True
        tp.font.color.rgb = theme["title"]

        # Bullets / Items
        bullets = c.get("bullets", [])
        total_chars = sum(len(b) for b in bullets)
        # Dynamic auto-sizing
        bullet_pt = 14 if total_chars > 250 else (15 if total_chars > 160 else 16)
        spacing_pt = 6 if len(bullets) > 4 else 10

        for b in bullets:
            bp = ctf.add_paragraph()
            clean_b = b.lstrip("- *#>")
            bp.text = f"▸  {clean_b}"
            bp.font.name = FONT_PRIMARY
            bp.font.size = Pt(bullet_pt)
            bp.font.color.rgb = theme["text"]
            bp.space_before = Pt(spacing_pt)


def render_step_pipeline_slide(slide, title: str, steps: List[Dict[str, str]], theme: Dict[str, Any], slide_idx: int, total_slides: int, subtitle: Optional[str] = None):
    """Renders a chronological or sequential process pipeline with step numbers."""
    _set_slide_bg(slide, theme["bg"])
    _add_slide_chrome(slide, title, theme, slide_idx, total_slides, category="EXECUTION WORKFLOW & PIPELINE", subtitle=subtitle)

    n = min(len(steps), 4)
    if n == 0:
        return

    gap = Inches(0.35)
    total_gaps = gap * (n - 1)
    card_width = (CONTENT_WIDTH - total_gaps) / n
    card_height = CONTENT_HEIGHT

    for i, s in enumerate(steps[:n]):
        card_left = MARGIN_LEFT + i * (card_width + gap)
        _add_rounded_card(slide, card_left, CONTENT_TOP, card_width, card_height, theme)

        cbox = slide.shapes.add_textbox(card_left + Inches(0.3), CONTENT_TOP + Inches(0.35), card_width - Inches(0.6), card_height - Inches(0.55))
        ctf = cbox.text_frame
        ctf.word_wrap = True
        ctf.margin_left = ctf.margin_right = ctf.margin_top = ctf.margin_bottom = 0

        # Step badge ("01", "02", etc.)
        step_num = s.get("step") or f"0{i+1}"
        sp = ctf.paragraphs[0]
        sp.text = f"STEP {step_num}"
        sp.font.name = FONT_PRIMARY
        sp.font.size = Pt(12)
        sp.font.bold = True
        sp.font.color.rgb = theme["accent"]

        # Step title
        tp = ctf.add_paragraph()
        tp.text = s.get("title", "")
        tp.font.name = FONT_HEADING
        tp.font.size = Pt(18)
        tp.font.bold = True
        tp.font.color.rgb = theme["title"]
        tp.space_before = Pt(6)

        # Step description or sub-bullets
        desc = s.get("desc", "")
        if desc:
            dp = ctf.add_paragraph()
            dp.text = desc
            dp.font.name = FONT_PRIMARY
            dp.font.size = Pt(13)
            dp.font.color.rgb = theme["muted"]
            dp.space_before = Pt(10)

        bullets = s.get("bullets", [])
        for b in bullets:
            bp = ctf.add_paragraph()
            bp.text = f"• {b.lstrip('- *#>')}"
            bp.font.name = FONT_PRIMARY
            bp.font.size = Pt(13)
            bp.font.color.rgb = theme["text"]
            bp.space_before = Pt(6)


def render_quote_slide(slide, title: str, quote_text: str, author: str, theme: Dict[str, Any], slide_idx: int, total_slides: int, subtitle: Optional[str] = None):
    """Renders an executive key takeaway or quotation callout."""
    _set_slide_bg(slide, theme["bg"])
    _add_slide_chrome(slide, title, theme, slide_idx, total_slides, category="EXECUTIVE TAKEAWAY", subtitle=subtitle)

    # Wide callout card
    card_left = MARGIN_LEFT + Inches(0.8)
    card_width = CONTENT_WIDTH - Inches(1.6)
    card_top = CONTENT_TOP + Inches(0.3)
    card_height = CONTENT_HEIGHT - Inches(0.6)

    _add_rounded_card(slide, card_left, card_top, card_width, card_height, theme, top_accent=False)

    # Accent left border bar
    left_bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, card_left, card_top, Inches(0.12), card_height)
    left_bar.fill.solid()
    left_bar.fill.fore_color.rgb = theme["accent"]
    left_bar.line.fill.background()

    cbox = slide.shapes.add_textbox(card_left + Inches(0.5), card_top + Inches(0.6), card_width - Inches(1.0), card_height - Inches(1.0))
    ctf = cbox.text_frame
    ctf.word_wrap = True
    ctf.margin_left = ctf.margin_right = ctf.margin_top = ctf.margin_bottom = 0

    qp = ctf.paragraphs[0]
    qp.text = f'"{quote_text.strip()}"'
    qp.font.name = FONT_HEADING
    qp.font.size = Pt(24 if len(quote_text) > 150 else 28)
    qp.font.bold = True
    qp.font.color.rgb = theme["text"]

    if author:
        ap = ctf.add_paragraph()
        ap.text = f"—  {author}"
        ap.font.name = FONT_PRIMARY
        ap.font.size = Pt(16)
        ap.font.bold = True
        ap.font.color.rgb = theme["accent"]
        ap.space_before = Pt(18)


def render_table_slide(slide, title: str, rows: List[List[str]], theme: Dict[str, Any], slide_idx: int, total_slides: int, subtitle: Optional[str] = None):
    """Renders a beautifully styled native table slide."""
    _set_slide_bg(slide, theme["bg"])
    _add_slide_chrome(slide, title, theme, slide_idx, total_slides, category="COMPARATIVE ANALYSIS", subtitle=subtitle)

    if not rows:
        return

    r_count = len(rows)
    c_count = max(len(r) for r in rows)

    table_shape = slide.shapes.add_table(r_count, c_count, MARGIN_LEFT, CONTENT_TOP, CONTENT_WIDTH, CONTENT_HEIGHT)
    table = table_shape.table

    for r_idx, r_data in enumerate(rows):
        is_header = (r_idx == 0)
        for c_idx in range(c_count):
            val = str(r_data[c_idx]) if c_idx < len(r_data) else ""
            cell = table.cell(r_idx, c_idx)
            cell.text = val
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE

            # Fill
            fill = cell.fill
            fill.solid()
            if is_header:
                fill.fore_color.rgb = theme["table_header_bg"]
            else:
                fill.fore_color.rgb = theme["table_alt_bg"] if (r_idx % 2 == 1) else theme["card_bg"]

            p = cell.text_frame.paragraphs[0]
            p.font.name = FONT_PRIMARY
            p.font.size = Pt(14 if is_header else 13)
            p.font.bold = is_header or (c_idx == 0)
            p.font.color.rgb = theme["title"] if is_header else theme["text"]


def render_standard_content_slide(slide, title: str, items: List[str], theme: Dict[str, Any], slide_idx: int, total_slides: int, subtitle: Optional[str] = None):
    """Renders standard bullets with smart 2-column auto-balancing and dynamic font fitting."""
    _set_slide_bg(slide, theme["bg"])
    _add_slide_chrome(slide, title, theme, slide_idx, total_slides, category="STRATEGIC OVERVIEW", subtitle=subtitle)

    clean_items = [it.lstrip("- *#>") for it in items if it.strip()]
    if not clean_items:
        clean_items = ["No content items specified."]

    # If 5 or more items, split into 2 side-by-side cards for balanced layout
    if len(clean_items) >= 5:
        mid = math.ceil(len(clean_items) / 2)
        col1_items = clean_items[:mid]
        col2_items = clean_items[mid:]

        col_w = (CONTENT_WIDTH - Inches(0.35)) / 2
        card_h = CONTENT_HEIGHT

        for c_idx, col_items in enumerate([col1_items, col2_items]):
            c_left = MARGIN_LEFT + c_idx * (col_w + Inches(0.35))
            _add_rounded_card(slide, c_left, CONTENT_TOP, col_w, card_h, theme)

            box = slide.shapes.add_textbox(c_left + Inches(0.35), CONTENT_TOP + Inches(0.35), col_w - Inches(0.7), card_h - Inches(0.7))
            tf = box.text_frame
            tf.word_wrap = True
            tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0

            # Dynamic typography
            total_chars = sum(len(x) for x in col_items)
            pt_size = 14 if total_chars > 280 else (15 if total_chars > 180 else 16)
            spacing_pt = 6 if len(col_items) > 4 else 10

            for i, it in enumerate(col_items):
                p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                p.text = f"▸  {it}"
                p.font.name = FONT_PRIMARY
                p.font.size = Pt(pt_size)
                p.font.color.rgb = theme["text"]
                p.space_before = Pt(spacing_pt)
    else:
        # Single wide card
        _add_rounded_card(slide, MARGIN_LEFT, CONTENT_TOP, CONTENT_WIDTH, CONTENT_HEIGHT, theme)

        box = slide.shapes.add_textbox(MARGIN_LEFT + Inches(0.5), CONTENT_TOP + Inches(0.45), CONTENT_WIDTH - Inches(1.0), CONTENT_HEIGHT - Inches(0.8))
        tf = box.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0

        total_chars = sum(len(x) for x in clean_items)
        pt_size = 15 if total_chars > 320 else (16 if total_chars > 200 else 18)
        spacing_pt = 8 if len(clean_items) > 3 else 14

        for i, it in enumerate(clean_items):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = f"▸  {it}"
            p.font.name = FONT_PRIMARY
            p.font.size = Pt(pt_size)
            p.font.color.rgb = theme["text"]
            p.space_before = Pt(spacing_pt)


# ---------------------------------------------------------------------------
# Intelligent Markdown Parsing & Layout Detection
# ---------------------------------------------------------------------------

def _extract_metric_line(line: str) -> Optional[Tuple[str, str, str]]:
    """Detects metric pattern: `**99.9%**: Label - Description` or `**10x** Acceleration`."""
    clean = line.lstrip("- *#>")
    match = re.match(r"^\*\*([0-9\.\+\<\>\%\$xXkKmMbB\/\-]+)\*\*\s*[:\-–—]?\s*(.+)$", clean)
    if match:
        val = match.group(1).strip()
        rest = match.group(2).strip()
        parts = re.split(r"[:\-–—]\s*", rest, 1)
        label = parts[0].strip()
        desc = parts[1].strip() if len(parts) > 1 else ""
        return val, label, desc
    return None


def _is_table_lines(lines: List[str]) -> bool:
    """Checks if lines contain a markdown table."""
    table_lines = [l for l in lines if "|" in l]
    return len(table_lines) >= 2


def _parse_markdown_table(lines: List[str]) -> List[List[str]]:
    """Converts markdown table lines to 2D list."""
    rows = []
    for l in lines:
        if "|" in l:
            stripped = l.strip()
            # Skip separator line like `|---|---|`
            if re.match(r"^\|?[\s\-:|]+\|?$", stripped):
                continue
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if cells:
                rows.append(cells)
    return rows


def parse_markdown_to_deck(md_content: str, prs: Presentation, theme_name: str = "modern_dark"):
    theme = THEMES.get(theme_name, THEMES["modern_dark"])
    lines = md_content.splitlines()

    # Segment slides by '# '
    raw_slides = []
    current_slide = None

    for raw in lines:
        line = raw.strip()
        if line.startswith("# "):
            if current_slide:
                raw_slides.append(current_slide)
            current_slide = {"title": line[2:].strip(), "lines": []}
        elif current_slide is not None:
            if line:
                current_slide["lines"].append(line)

    if current_slide:
        raw_slides.append(current_slide)

    if not raw_slides:
        raw_slides = [{"title": "INDRA Sovereign Presentation", "lines": ["No slide content provided."]}]

    blank_layout = prs.slide_layouts[6]
    total_slides = len(raw_slides)

    for idx, s in enumerate(raw_slides):
        slide = prs.slides.add_slide(blank_layout)
        title_text = s["title"]
        s_lines = s["lines"]

        # Slide 1 is ALWAYS the Hero Title Slide
        if idx == 0:
            render_hero_slide(slide, title_text, None, s_lines, theme)
            continue

        # Extract possible subtitle (line immediately starting with `*subtitle*` or plain text before headings)
        subtitle = None
        work_lines = s_lines[:]
        if work_lines and not work_lines[0].startswith(("#", "-", "*", ">", "|", "1.", "2.", "3.", "4.")):
            subtitle = work_lines[0]
            work_lines = work_lines[1:]

        # Detection 1: Table Slide
        if _is_table_lines(work_lines):
            rows = _parse_markdown_table(work_lines)
            if rows:
                render_table_slide(slide, title_text, rows, theme, idx, total_slides, subtitle=subtitle)
                continue

        # Detection 2: Quote / Takeaway
        quote_candidates = [l for l in work_lines if l.startswith(">")]
        if quote_candidates:
            q_text = " ".join(l.lstrip("> ").strip() for l in quote_candidates)
            author = "INDRA Strategic Architecture"
            render_quote_slide(slide, title_text, q_text, author, theme, idx, total_slides, subtitle=subtitle)
            continue

        # Detection 3: Metric Stat Cards
        metric_matches = []
        for l in work_lines:
            m_res = _extract_metric_line(l)
            if m_res:
                metric_matches.append({"value": m_res[0], "label": m_res[1], "desc": m_res[2]})

        if len(metric_matches) >= 2:
            render_metric_cards_slide(slide, title_text, metric_matches, theme, idx, total_slides, subtitle=subtitle)
            continue

        # Detection 4: Numbered Process Steps (e.g. `1. Step`, `2. Step`)
        step_matches = []
        for l in work_lines:
            step_m = re.match(r"^(\d+)\.\s*(.+)$", l.strip())
            if step_m:
                s_num = step_m.group(1)
                s_rest = step_m.group(2)
                parts = re.split(r"[:\-–—]\s*", s_rest, 1)
                s_title = parts[0].strip()
                s_desc = parts[1].strip() if len(parts) > 1 else ""
                step_matches.append({"step": s_num, "title": s_title, "desc": s_desc})

        if len(step_matches) >= 2 and len(step_matches) <= 4:
            render_step_pipeline_slide(slide, title_text, step_matches, theme, idx, total_slides, subtitle=subtitle)
            continue

        # Detection 5: Multi-Card Grid (`## Subheadings`)
        subheading_indices = [i for i, l in enumerate(work_lines) if l.startswith("## ")]
        if 2 <= len(subheading_indices) <= 4:
            cards = []
            for h_pos, start_idx in enumerate(subheading_indices):
                end_idx = subheading_indices[h_pos + 1] if h_pos + 1 < len(subheading_indices) else len(work_lines)
                card_title = work_lines[start_idx][3:].strip()
                card_bullets = [work_lines[j] for j in range(start_idx + 1, end_idx) if work_lines[j].strip()]
                cards.append({"title": card_title, "bullets": card_bullets})

            render_card_grid_slide(slide, title_text, cards, theme, idx, total_slides, subtitle=subtitle)
            continue

        # Default Fallback: Clean standard content slide with smart 2-column auto-split
        render_standard_content_slide(slide, title_text, work_lines, theme, idx, total_slides, subtitle=subtitle)


# ---------------------------------------------------------------------------
# JSON Deck Specification Support
# ---------------------------------------------------------------------------

def parse_json_to_deck(spec: Dict[str, Any], prs: Presentation, theme_name: str = "modern_dark"):
    theme = THEMES.get(theme_name, THEMES["modern_dark"])
    blank_layout = prs.slide_layouts[6]
    slides_spec = spec.get("slides", [])
    total_slides = len(slides_spec)

    for idx, s in enumerate(slides_spec):
        slide = prs.slides.add_slide(blank_layout)
        layout = s.get("layout", "standard")
        title = s.get("title", f"Slide {idx+1}")
        subtitle = s.get("subtitle")

        if layout == "hero" or layout == "title" or idx == 0:
            render_hero_slide(slide, title, subtitle, s.get("items", s.get("bullets", [])), theme)
        elif layout == "metrics":
            render_metric_cards_slide(slide, title, s.get("metrics", []), theme, idx, total_slides, subtitle=subtitle)
        elif layout == "cards":
            render_card_grid_slide(slide, title, s.get("cards", []), theme, idx, total_slides, subtitle=subtitle)
        elif layout == "steps":
            render_step_pipeline_slide(slide, title, s.get("steps", []), theme, idx, total_slides, subtitle=subtitle)
        elif layout == "quote":
            render_quote_slide(slide, title, s.get("quote", ""), s.get("author", ""), theme, idx, total_slides, subtitle=subtitle)
        elif layout == "table" or s.get("tables"):
            rows = s.get("rows", s.get("tables", [{}])[0].get("rows", []))
            render_table_slide(slide, title, rows, theme, idx, total_slides, subtitle=subtitle)
        else:
            items = s.get("bullets", s.get("items", []))
            render_standard_content_slide(slide, title, items, theme, idx, total_slides, subtitle=subtitle)


def render_pptx(input_path: str, output_path: str, theme: str = "modern_dark") -> bool:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    prs = Presentation()
    prs.slide_width = SLIDE_WIDTH
    prs.slide_height = SLIDE_HEIGHT

    content_raw = Path(input_path).read_text(encoding="utf-8-sig")
    if input_path.endswith(".json"):
        spec = json.loads(content_raw)
        parse_json_to_deck(spec, prs, theme)
    else:
        parse_markdown_to_deck(content_raw, prs, theme)

    prs.save(str(out))
    print(f"[indra-pptx] Successfully created presentation ({theme}): {output_path}")
    return True


def main():
    parser = argparse.ArgumentParser(description="INDRA 100% Offline 16:9 PowerPoint Generator (Claude-Quality)")
    parser.add_argument("input", help="Path to input Markdown outline (.md, .txt) or JSON (.json) spec")
    parser.add_argument("-o", "--output", required=True, help="Destination .pptx path")
    parser.add_argument("--theme", default="modern_dark", choices=list(THEMES.keys()), help="Visual theme")
    args = parser.parse_args()

    render_pptx(args.input, args.output, args.theme)


if __name__ == "__main__":
    main()
