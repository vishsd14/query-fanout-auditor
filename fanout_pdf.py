#!/usr/bin/env python3
"""
fanout_pdf.py
─────────────
PDF report generator for query-fanout-auditor.
Called by fanout_audit.py when --output-pdf is passed.

Requires: reportlab>=4.0 (pip install reportlab)
"""

from datetime import datetime

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.colors import HexColor, white
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, KeepTogether, HRFlowable
    )
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False


# ── Palette ────────────────────────────────────────────────────────────────
def _c(h): return HexColor(h)

VOID      = _c('#09090F')
TEAL      = _c('#00D4E4')
TEAL_BG   = _c('#E0FAFB')
INK       = _c('#1A1A2E')
MIST      = _c('#6B7280')
LIGHT     = _c('#94A3B8')
GREEN     = _c('#16A34A')
GREEN_BG  = _c('#F0FDF4')
AMBER     = _c('#D97706')
AMBER_BG  = _c('#FFFBEB')
RED       = _c('#DC2626')
RED_BG    = _c('#FEF2F2')
YELLOW    = _c('#A16207')
YELLOW_BG = _c('#FEFCE8')
SECTION   = _c('#F1F5F9')
BORDER    = _c('#E2E8F0')

PAGE_W, PAGE_H = A4
M = 16 * mm
CONTENT_W = PAGE_W - 2 * M


# ── Style factory ──────────────────────────────────────────────────────────
def _s(name, **kw):
    defaults = dict(fontName='Helvetica', fontSize=9, textColor=INK, leading=13)
    defaults.update(kw)
    return ParagraphStyle(name, **defaults)

def _make_styles():
    return {
        'eye'     : _s('eye',  fontName='Helvetica-Bold', fontSize=7.5, textColor=TEAL, letterSpacing=1.5),
        'h1'      : _s('h1',   fontName='Helvetica-Bold', fontSize=22,  textColor=white, leading=28),
        'url'     : _s('url',  fontName='Helvetica',      fontSize=8.5, textColor=TEAL),
        'meta_r'  : _s('mr',   fontName='Helvetica',      fontSize=8,   textColor=LIGHT, alignment=TA_RIGHT),
        'h2'      : _s('h2',   fontName='Helvetica-Bold', fontSize=13,  textColor=INK,   leading=18, spaceBefore=4, spaceAfter=4),
        'h3'      : _s('h3',   fontName='Helvetica-Bold', fontSize=10,  textColor=INK,   leading=14, spaceBefore=4, spaceAfter=2),
        'h4'      : _s('h4',   fontName='Helvetica-Bold', fontSize=9,   textColor=INK,   leading=13, spaceBefore=3, spaceAfter=2),
        'body'    : _s('body', fontName='Helvetica',      fontSize=8.5, textColor=INK,   leading=13, spaceAfter=3),
        'mist'    : _s('mist', fontName='Helvetica',      fontSize=8.5, textColor=MIST,  leading=12),
        'note'    : _s('note', fontName='Helvetica-Oblique', fontSize=8, textColor=MIST, leading=12, spaceAfter=3),
        'fix'     : _s('fix',  fontName='Helvetica',      fontSize=8.5, textColor=INK,   leading=13, leftIndent=10),
        'bullet'  : _s('bul',  fontName='Helvetica',      fontSize=8.5, textColor=INK,   leading=13, leftIndent=14, spaceAfter=2),
        'th'      : _s('th',   fontName='Helvetica-Bold', fontSize=7.5, textColor=MIST,  leading=11),
        'td'      : _s('td',   fontName='Helvetica',      fontSize=7.5, textColor=INK,   leading=11),
        'td_mist' : _s('tdm',  fontName='Helvetica',      fontSize=7.5, textColor=MIST,  leading=11),
        'stat_lbl': _s('sl',   fontName='Helvetica',      fontSize=7.5, textColor=MIST,  leading=11, alignment=TA_CENTER),
        'ot'      : _s('ot',   fontName='Helvetica',      fontSize=8,   textColor=TEAL,  leading=12),
        'ow'      : _s('ow',   fontName='Helvetica-Oblique', fontSize=8.5, textColor=MIST, leading=13, spaceAfter=4),
    }


