"""CLEON-branded Excel and PDF exports for report data."""

from pathlib import Path
import os
from xml.sax.saxutils import escape

from date_utils import format_display_date

NAVY = "10182A"
ORANGE = "EC7624"
PALE = "F3F6FA"
TEXT = "263244"
RC_NUMBER = "RC: 8817624"
COMPANY_EMAIL = "cleonoilandgas@gmail.com"
LOGO_PATH = Path(__file__).with_name("cleon_oil_gas_logo.png")
CURRENCY_HEADERS = (
    "price", "cost", "sales", "profit", "amount", "balance",
    "short/over", "expense", "revenue", "payment", "rtt cost", "total",
)
def _is_currency_header(header):
    normalized = str(header).casefold()
    if "litre" in normalized or normalized.endswith((" l", " (l)", " [l]")):
        return False
    return any(token in normalized for token in CURRENCY_HEADERS)


def _export_value(header, value):
    if value is None:
        return ""
    if isinstance(value, str):
        if "NGN " in value:
            return value.replace("NGN ", "₦")
        if "date" in str(header).casefold():
            return format_display_date(value)
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if _is_currency_header(header):
            return f"₦{value:,.2f}"
        return f"{value:,.2f}"
    return value


def add_total_column(report_name, headers, rows):
    """Remove the Total column from all exported report tables."""
    keep_indices = [
        index for index, header in enumerate(headers)
        if str(header).strip().casefold() != "total"
    ]
    return (
        [headers[index] for index in keep_indices],
        [tuple(row[index] for index in keep_indices) for row in rows],
    )


def _safe_sheet_title(value):
    title = str(value or "Report")
    for character in ("\\", "/", "*", "?", ":", "[", "]"):
        title = title.replace(character, "-")
    return title[:31]


def _register_pdf_fonts():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    font_directory = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    regular_path = font_directory / "arial.ttf"
    bold_path = font_directory / "arialbd.ttf"
    if not regular_path.exists() or not bold_path.exists():
        raise FileNotFoundError(
            f"Unicode PDF fonts were not found in {font_directory}."
        )
    if "CLEONArial" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("CLEONArial", str(regular_path)))
    if "CLEONArial-Bold" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("CLEONArial-Bold", str(bold_path)))
    pdfmetrics.registerFontFamily(
        "CLEONArial",
        normal="CLEONArial",
        bold="CLEONArial-Bold",
        italic="CLEONArial",
        boldItalic="CLEONArial-Bold",
    )
    return "CLEONArial", "CLEONArial-Bold"


