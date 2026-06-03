import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER


def _fmt_money(value) -> str:
    try:
        return f"{float(value):,.0f}"
    except (TypeError, ValueError):
        return str(value) if value else "0"


def generate_accounting_pdf(accounting_json: dict) -> bytes:
    """Generate a PDF from an accounting_json dict and return raw bytes."""
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "title",
        parent=styles["Normal"],
        fontSize=13,
        fontName="Helvetica-Bold",
        spaceAfter=4,
    )
    label_style = ParagraphStyle(
        "label",
        parent=styles["Normal"],
        fontSize=9,
        fontName="Helvetica-Bold",
    )
    value_style = ParagraphStyle(
        "value",
        parent=styles["Normal"],
        fontSize=9,
        fontName="Helvetica",
    )
    cell_style = ParagraphStyle(
        "cell",
        parent=styles["Normal"],
        fontSize=8,
        fontName="Helvetica",
        leading=10,
    )
    header_cell_style = ParagraphStyle(
        "header_cell",
        parent=styles["Normal"],
        fontSize=8,
        fontName="Helvetica-Bold",
        alignment=TA_CENTER,
    )
    notes_style = ParagraphStyle(
        "notes",
        parent=styles["Normal"],
        fontSize=8,
        fontName="Helvetica-Oblique",
        textColor=colors.HexColor("#444444"),
    )

    comprobante = accounting_json.get("comprobante", {})
    comp_nombre = comprobante.get("nombre", "").upper()
    comp_numero = comprobante.get("numero", "")
    fecha = accounting_json.get("fecha", "")
    consecutivo = accounting_json.get("consecutivo", "")
    descripcion = accounting_json.get("descripcion", "")
    notas = accounting_json.get("notas", "")
    detalle = accounting_json.get("detalle", [])
    totales = accounting_json.get("totales", {})

    story = []

    # --- Header ---
    story.append(Paragraph(f"COMPROBANTE DE {comp_nombre}", title_style))

    header_data = [
        [
            Paragraph("N°:", label_style),
            Paragraph(str(comp_numero), value_style),
            Paragraph("Consecutivo:", label_style),
            Paragraph(str(consecutivo), value_style),
            Paragraph("Fecha:", label_style),
            Paragraph(str(fecha), value_style),
        ]
    ]
    header_table = Table(header_data, colWidths=[2 * cm, 2 * cm, 3 * cm, 4 * cm, 2 * cm, 4 * cm])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.2 * cm))

    desc_data = [
        [Paragraph("Descripción:", label_style), Paragraph(str(descripcion), value_style)]
    ]
    desc_table = Table(desc_data, colWidths=[3 * cm, None])
    desc_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(desc_table)
    story.append(Spacer(1, 0.4 * cm))

    # --- Detail table ---
    col_headers = [
        Paragraph("Cuenta", header_cell_style),
        Paragraph("Nombre", header_cell_style),
        Paragraph("Tercero", header_cell_style),
        Paragraph("Descripción", header_cell_style),
        Paragraph("Centro Costo", header_cell_style),
        Paragraph("Débito", header_cell_style),
        Paragraph("Crédito", header_cell_style),
    ]

    table_data = [col_headers]

    for item in detalle:
        tercero = item.get("tercero") or {}
        tercero_text = ""
        if tercero:
            nombre_tercero = tercero.get("nombre_o_razon_social", "")
            doc_tercero = tercero.get("numero_documento", "")
            if nombre_tercero:
                tercero_text = f"{nombre_tercero}\n{doc_tercero}" if doc_tercero else nombre_tercero

        table_data.append([
            Paragraph(str(item.get("cuenta", "")), cell_style),
            Paragraph(str(item.get("nombre", "")), cell_style),
            Paragraph(tercero_text, cell_style),
            Paragraph(str(item.get("descripcion", "")), cell_style),
            Paragraph(str(item.get("centro_costo") or ""), cell_style),
            Paragraph(_fmt_money(item.get("debito", 0)), ParagraphStyle("money_d", parent=cell_style, alignment=TA_RIGHT)),
            Paragraph(_fmt_money(item.get("credito", 0)), ParagraphStyle("money_c", parent=cell_style, alignment=TA_RIGHT)),
        ])

    # Totals row
    table_data.append([
        Paragraph("TOTALES", ParagraphStyle("tot_label", parent=cell_style, fontName="Helvetica-Bold")),
        Paragraph("", cell_style),
        Paragraph("", cell_style),
        Paragraph("", cell_style),
        Paragraph("", cell_style),
        Paragraph(_fmt_money(totales.get("debito", 0)), ParagraphStyle("tot_d", parent=cell_style, fontName="Helvetica-Bold", alignment=TA_RIGHT)),
        Paragraph(_fmt_money(totales.get("credito", 0)), ParagraphStyle("tot_c", parent=cell_style, fontName="Helvetica-Bold", alignment=TA_RIGHT)),
    ])

    col_widths = [2.5 * cm, 5.5 * cm, 5 * cm, 6.5 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm]
    detail_table = Table(table_data, colWidths=col_widths, repeatRows=1)

    totals_row_index = len(table_data) - 1
    detail_table.setStyle(TableStyle([
        # Header row
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, totals_row_index - 1), [colors.white, colors.HexColor("#f5f6fa")]),
        # Totals row
        ("BACKGROUND", (0, totals_row_index), (-1, totals_row_index), colors.HexColor("#dde1e7")),
        ("FONTNAME", (0, totals_row_index), (-1, totals_row_index), "Helvetica-Bold"),
        ("LINEABOVE", (0, totals_row_index), (-1, totals_row_index), 1, colors.HexColor("#2c3e50")),
        # Grid
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))

    story.append(detail_table)

    # --- Notes ---
    if notas:
        story.append(Spacer(1, 0.4 * cm))
        story.append(Paragraph(f"<b>Notas:</b> {notas}", notes_style))

    doc.build(story)
    return buffer.getvalue()