# ── Badge helper ───────────────────────────────────────────────────────────
def _badge(text, bg, fg):
    S = _make_styles()
    p = Paragraph(f'<b>{text}</b>', ParagraphStyle(
        'bdg_inner', fontName='Helvetica-Bold', fontSize=7, textColor=fg, leading=9))
    t = Table([[p]], colWidths=[None])
    t.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,-1), bg),
        ('TOPPADDING',    (0,0), (-1,-1), 2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('LEFTPADDING',   (0,0), (-1,-1), 5),
        ('RIGHTPADDING',  (0,0), (-1,-1), 5),
    ]))
    return t

def _cov_badge(cov):
    S = _make_styles()
    if cov == 'COVERED': return _badge('COVERED', GREEN_BG, GREEN)
    if cov == 'PARTIAL':  return _badge('PARTIAL',  AMBER_BG, AMBER)
    if cov == 'MISSING':  return _badge('MISSING',  RED_BG,   RED)
    return Paragraph(cov or '—', S['td_mist'])

def _pri_badge(pri):
    S = _make_styles()
    p = str(pri)
    if 'P1' in p: return _badge('P1', RED_BG,    RED)
    if 'P2' in p: return _badge('P2', AMBER_BG,  AMBER)
    if 'P3' in p: return _badge('P3', YELLOW_BG, YELLOW)
    if '✅' in p or 'OK' in p: return _badge('OK', GREEN_BG, GREEN)
    return Paragraph(p, S['td_mist'])


# ── Section header ─────────────────────────────────────────────────────────
def _section_header(title, subtitle=None):
    S = _make_styles()
    rows = [[Paragraph(title, S['h2'])]]
    if subtitle:
        rows.append([Paragraph(subtitle, S['mist'])])
    t = Table(rows, colWidths=[CONTENT_W])
    style = [
        ('BACKGROUND',    (0,0), (-1,-1), SECTION),
        ('LEFTPADDING',   (0,0), (-1,-1), 10),
        ('RIGHTPADDING',  (0,0), (-1,-1), 10),
        ('TOPPADDING',    (0,0), (0,0),   8),
        ('BOTTOMPADDING', (0,-1),(-1,-1), 8),
        ('LINEAFTER',     (0,0), (0,-1),  2, TEAL),
    ]
    if subtitle:
        style.append(('TOPPADDING', (0,1), (0,1), 2))
    t.setStyle(TableStyle(style))
    return t


# ══════════════════════════════════════════════════════════════════════════
# SECTIONS
# ══════════════════════════════════════════════════════════════════════════

def _build_header(keyword, url, market, persona, models_used, date_str):
    S = _make_styles()
    eye  = Paragraph('QUERY FAN-OUT COVERAGE BRIEF', S['eye'])
    meta = Paragraph(f'{market} · {persona}', S['meta_r'])
    top  = Table([[eye, meta]], colWidths=[CONTENT_W - 80*mm, 80*mm])
    top.setStyle(TableStyle([
        ('LEFTPADDING',   (0,0), (-1,-1), 0),
        ('RIGHTPADDING',  (0,0), (-1,-1), 0),
        ('TOPPADDING',    (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('VALIGN',        (0,0), (-1,-1), 'BOTTOM'),
    ]))

    # Keyword — highlight last word in teal if it contains a year or looks like a location
    kw_display = keyword.title()
    kw_para = Paragraph(
        f'<font color="#F2F2FF">{kw_display}</font>',
        ParagraphStyle('kw', fontName='Helvetica-Bold', fontSize=22,
                       textColor=white, leading=28)
    )
    model_date = Paragraph(
        f'Models: {" · ".join(m.upper() for m in models_used)}<br/>{date_str}',
        S['meta_r']
    )
    kw_row = Table([[kw_para, model_date]], colWidths=[CONTENT_W - 70*mm, 70*mm])
    kw_row.setStyle(TableStyle([
        ('LEFTPADDING',  (0,0),(-1,-1),0),
        ('RIGHTPADDING', (0,0),(-1,-1),0),
        ('TOPPADDING',   (0,0),(-1,-1),0),
        ('BOTTOMPADDING',(0,0),(-1,-1),4),
        ('VALIGN',       (0,0),(-1,-1),'BOTTOM'),
    ]))

    url_display = url.replace('https://', '').replace('http://', '')
    url_para = Paragraph(url_display, S['url'])

    hdr = Table([[top], [kw_row], [url_para]], colWidths=[CONTENT_W])
    hdr.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,-1), VOID),
        ('LEFTPADDING',   (0,0), (-1,-1), 14),
        ('RIGHTPADDING',  (0,0), (-1,-1), 14),
        ('TOPPADDING',    (0,0), (0,0),   14),
        ('TOPPADDING',    (0,1), (-1,1),  0),
        ('TOPPADDING',    (0,2), (-1,2),  4),
        ('BOTTOMPADDING', (0,0), (0,0),   0),
        ('BOTTOMPADDING', (0,1), (0,1),   0),
        ('BOTTOMPADDING', (0,2), (-1,-1), 14),
    ]))
    return [hdr, Spacer(1, 8)]