def export_excel(path, report_name, headers, rows, date_range,
                 detail_headers=None, detail_rows=None):
    """Save a styled workbook with logo, RC number, and printable settings."""
    from openpyxl import Workbook
    from openpyxl.drawing.image import Image as ExcelImage
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    navy_fill = PatternFill("solid", fgColor=NAVY)
    thin_gray = Side(style="thin", color="D9E0E8")

    def add_report_sheet(sheet, sheet_name, sheet_headers, sheet_rows):
        sheet_headers, sheet_rows = add_total_column(
            sheet_name, sheet_headers, sheet_rows
        )
        sheet.title = _safe_sheet_title(sheet_name)
        column_count = max(1, len(sheet_headers))
        end_column = max(6, column_count)

        sheet.row_dimensions[1].height = 43
        if LOGO_PATH.exists():
            image = ExcelImage(str(LOGO_PATH))
            image.width = 150
            image.height = 47
            sheet.add_image(image, "A1")
        rc_cell = sheet.cell(1, end_column, RC_NUMBER)
        rc_cell.font = Font(name="Aptos", size=11, bold=True, color=ORANGE)
        rc_cell.alignment = Alignment(horizontal="right", vertical="center")

        sheet.row_dimensions[3].height = 5
        for column in range(1, end_column + 1):
            sheet.cell(3, column).fill = navy_fill
        sheet.cell(4, 1, str(sheet_name).upper())
        sheet.cell(4, 1).font = Font(
            name="Aptos Display", size=16, bold=True, color=NAVY
        )
        sheet.cell(
            5, 1,
            f"Reporting period: {format_display_date(date_range[0])} to "
            f"{format_display_date(date_range[1])}",
        )
        sheet.cell(5, 1).font = Font(name="Aptos", size=10, color=TEXT)

        header_row = 7
        for column, label in enumerate(sheet_headers, 1):
            cell = sheet.cell(header_row, column, str(label))
            cell.fill = navy_fill
            cell.font = Font(name="Aptos", size=10, bold=True, color="FFFFFF")
            cell.alignment = Alignment(vertical="center", wrap_text=True)
        sheet.row_dimensions[header_row].height = 30

        for row_index, row in enumerate(sheet_rows, header_row + 1):
            for column, value in enumerate(row, 1):
                header = sheet_headers[column - 1]
                cell = sheet.cell(row_index, column, value)
                cell.font = Font(name="Aptos", size=10, color=TEXT)
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                cell.border = Border(bottom=thin_gray)
                if row_index % 2 == 0:
                    cell.fill = PatternFill("solid", fgColor=PALE)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    cell.number_format = (
                        '"₦"#,##0.00;[Red]-"₦"#,##0.00'
                        if _is_currency_header(header) else "#,##0.00"
                    )
                elif isinstance(value, str):
                    cell.value = _export_value(header, value)

        last_row = max(header_row, header_row + len(sheet_rows))
        orange_side = Side(style="medium", color=ORANGE)
        for column in range(1, end_column + 1):
            sheet.cell(last_row, column).border = Border(bottom=orange_side)

        for column, label in enumerate(sheet_headers, 1):
            values = [str(label)] + [
                str(row[column - 1] or "") for row in sheet_rows
            ]
            width = min(
                34, max(12, max((len(value) for value in values), default=12) + 2)
            )
            sheet.column_dimensions[get_column_letter(column)].width = width
        if len(sheet_headers) < end_column:
            sheet.column_dimensions[get_column_letter(end_column)].width = 20

        sheet.freeze_panes = "A8"
        if sheet_headers:
            sheet.auto_filter.ref = (
                f"A{header_row}:"
                f"{get_column_letter(len(sheet_headers))}{last_row}"
            )
        sheet.sheet_view.showGridLines = False
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.page_setup.orientation = (
            "landscape" if len(sheet_headers) > 6 else "portrait"
        )
        sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
        sheet.page_margins.left = 0.25
        sheet.page_margins.right = 0.25
        sheet.page_margins.top = 0.45
        sheet.page_margins.bottom = 0.5
        sheet.print_title_rows = f"{header_row}:{header_row}"
        sheet.print_area = (
            f"A1:{get_column_letter(end_column)}{last_row}"
        )
        sheet.oddFooter.center.text = (
            f"\u2709  {COMPANY_EMAIL}     |     Page &P of &N"
        )
        sheet.oddFooter.center.size = 9
        sheet.oddFooter.center.font = "Aptos,Italic"
        sheet.oddFooter.center.color = NAVY

    sheet = workbook.active
    add_report_sheet(sheet, report_name, headers, rows)
    if detail_headers is not None and detail_rows is not None:
        detail_sheet = workbook.create_sheet("Delivery Detail")
        add_report_sheet(
            detail_sheet, "Delivery Detail", detail_headers, detail_rows
        )
    workbook.save(path)


