from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from io import BytesIO
from datetime import datetime


def generate_pdf_report(title: str, data: dict) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)

    styles = getSampleStyleSheet()
    elements = []

    # 🔷 HEADER
    elements.append(Paragraph("<b>MOMA.HOUSE</b>", styles["Title"]))
    elements.append(Paragraph("PREMIUM PROPERTY MANAGEMENT", styles["Normal"]))
    elements.append(Spacer(1, 12))

    # 🔷 TITLE
    elements.append(Paragraph(f"<b>{title}</b>", styles["Heading2"]))
    elements.append(Paragraph(
        f"{data.get('period_start')} — {data.get('period_end')}",
        styles["Normal"]
    ))
    elements.append(Paragraph(
        f"Generated: {datetime.utcnow().strftime('%d/%m/%Y, %H:%M:%S')}",
        styles["Normal"]
    ))

    elements.append(Spacer(1, 20))

    # 🔷 METRICS GRID (2x2)
    metrics = [
        ["Total Bookings", "Total Revenue"],
        [data.get("total_bookings", 0), f"${data.get('total_revenue', 0)}"],
        ["Total Nights", "Avg Booking Value"],
        [data.get("total_nights", 0), f"${data.get('avg_booking_value', 0)}"],
    ]

    metrics_table = Table(metrics, colWidths=[250, 250])

    metrics_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("BACKGROUND", (0, 2), (-1, 2), colors.lightgrey),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("PADDING", (0, 0), (-1, -1), 10),
    ]))

    elements.append(metrics_table)
    elements.append(Spacer(1, 20))

    # 🔷 Revenue by Channel
    elements.append(Paragraph("<b>Revenue by Channel</b>", styles["Heading3"]))
    elements.append(Spacer(1, 10))

    channel_data = data.get("revenue_by_channel", [])
    for ch in channel_data:
        elements.append(Paragraph(
            f"{ch['platform']} ({ch['count']}) ${ch['revenue']}",
            styles["Normal"]
        ))

    elements.append(Spacer(1, 20))

    # 🔷 Revenue by Property
    elements.append(Paragraph("<b>Revenue by Property</b>", styles["Heading3"]))
    elements.append(Spacer(1, 10))

    property_data = data.get("revenue_by_property", [])
    for p in property_data:
        elements.append(Paragraph(
            f"{p['property_name']} ({p['count']}) ${p['revenue']}",
            styles["Normal"]
        ))

    elements.append(Spacer(1, 20))

    # 🔷 BOOKINGS TABLE
    elements.append(Paragraph("<b>All Bookings</b>", styles["Heading3"]))
    elements.append(Spacer(1, 10))

    table_data = [["Property", "Guest", "Dates", "Nts", "Channel", "Status", "Amount"]]

    bookings = data.get("bookings", [])

    for b in bookings:
        table_data.append([
            b.get("property_name"),
            b.get("guest_name"),
            f"{b.get('check_in')} - {b.get('check_out')}",
            b.get("nights"),
            b.get("channel"),
            b.get("status"),
            f"${b.get('revenue')}"
        ])

    booking_table = Table(table_data, repeatRows=1)

    booking_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.black),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))

    elements.append(booking_table)

    # 🔷 FOOTER
    elements.append(Spacer(1, 30))
    elements.append(Paragraph(
        "MOMA.HOUSE — Premium Property Management Confidential",
        styles["Normal"]
    ))

    doc.build(elements)

    pdf = buffer.getvalue()
    buffer.close()

    return pdf