def _build_stats(clusters):
    total    = len(clusters)
    covered  = sum(1 for c in clusters if c.get('coverage') == 'COVERED')
    partial  = sum(1 for c in clusters if c.get('coverage') == 'PARTIAL')
    missing  = sum(1 for c in clusters if c.get('coverage') == 'MISSING')
    score    = round((covered * 1.0 + partial * 0.5) / total * 100) if total else 0
    consensus = sum(1 for c in clusters if c.get('consensus_count', 0) >= 2)

    stats = [
        (f'{score}', '/100', 'COVERAGE SCORE',    TEAL),
        (f'{total}',  '',    'QUERY CLUSTERS',     INK),
        (f'{consensus}','',  'CONSENSUS QUERIES',  INK),
        (f'{partial}',  '',  'PARTIAL COVERAGE',   AMBER),
        (f'{missing}',  '',  'MISSING ENTIRELY',   RED),
    ]

    cells = []
    col_w = CONTENT_W / 5
    for val, suf, lbl, col in stats:
        num_style = ParagraphStyle(
            'ns', fontName='Helvetica-Bold', fontSize=22,
            textColor=col, leading=26, alignment=TA_CENTER)
        suffix_str = f'<font size="11" color="#6B7280">{suf}</font>' if suf else ''
        num_p = Paragraph(f'{val}{suffix_str}', num_style)
        lbl_p = Paragraph(lbl, _make_styles()['stat_lbl'])
        cell  = Table([[num_p], [lbl_p]], colWidths=[col_w - 2])
        cell.setStyle(TableStyle([
            ('LEFTPADDING',   (0,0),(-1,-1), 0),
            ('RIGHTPADDING',  (0,0),(-1,-1), 0),
            ('TOPPADDING',    (0,0),(0,0),   10),
            ('BOTTOMPADDING', (0,0),(0,0),    4),
            ('TOPPADDING',    (0,1),(0,1),    2),
            ('BOTTOMPADDING', (0,1),(0,1),   10),
        ]))
        cells.append(cell)

    row = Table([cells], colWidths=[col_w]*5)
    row.setStyle(TableStyle([
        ('BACKGROUND', (0,0),(-1,-1), SECTION),
        ('LINEAFTER',  (0,0),(3,0),   0.5, BORDER),
        ('LEFTPADDING',(0,0),(-1,-1), 0),
        ('RIGHTPADDING',(0,0),(-1,-1),0),
        ('TOPPADDING', (0,0),(-1,-1), 0),
        ('BOTTOMPADDING',(0,0),(-1,-1),0),
        ('ALIGN',      (0,0),(-1,-1), 'CENTER'),
    ]))
    return [row, Spacer(1, 4)]