def export_pdf(path, report_name, headers, rows, date_range):
    """Save a paginated report using the CLEON letterhead colors and footer."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph, SimpleDocTemplate, Table, TableStyle,
    )
    from reportlab.lib.utils import ImageReader

    headers, rows = add_total_column(report_name, headers, rows)
    pdf_font, pdf_bold_font = _register_pdf_fonts()
    page_size = A4
    doc = SimpleDocTemplate(
        str(path), pagesize=page_size,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=31 * mm, bottomMargin=22 * mm,
        title=f"CLEON Oil & Gas - {report_name}",
        author="CLEON Oil & Gas",
    )
    navy = colors.HexColor(f"#{NAVY}")
    orange = colors.HexColor(f"#{ORANGE}")
    text = colors.HexColor(f"#{TEXT}")
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CLEONTitle", parent=styles["Heading1"], fontName=pdf_bold_font,
        fontSize=15, leading=19, textColor=navy, spaceAfter=4,
    )
    period_style = ParagraphStyle(
        "CLEONPeriod", parent=styles["Normal"], fontName=pdf_font,
        fontSize=9, leading=12, textColor=text, spaceAfter=12,
    )
    cell_style = ParagraphStyle(
        "CLEONCell", parent=styles["Normal"], fontName=pdf_font,
        fontSize=7.5 if len(headers) > 6 else 8.5, leading=10, textColor=text,
        wordWrap="CJK",
    )
    head_style = ParagraphStyle(
        "CLEONHead", parent=cell_style, fontName=pdf_bold_font,
        textColor=colors.white,
    )
    data = [[Paragraph(escape(str(value)), head_style) for value in headers]]
    for row in rows:
        data.append([
            Paragraph(
                escape(str(_export_value(header, value))), cell_style
            )
            for header, value in zip(headers, row)
        ])
    available_width = page_size[0] - doc.leftMargin - doc.rightMargin
    widths = [available_width / max(1, len(headers))] * max(1, len(headers))
    report_table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    report_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), navy),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D9E0E8")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        *[("BACKGROUND", (0, row_no), (-1, row_no), colors.HexColor("#F3F6FA"))
          for row_no in range(2, len(data), 2)],
    ]))
    story = [
        Paragraph(str(report_name), title_style),
        Paragraph(
            f"Reporting period: {format_display_date(date_range[0])} to "
            f"{format_display_date(date_range[1])}",
            period_style,
        ),
        report_table,
    ]

    def draw_letterhead(canvas, document):
        canvas.saveState()
        width, height = page_size
        if LOGO_PATH.exists():
            canvas.drawImage(ImageReader(str(LOGO_PATH)), doc.leftMargin,
                             height - 24 * mm, width=42 * mm, height=13.1 * mm,
                             preserveAspectRatio=True, mask="auto")
        canvas.setFont(pdf_bold_font, 10)
        canvas.setFillColor(orange)
        canvas.drawRightString(width - doc.rightMargin, height - 16 * mm, RC_NUMBER)
        canvas.setStrokeColor(navy)
        canvas.setLineWidth(2.2)
        canvas.line(doc.leftMargin, height - 27 * mm,
                    width - doc.rightMargin, height - 27 * mm)
        canvas.setStrokeColor(orange)
        canvas.setLineWidth(1.8)
        canvas.line(doc.leftMargin, 15 * mm, width - doc.rightMargin, 15 * mm)
        canvas.setFont("Helvetica-Oblique", 8.5)
        canvas.setFillColor(navy)
        email_width = canvas.stringWidth(COMPANY_EMAIL, "Helvetica-Oblique", 8.5)
        icon_width = 8
        gap = 4
        start_x = (width - (icon_width + gap + email_width)) / 2
        icon_y = 9 * mm - 1
        canvas.setStrokeColor(navy)
        canvas.setLineWidth(0.8)
        canvas.rect(start_x, icon_y, icon_width, 6, stroke=1, fill=0)
        canvas.line(start_x, icon_y + 6, start_x + icon_width / 2, icon_y + 2.5)
        canvas.line(start_x + icon_width, icon_y + 6,
                    start_x + icon_width / 2, icon_y + 2.5)
        canvas.drawString(start_x + icon_width + gap, 9 * mm, COMPANY_EMAIL)
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_letterhead, onLaterPages=draw_letterhead)


def export_product_delivery_pdf(path, summary_headers, summary_rows,
                                detail_headers, detail_rows, date_range):
    """Print a landscape CLEON product summary and linked audit detail."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        KeepTogether, Paragraph, SimpleDocTemplate, Table, TableStyle,
    )
    from reportlab.lib.utils import ImageReader

    summary_headers, summary_rows = add_total_column(
        "Product / Delivery", summary_headers, summary_rows
    )
    detail_headers, detail_rows = add_total_column(
        "Delivery Detail", detail_headers, detail_rows
    )
    pdf_font, pdf_bold_font = _register_pdf_fonts()
    page_size = landscape(A4)
    doc = SimpleDocTemplate(
        str(path), pagesize=page_size, leftMargin=10 * mm,
        rightMargin=10 * mm, topMargin=31 * mm, bottomMargin=20 * mm,
        title="CLEON Product and Delivery Reconciliation",
        author="CLEON Oil & Gas",
    )
    navy = colors.HexColor(f"#{NAVY}")
    orange = colors.HexColor(f"#{ORANGE}")
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "ProductReportTitle", parent=styles["Heading1"],
        fontName=pdf_bold_font, fontSize=14, leading=16,
        textColor=navy, spaceAfter=5,
    )
    body = ParagraphStyle(
        "ProductReportBody", parent=styles["Normal"], fontName=pdf_font,
        fontSize=6.5,
        leading=7.5, wordWrap="CJK",
    )
    head = ParagraphStyle(
        "ProductReportHeader", parent=body, fontName=pdf_bold_font,
        textColor=colors.white,
    )

    def make_table(headers, rows, font_size=5.5):
        cell_style = ParagraphStyle(
            f"ProductCell{font_size}", parent=body,
            fontSize=font_size, leading=font_size + 1,
        )
        header_cells = [
            Paragraph(escape(str(value)), head) for value in headers
        ]
        data = [header_cells]
        for row in rows:
            data.append([
                Paragraph(
                escape(str(_export_value(header, value))), cell_style
            )
            for header, value in zip(headers, row)
            ])
        widths = [doc.width / max(1, len(headers)) for _ in headers]
        table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), navy),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D9E0E8")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            *[("BACKGROUND", (0, row_no), (-1, row_no),
               colors.HexColor("#F3F6FA"))
              for row_no in range(2, len(data), 2)],
        ]))
        return table

    story = [
        KeepTogether([
            Paragraph("Product and Delivery Summary", title),
            make_table(summary_headers, summary_rows, 6.5),
        ]),
        KeepTogether([
            Paragraph("Receipt, Pump, Settlement and Expense Detail", title),
            make_table(detail_headers, detail_rows, 6.0),
        ]),
    ]

    def draw_letterhead(canvas, document):
        canvas.saveState()
        width, height = page_size
        if LOGO_PATH.exists():
            canvas.drawImage(
                ImageReader(str(LOGO_PATH)), doc.leftMargin,
                height - 24 * mm, width=42 * mm, height=13.1 * mm,
                preserveAspectRatio=True, mask="auto",
            )
        canvas.setFont(pdf_bold_font, 9)
        canvas.setFillColor(orange)
        canvas.drawRightString(
            width - doc.rightMargin, height - 16 * mm, RC_NUMBER
        )
        canvas.setStrokeColor(navy)
        canvas.setLineWidth(2.0)
        canvas.line(
            doc.leftMargin, height - 27 * mm,
            width - doc.rightMargin, height - 27 * mm,
        )
        canvas.setStrokeColor(orange)
        canvas.setLineWidth(1.2)
        canvas.line(doc.leftMargin, 15 * mm, width - doc.rightMargin, 15 * mm)
        canvas.setFont(pdf_font, 8)
        canvas.setFillColor(navy)
        canvas.drawRightString(
            width - doc.rightMargin, 9 * mm,
            f"Page {document.page}"
        )
        canvas.setFont(pdf_font, 8)
        canvas.drawString(doc.leftMargin, 9 * mm, COMPANY_EMAIL)
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_letterhead, onLaterPages=draw_letterhead)