def _build_coverage_bar(clusters):
    S = _make_styles()
    total   = len(clusters) or 1
    covered = sum(1 for c in clusters if c.get('coverage') == 'COVERED')
    partial = sum(1 for c in clusters if c.get('coverage') == 'PARTIAL')
    missing = sum(1 for c in clusters if c.get('coverage') == 'MISSING')
    bar_w   = CONTENT_W - 2

    cov_w = bar_w * covered / total
    par_w = max(bar_w * partial / total, 4 if partial else 0)
    mis_w = bar_w - cov_w - par_w

    cells, widths, style_bits = [], [], []
    col = 0
    if cov_w > 0:
        cells.append(Paragraph('', S['body'])); widths.append(cov_w)
        style_bits.append(('BACKGROUND', (col,0),(col,0), GREEN)); col += 1
    if par_w > 0:
        cells.append(Paragraph('', S['body'])); widths.append(par_w)
        style_bits.append(('BACKGROUND', (col,0),(col,0), AMBER)); col += 1
    if mis_w > 0:
        cells.append(Paragraph('', S['body'])); widths.append(mis_w)
        style_bits.append(('BACKGROUND', (col,0),(col,0), RED))

    bar = Table([cells], colWidths=widths)
    bar.setStyle(TableStyle([
        ('TOPPADDING',    (0,0),(-1,-1), 5),
        ('BOTTOMPADDING', (0,0),(-1,-1), 5),
    ] + style_bits))

    legend = Table([[
        Paragraph(f'<font color="#16A34A">■</font>  Covered — {covered} ({covered/total*100:.0f}%)', S['td']),
        Paragraph(f'<font color="#D97706">■</font>  Partial — {partial} ({partial/total*100:.0f}%)',  S['td']),
        Paragraph(f'<font color="#DC2626">■</font>  Missing — {missing} ({missing/total*100:.0f}%)',  S['td']),
    ]], colWidths=[CONTENT_W/3]*3)
    legend.setStyle(TableStyle([
        ('LEFTPADDING',  (0,0),(-1,-1),4),
        ('TOPPADDING',   (0,0),(-1,-1),4),
        ('BOTTOMPADDING',(0,0),(-1,-1),0),
    ]))
    return [bar, legend, Spacer(1, 8)]


def _build_gap_card(cluster, idx):
    S = _make_styles()
    pri = str(cluster.get('priority', ''))
    cov = cluster.get('coverage', 'UNKNOWN')
    if 'P1' in pri:
        pri_bg, pri_fg, border_col = RED_BG,   RED,   RED
        pri_text = 'P1 — FIX IMMEDIATELY'
    else:
        pri_bg, pri_fg, border_col = AMBER_BG, AMBER, AMBER
        pri_text = 'P2 — THIS SPRINT'

    models_str = ' / '.join(cluster.get('models', []))
    consensus  = cluster.get('consensus_count', 1)

    header_row = Table([[
        _badge(pri_text, pri_bg, pri_fg),
        Paragraph('', S['body']),
        _cov_badge(cov),
    ]], colWidths=[32*mm, CONTENT_W - 58*mm, 22*mm])
    header_row.setStyle(TableStyle([
        ('LEFTPADDING',   (0,0),(-1,-1), 0),
        ('RIGHTPADDING',  (0,0),(-1,-1), 0),
        ('TOPPADDING',    (0,0),(-1,-1), 0),
        ('BOTTOMPADDING', (0,0),(-1,-1), 6),
        ('VALIGN',        (0,0),(-1,-1), 'MIDDLE'),
    ]))

    meta_row = Table([[
        Paragraph('<b>Intent:</b>', S['td']),
        Paragraph(cluster.get('intent_type','—'), S['td_mist']),
        Paragraph('<b>Consensus:</b>', S['td']),
        Paragraph(f'{models_str} ({consensus}/3)', S['td_mist']),
    ]], colWidths=[14*mm, 44*mm, 22*mm, CONTENT_W - 92*mm])
    meta_row.setStyle(TableStyle([
        ('LEFTPADDING',  (0,0),(-1,-1),0),
        ('RIGHTPADDING', (0,0),(-1,-1),4),
        ('TOPPADDING',   (0,0),(-1,-1),0),
        ('BOTTOMPADDING',(0,0),(-1,-1),5),
    ]))

    fix_text = cluster.get('recommended_fix') or cluster.get('priority_action', '')
    why_text = cluster.get('reason', '')

    fix_row = Table([[
        Paragraph('<b>Fix —</b>', ParagraphStyle('fx', fontName='Helvetica-Bold',
                  fontSize=8.5, textColor=TEAL, leading=13)),
        Paragraph(fix_text, S['fix']),
    ]], colWidths=[12*mm, CONTENT_W - 30*mm])
    fix_row.setStyle(TableStyle([
        ('LEFTPADDING',   (0,0),(-1,-1),0),
        ('RIGHTPADDING',  (0,0),(-1,-1),0),
        ('TOPPADDING',    (0,0),(-1,-1),4),
        ('BOTTOMPADDING', (0,0),(-1,-1),0),
        ('VALIGN',        (0,0),(-1,-1),'TOP'),
        ('LINEABOVE',     (0,0),(-1,0), 0.5, TEAL),
    ]))

    rows = [
        [Paragraph(f'<b>{idx}. {cluster.get("canonical","")}</b>', S['h3'])],
        [header_row],
        [meta_row],
        [Paragraph(why_text, S['mist'])],
        [fix_row],
    ]
    card = Table(rows, colWidths=[CONTENT_W])
    card.setStyle(TableStyle([
        ('BACKGROUND',    (0,0),(-1,-1), white),
        ('LINEABOVE',     (0,0),(-1,0),  1, border_col),
        ('LINEBEFORE',    (0,0),(0,-1),  1, BORDER),
        ('LINEAFTER',     (0,0),(-1,-1), 1, BORDER),
        ('LINEBELOW',     (0,-1),(-1,-1),1, BORDER),
        ('LEFTPADDING',   (0,0),(-1,-1), 10),
        ('RIGHTPADDING',  (0,0),(-1,-1), 10),
        ('TOPPADDING',    (0,0),(0,0),   10),
        ('TOPPADDING',    (0,1),(-1,-1), 0),
        ('BOTTOMPADDING', (0,-1),(-1,-1),10),
        ('BOTTOMPADDING', (0,0),(0,-2),  3),
    ]))
    return [KeepTogether([card, Spacer(1, 6)])]


def _build_priority_gaps(clusters):
    p1_p2 = [c for c in clusters
              if str(c.get('priority','')).startswith(('🔴','🟠'))
              or 'P1' in str(c.get('priority',''))
              or 'P2' in str(c.get('priority',''))]
    if not p1_p2:
        return []
    elems = [Spacer(1,6), _section_header('Priority Gaps',
             f'{len(p1_p2)} gap{"s" if len(p1_p2)!=1 else ""} — fix immediately or this sprint'),
             Spacer(1,8)]
    for i, c in enumerate(p1_p2, 1):
        elems.extend(_build_gap_card(c, i))
    return elems


def _build_scorecard(clusters):
    S = _make_styles()
    col_w = [14*mm, 78*mm, 27*mm, 28*mm, 27*mm]
    hdr = [Paragraph(h, S['th']) for h in
           ['PRIORITY', 'FAN-OUT QUERY', 'INTENT', 'MODELS', 'COVERAGE']]
    rows = [hdr]
    for c in clusters:
        models_str = ' / '.join(c.get('models', []))
        rows.append([
            _pri_badge(c.get('priority', '')),
            Paragraph(c.get('canonical', ''), S['td']),
            Paragraph(c.get('intent_type', ''), S['td_mist']),
            Paragraph(models_str, S['td_mist']),
            _cov_badge(c.get('coverage', '')),
        ])

    tbl = Table(rows, colWidths=col_w, repeatRows=1)
    tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,0),  SECTION),
        ('LINEBELOW',     (0,0), (-1,0),  1, BORDER),
        ('LEFTPADDING',   (0,0), (-1,-1), 5),
        ('RIGHTPADDING',  (0,0), (-1,-1), 5),
        ('TOPPADDING',    (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
        ('ROWBACKGROUNDS',(0,1), (-1,-1), [white, SECTION]),
        ('LINEBELOW',     (0,1), (-1,-1), 0.25, BORDER),
        ('BOX',           (0,0), (-1,-1), 0.5,  BORDER),
    ]))

    return [Spacer(1,6),
            _section_header('Full Coverage Scorecard', f'{len(clusters)} clusters'),
            Spacer(1,8), tbl, Spacer(1,8)]