def export_fuel_receipts_pdf(path, headers, rows, date_range):
    """Export fuel receipts as landscape delivery and payment/reconciliation pages."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        KeepTogether, Paragraph, SimpleDocTemplate, Table, TableStyle,
    )
    from reportlab.lib.utils import ImageReader

    headers, rows = add_total_column("Fuel Receipts", headers, rows)
    pdf_font, pdf_bold_font = _register_pdf_fonts()
    page_size = landscape(A4)
    doc = SimpleDocTemplate(
        str(path), pagesize=page_size, leftMargin=10 * mm,
        rightMargin=10 * mm, topMargin=31 * mm, bottomMargin=20 * mm,
        title="CLEON Fuel Receipts",
        author="CLEON Oil & Gas",
    )
    navy = colors.HexColor(f"#{NAVY}")
    orange = colors.HexColor(f"#{ORANGE}")
    text = colors.HexColor(f"#{TEXT}")
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "FuelReceiptsTitle", parent=styles["Heading1"],
        fontName=pdf_bold_font, fontSize=14, leading=16,
        textColor=navy, spaceAfter=4,
    )
    period_style = ParagraphStyle(
        "FuelReceiptsPeriod", parent=styles["Normal"],
        fontName=pdf_font, fontSize=8, leading=10,
        textColor=text, spaceAfter=8,
    )
    header_style = ParagraphStyle(
        "FuelReceiptsHeader", parent=styles["Normal"],
        fontName=pdf_bold_font, fontSize=6, leading=7,
        textColor=colors.white, wordWrap="CJK",
    )
    cell_style = ParagraphStyle(
        "FuelReceiptsCell", parent=styles["Normal"],
        fontName=pdf_font, fontSize=6, leading=7,
        textColor=text, wordWrap="CJK",
    )
    header_indices = {header: index for index, header in enumerate(headers)}
    sections = (
        (
            "Delivery and Cost Summary",
            (
                "Date", "Tank", "Product Type", "Supplier", "Invoice Number",
                "Invoice L", "Actual L", "Short/Over L", "Cost/L",
                "Invoice Cost", "Actual Cost",
            ),
        ),
        (
            "Payment and Short Reconciliation",
            (
                "Date", "Tank", "Product Type", "Invoice Number",
                "Product Short L", "Reconciled Short L",
                "Station-Borne Short L", "Unreconciled Short L",
                "Reconciled Short Cost", "Station-Borne Cost",
                "Adjusted Product Cost", "Amount Sent", "Balance",
            ),
        ),
    )

    def make_table(section_headers, section_rows):
        data = [[
            Paragraph(escape(str(header)), header_style)
            for header in section_headers
        ]]
        for row in section_rows:
            data.append([
                Paragraph(
                    escape(str(_export_value(header, value))), cell_style
                )
                for header, value in zip(section_headers, row)
            ])
        widths = [doc.width / len(section_headers)] * len(section_headers)
        table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), navy),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D9E0E8")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            *[("BACKGROUND", (0, row_no), (-1, row_no),
               colors.HexColor("#F3F6FA"))
              for row_no in range(2, len(data), 2)],
        ]))
        return table

    story = []
    for section_title, section_headers in sections:
        indices = [header_indices[header] for header in section_headers]
        section_rows = [
            tuple(row[index] for index in indices)
            for row in rows
        ]
        story.append(KeepTogether([
            Paragraph(section_title, title_style),
            Paragraph(
                f"Reporting period: {format_display_date(date_range[0])} to "
                f"{format_display_date(date_range[1])}",
                period_style,
            ),
            make_table(section_headers, section_rows),
        ]))

    def draw_letterhead(canvas, document):
        canvas.saveState()
        width, height = page_size
        if LOGO_PATH.exists():
            canvas.drawImage(
                ImageReader(str(LOGO_PATH)), doc.leftMargin,
                height - 24 * mm, width=42 * mm, height=13.1 * mm,
                preserveAspectRatio=True, mask="auto",
            )
        canvas.setFont(pdf_bold_font, 9)
        canvas.setFillColor(orange)
        canvas.drawRightString(
            width - doc.rightMargin, height - 16 * mm, RC_NUMBER
        )
        canvas.setStrokeColor(navy)
        canvas.setLineWidth(2.0)
        canvas.line(
            doc.leftMargin, height - 27 * mm,
            width - doc.rightMargin, height - 27 * mm,
        )
        canvas.setStrokeColor(orange)
        canvas.setLineWidth(1.2)
        canvas.line(doc.leftMargin, 15 * mm, width - doc.rightMargin, 15 * mm)
        canvas.setFont(pdf_font, 8)
        canvas.setFillColor(navy)
        canvas.drawRightString(
            width - doc.rightMargin, 9 * mm, f"Page {document.page}"
        )
        canvas.drawString(doc.leftMargin, 9 * mm, COMPANY_EMAIL)
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_letterhead, onLaterPages=draw_letterhead)