def _build_forecast(forecast):
    if not forecast:
        return []
    S = _make_styles()
    note = Paragraph(
        'Scores are deterministic projections based on the coverage formula — '
        'not traffic estimates. They show AI citation coverage potential if gaps are closed.',
        S['note'])

    current = forecast.get('current', 0)
    p1_only = forecast.get('p1_only', current)
    p1_p2   = forecast.get('p1_p2',   current)
    all_g   = forecast.get('all_gaps', current)
    p1_c    = forecast.get('p1_count', 0)
    p2_c    = forecast.get('p2_count', 0)
    p3_c    = forecast.get('p3_count', 0)
    d1      = forecast.get('delta_p1', 0)
    d12     = forecast.get('delta_p1_p2', 0)
    da      = forecast.get('delta_all', 0)

    scenarios = [
        ('Current state',  '—',              f'{current}/100', '—',          MIST,  True),
        ('Fix P1 only',    f'{p1_c} gaps',   f'{p1_only}/100', f'+{d1} pts', RED   if d1 > 0 else MIST, False),
        ('Fix P1 + P2',    f'{p1_c+p2_c} gaps', f'{p1_p2}/100', f'+{d12} pts', AMBER if d12 > 0 else MIST, False),
        ('Fix all gaps',   f'{p1_c+p2_c+p3_c} gaps', f'{all_g}/100', f'+{da} pts', GREEN if da > 0 else MIST, False),
    ]

    col_w = [52*mm, 32*mm, 38*mm, 38*mm]
    hdr   = [Paragraph(h, S['th']) for h in
             ['SCENARIO', 'GAPS FIXED', 'PROJECTED SCORE', 'Δ VS CURRENT']]
    rows  = [hdr]
    row_bgs = [SECTION]
    for scenario, gaps_txt, score, delta, col, bold in scenarios:
        fn = 'Helvetica-Bold' if bold else 'Helvetica'
        rows.append([
            Paragraph(f'<b>{scenario}</b>' if bold else scenario,
                      ParagraphStyle('fss', fontName=fn, fontSize=8.5, textColor=INK, leading=13)),
            Paragraph(gaps_txt,  S['td_mist']),
            Paragraph(f'<b>{score}</b>',
                      ParagraphStyle('fsc', fontName='Helvetica-Bold', fontSize=8.5, textColor=col, leading=13)),
            Paragraph(delta,
                      ParagraphStyle('fsd', fontName='Helvetica-Bold' if col!=MIST else 'Helvetica',
                                     fontSize=8.5, textColor=col, leading=13)),
        ])
        row_bgs.append(GREEN_BG if col == GREEN else white)

    tbl = Table(rows, colWidths=col_w, repeatRows=1)
    style = [
        ('BACKGROUND',    (0,0), (-1,0),  SECTION),
        ('LINEBELOW',     (0,0), (-1,0),  1, BORDER),
        ('LINEBELOW',     (0,1), (-1,-1), 0.25, BORDER),
        ('BOX',           (0,0), (-1,-1), 0.5, BORDER),
        ('LEFTPADDING',   (0,0), (-1,-1), 8),
        ('RIGHTPADDING',  (0,0), (-1,-1), 8),
        ('TOPPADDING',    (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]
    for i, bg in enumerate(row_bgs[1:], 1):
        if bg != white:
            style.append(('BACKGROUND', (0,i),(-1,i), bg))
    tbl.setStyle(TableStyle(style))

    return [Spacer(1,6), _section_header('Improvement Forecast'),
            Spacer(1,6), note, Spacer(1,6), tbl, Spacer(1,8)]


def _build_outline_card(outline, idx):
    S = _make_styles()
    pri = outline.get('priority', 'P2')
    pri_bg  = RED_BG   if 'P1' in pri else AMBER_BG
    pri_fg  = RED      if 'P1' in pri else AMBER
    action  = outline.get('action', '')
    target  = outline.get('page_target', '')
    why     = outline.get('rationale', '')
    h2      = outline.get('h2', '')
    schema  = outline.get('schema', 'None')
    wc      = outline.get('word_count', '')
    schema_r = outline.get('schema_rationale', '')
    query   = outline.get('query', '')
    questions = outline.get('key_questions', [])

    # Header
    badge_row = Table([[
        _badge(pri, pri_bg, pri_fg),
        Paragraph('&nbsp;', S['body']),
        _badge(f'✏ {action}' if action else '✏ Update page', TEAL_BG, _c('#0891B2')),
    ]], colWidths=[12*mm, 4*mm, 44*mm])
    badge_row.setStyle(TableStyle([
        ('LEFTPADDING',  (0,0),(-1,-1),0),
        ('RIGHTPADDING', (0,0),(-1,-1),2),
        ('TOPPADDING',   (0,0),(-1,-1),0),
        ('BOTTOMPADDING',(0,0),(-1,-1),4),
        ('VALIGN',       (0,0),(-1,-1),'MIDDLE'),
    ]))

    hdr_rows = [
        [Paragraph(f'<b>{idx}. {query}</b>', S['h3'])],
        [badge_row],
        [Paragraph(f'<b>Target:</b> <font color="#00D4E4">{target}</font>', S['td'])],
    ]
    if why:
        hdr_rows.append([Paragraph(why, S['ow'])])
    hdr_rows.append([Paragraph(f'<b>Suggested H2:</b> {h2}', S['body'])])

    hdr_tbl = Table(hdr_rows, colWidths=[CONTENT_W])
    hdr_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0,0),(-1,-1), SECTION),
        ('LEFTPADDING',   (0,0),(-1,-1), 10),
        ('RIGHTPADDING',  (0,0),(-1,-1), 10),
        ('TOPPADDING',    (0,0),(0,0),   10),
        ('TOPPADDING',    (0,1),(-1,-1), 3),
        ('BOTTOMPADDING', (0,-1),(-1,-1),6),
        ('BOTTOMPADDING', (0,0),(0,-2),  2),
        ('LINEAFTER',     (0,0),(0,-1),  2, TEAL),
    ]))

    body_parts = [hdr_tbl]

    # Sections: full depth has 'sections' [{h3, draft}], lean has 'h3s' [str]
    sections = outline.get('sections', [])
    h3s      = outline.get('h3s', [])

    if sections:
        for sec in sections:
            h3_text   = sec.get('h3', '') if isinstance(sec, dict) else str(sec)
            draft_text= sec.get('draft', '') if isinstance(sec, dict) else ''
            sec_rows  = [[Paragraph(h3_text, S['h4'])]]
            if draft_text:
                sec_rows.append([Paragraph(draft_text, S['body'])])
            st = Table(sec_rows, colWidths=[CONTENT_W])
            st.setStyle(TableStyle([
                ('LEFTPADDING',   (0,0),(-1,-1),10),
                ('RIGHTPADDING',  (0,0),(-1,-1),10),
                ('TOPPADDING',    (0,0),(0,0),  6),
                ('TOPPADDING',    (0,1),(-1,-1),2),
                ('BOTTOMPADDING', (0,-1),(-1,-1),6),
                ('BOTTOMPADDING', (0,0),(0,-2), 2),
                ('LINEABOVE',     (0,0),(-1,0), 0.25, BORDER),
            ]))
            body_parts.append(st)
    elif h3s:
        for h3_text in h3s:
            st = Table([[Paragraph(h3_text, S['h4'])]],
                       colWidths=[CONTENT_W])
            st.setStyle(TableStyle([
                ('LEFTPADDING',  (0,0),(-1,-1),10),
                ('RIGHTPADDING', (0,0),(-1,-1),10),
                ('TOPPADDING',   (0,0),(-1,-1),5),
                ('BOTTOMPADDING',(0,0),(-1,-1),5),
                ('LINEABOVE',    (0,0),(-1,0), 0.25, BORDER),
            ]))
            body_parts.append(st)

    # Footer: must-answer + schema
    must_text = '<br/>'.join([f'• {q}' for q in questions]) if questions else '—'
    schema_txt = f'{schema}'
    if schema_r:
        schema_txt += f'<br/><i><font color="#6B7280">{schema_r}</font></i>'
    footer_rows = [
        [Paragraph('<b>Must answer:</b>', S['td']), Paragraph(must_text,   S['td'])],
        [Paragraph('<b>Word count:</b>',  S['td']), Paragraph(f'{wc}', S['td'])],
        [Paragraph('<b>Schema:</b>',      S['td']), Paragraph(schema_txt,  S['td'])],
    ]
    ft = Table(footer_rows, colWidths=[24*mm, CONTENT_W - 24*mm])
    ft.setStyle(TableStyle([
        ('BACKGROUND',    (0,0),(-1,-1), TEAL_BG),
        ('LEFTPADDING',   (0,0),(-1,-1),10),
        ('RIGHTPADDING',  (0,0),(-1,-1),10),
        ('TOPPADDING',    (0,0),(-1,-1),4),
        ('BOTTOMPADDING', (0,-1),(-1,-1),8),
        ('BOTTOMPADDING', (0,0),(0,-2), 3),
        ('VALIGN',        (0,0),(-1,-1),'TOP'),
    ]))
    body_parts.append(ft)
    body_parts.append(Spacer(1, 10))

    return [KeepTogether(body_parts[:3])] + body_parts[3:]


def _build_content_outlines(outlines):
    if not outlines:
        return []
    elems = [
        PageBreak(),
        _section_header('Content Outlines',
                        'Structured briefs for every P1 and P2 gap — shaped by the '
                        'specific fan-out sub-query AI engines are asking.'),
        Spacer(1, 8),
    ]
    for i, o in enumerate(outlines, 1):
        elems.extend(_build_outline_card(o, i))
    return elems


# ── Footer callback ────────────────────────────────────────────────────────
def _make_footer(keyword):
    def footer_cb(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(MIST)
        canvas.drawString(M, 10*mm,
            f'Query Fan-Out Coverage Brief · {keyword} · '
            'github.com/vishsd14/query-fanout-auditor')
        canvas.drawRightString(PAGE_W - M, 10*mm, f'Page {doc.page}')
        canvas.restoreState()
    return footer_cb


# ══════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════

def generate_pdf(keyword, url, market, persona, models_used,
                 clusters, forecast, outlines, output_path):
    """
    Generate a styled PDF report from fan-out audit data.

    Args:
        keyword      : str  — keyword audited
        url          : str  — target page URL
        market       : str  — market / country
        persona      : str  — simulated user persona
        models_used  : list — model names used
        clusters     : list — cluster dicts from compute_consensus + scoring
        forecast     : dict — improvement forecast from generate_improvement_forecast()
        outlines     : list — content outline dicts from generate_content_outlines()
        output_path  : str  — path to write the .pdf file

    Returns:
        True on success, False on failure (with printed error).
    """
    if not HAS_REPORTLAB:
        print('\n   ⚠️  reportlab is not installed — PDF generation skipped.')
        print('   ⚠️  Install it with: pip install reportlab --break-system-packages')
        return False

    try:
        date_str = datetime.now().strftime('%d %B %Y')

        doc = SimpleDocTemplate(
            output_path, pagesize=A4,
            leftMargin=M, rightMargin=M,
            topMargin=M, bottomMargin=18*mm,
            title=f'Query Fan-Out Coverage Brief — {keyword}',
            author='query-fanout-auditor',
        )

        story = []
        story.extend(_build_header(keyword, url, market, persona, models_used, date_str))
        story.extend(_build_stats(clusters))
        story.extend(_build_coverage_bar(clusters))
        story.extend(_build_priority_gaps(clusters))
        story.extend(_build_scorecard(clusters))
        story.extend(_build_forecast(forecast))
        story.extend(_build_content_outlines(outlines))

        footer = _make_footer(keyword)
        doc.build(story, onFirstPage=footer, onLaterPages=footer)
        return True

    except Exception as e:
        print(f'\n   ⚠️  PDF generation failed: {e}')
        return False
