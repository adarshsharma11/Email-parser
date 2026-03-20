# src/utils/report_pdf.py
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import inch, mm
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from io import BytesIO
from datetime import datetime
import re


class PDFGenerator:
    """Base PDF Generator with common styling and utilities"""
    
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._create_custom_styles()
        self.page_width = A4[0] - 2 * inch  # Usable width after margins
        self.page_height = A4[1] - 2 * inch

    def _create_custom_styles(self):
        """Create custom styles for consistent design matching frontend"""
        
        # Company header - large bold
        self.styles.add(ParagraphStyle(
            name='CompanyHeader',
            parent=self.styles['Title'],
            fontSize=24,
            textColor=colors.HexColor('#1a2c3e'),
            alignment=TA_LEFT,
            spaceAfter=0,
            fontName='Helvetica-Bold'
        ))
        
        # Company subheader
        self.styles.add(ParagraphStyle(
            name='CompanySubheader',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#6c757d'),
            alignment=TA_LEFT,
            spaceAfter=12,
        ))
        
        # Report title
        self.styles.add(ParagraphStyle(
            name='ReportTitle',
            parent=self.styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#2c3e50'),
            alignment=TA_LEFT,
            spaceBefore=12,
            spaceAfter=6,
            fontName='Helvetica-Bold'
        ))
        
        # Section header
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#2c3e50'),
            spaceBefore=12,
            spaceAfter=8,
            fontName='Helvetica-Bold'
        ))
        
        # Metric card title
        self.styles.add(ParagraphStyle(
            name='MetricTitle',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#6c757d'),
            alignment=TA_CENTER,
            spaceAfter=4,
        ))
        
        # Metric value
        self.styles.add(ParagraphStyle(
            name='MetricValue',
            parent=self.styles['Normal'],
            fontSize=24,
            textColor=colors.HexColor('#2c3e50'),
            alignment=TA_CENTER,
            fontName='Helvetica-Bold',
        ))
        
        # Table header style - Sky Blue
        self.styles.add(ParagraphStyle(
            name='TableHeader',
            parent=self.styles['Normal'],
            fontSize=9,
            textColor=colors.white,
            alignment=TA_LEFT,
            fontName='Helvetica-Bold',
        ))
        
        # Table cell style
        self.styles.add(ParagraphStyle(
            name='TableCell',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#2c3e50'),
            alignment=TA_LEFT,
            leading=10,
        ))
        
        # Table cell right align
        self.styles.add(ParagraphStyle(
            name='TableCellRight',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#2c3e50'),
            alignment=TA_RIGHT,
            leading=10,
        ))
        
        # Table cell center align
        self.styles.add(ParagraphStyle(
            name='TableCellCenter',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#2c3e50'),
            alignment=TA_CENTER,
            leading=10,
        ))
        
        # Footer style
        self.styles.add(ParagraphStyle(
            name='Footer',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#adb5bd'),
            alignment=TA_CENTER,
        ))

    def _add_header(self, elements, title, period_start, period_end):
        """Add consistent header to all reports"""
        # Company name
        elements.append(Paragraph("MOMA.HOUSE", self.styles['CompanyHeader']))
        elements.append(Paragraph("PREMIUM PROPERTY MANAGEMENT", self.styles['CompanySubheader']))
        elements.append(Spacer(1, 8))
        
        # Report title
        elements.append(Paragraph(title, self.styles['ReportTitle']))
        
        # Date range
        date_range = f"{period_start} — {period_end}"
        elements.append(Paragraph(date_range, self.styles['MetricTitle']))
        
        # Generated timestamp
        generated = f"Generated: {datetime.now().strftime('%d/%m/%Y, %H:%M:%S')}"
        elements.append(Paragraph(generated, self.styles['MetricTitle']))
        elements.append(Spacer(1, 20))

    def _add_footer(self, elements, page_number=None):
        """Add consistent footer"""
        elements.append(Spacer(1, 30))
        elements.append(Paragraph(
            "MOMA.HOUSE — Premium Property Management Confidential",
            self.styles['Footer']
        ))

    def _wrap_text(self, text, max_length=30):
        """Wrap long text to prevent overflow"""
        if not text:
            return ""
        text = str(text)
        if len(text) <= max_length:
            return text
        return text[:max_length-3] + "..."

    def _format_date(self, date_value):
        """Format date consistently"""
        if not date_value:
            return ""
        try:
            if hasattr(date_value, 'strftime'):
                return date_value.strftime("%Y-%m-%d")
            elif isinstance(date_value, str):
                # Try to parse and format
                return date_value[:10] if len(date_value) >= 10 else date_value
            else:
                return str(date_value)[:10]
        except:
            return str(date_value)[:10]


class BookingSummaryPDF(PDFGenerator):
    """Booking Summary Report - Matches design requirements"""
    
    def generate(self, data: dict) -> bytes:
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, 
                               topMargin=0.75*inch, bottomMargin=0.5*inch, 
                               leftMargin=0.5*inch, rightMargin=0.5*inch)
        elements = []
        
        # Header
        self._add_header(elements, "Booking Summary", 
                        data.get('period_start', ''), data.get('period_end', ''))
        
        # Metrics Cards
        total_bookings = data.get('total_bookings', 0)
        total_revenue = data.get('total_revenue', 0)
        avg_booking = data.get('average_booking_value', 0)
        
        metrics_data = [
            [str(total_bookings), f"${total_revenue:,.2f}", f"${avg_booking:,.2f}"],
            ["Total Bookings", "Total Revenue", "Avg Booking Value"]
        ]
        
        metrics_table = Table(metrics_data, colWidths=[doc.width/3, doc.width/3, doc.width/3])
        metrics_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('ALIGN', (0, 1), (-1, 1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTSIZE', (0, 0), (-1, 0), 24),
            ('FONTSIZE', (0, 1), (-1, 1), 10),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
            ('TEXTCOLOR', (0, 1), (-1, 1), colors.HexColor('#6c757d')),
            ('TOPPADDING', (0, 0), (-1, 0), 15),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 5),
            ('TOPPADDING', (0, 1), (-1, 1), 5),
        ]))
        elements.append(metrics_table)
        elements.append(Spacer(1, 25))
        
        # Revenue by Channel
        elements.append(Paragraph("Revenue by Channel", self.styles['SectionHeader']))
        
        channel_data = data.get('by_channel', [])
        if channel_data:
            for ch in channel_data:
                elements.append(Paragraph(
                    f"• {self._wrap_text(ch.get('channel', ''), 20)} ({ch.get('count', 0)}) ${ch.get('revenue', 0):,.2f}",
                    self.styles['TableCell']
                ))
                elements.append(Spacer(1, 2))
        else:
            elements.append(Paragraph("No data available", self.styles['TableCell']))
        
        elements.append(Spacer(1, 20))
        
        # Revenue by Property
        elements.append(Paragraph("Revenue by Property", self.styles['SectionHeader']))
        
        property_data = data.get('by_property', [])
        if property_data:
            for p in property_data:
                elements.append(Paragraph(
                    f"• {self._wrap_text(p.get('property_name', ''), 25)} ({p.get('count', 0)}) ${p.get('revenue', 0):,.2f}",
                    self.styles['TableCell']
                ))
                elements.append(Spacer(1, 2))
        else:
            elements.append(Paragraph("No data available", self.styles['TableCell']))
        
        elements.append(Spacer(1, 20))
        
        # All Bookings Table
        elements.append(Paragraph("All Bookings", self.styles['SectionHeader']))
        
        bookings = data.get('bookings', [])
        if bookings:
            # Calculate column widths based on content
            col_widths = [doc.width * 0.18, doc.width * 0.14, doc.width * 0.22, 
                          doc.width * 0.05, doc.width * 0.12, doc.width * 0.1, doc.width * 0.12]
            
            # Table headers with sky blue background
            table_data = [[
                Paragraph("<b>Property</b>", self.styles['TableHeader']),
                Paragraph("<b>Guest</b>", self.styles['TableHeader']),
                Paragraph("<b>Dates</b>", self.styles['TableHeader']),
                Paragraph("<b>Nts</b>", self.styles['TableHeader']),
                Paragraph("<b>Channel</b>", self.styles['TableHeader']),
                Paragraph("<b>Status</b>", self.styles['TableHeader']),
                Paragraph("<b>Amount</b>", self.styles['TableHeader'])
            ]]
            
            for booking in bookings[:25]:  # Limit to 25 per page
                check_in = self._format_date(booking.get('check_in', ''))
                check_out = self._format_date(booking.get('check_out', ''))
                date_range = f"{check_in} – {check_out}" if check_in and check_out else "N/A"
                
                table_data.append([
                    self._wrap_text(booking.get('property_name', ''), 20),
                    self._wrap_text(booking.get('guest_name', ''), 15),
                    date_range,
                    str(booking.get('nights', 0)),
                    booking.get('channel', '')[:12],
                    booking.get('status', 'Confirmed'),
                    f"${booking.get('total_amount', 0):,.2f}"
                ])
            
            booking_table = Table(table_data, colWidths=col_widths, repeatRows=1)
            booking_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#00BFFF')),  # Sky Blue
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
                ('ALIGN', (3, 0), (3, -1), 'CENTER'),
                ('ALIGN', (6, 0), (6, -1), 'RIGHT'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('PADDING', (0, 0), (-1, -1), 4),
                ('FONTSIZE', (0, 1), (-1, -1), 7),
                ('LEADING', (0, 1), (-1, -1), 9),
            ]))
            elements.append(booking_table)
            
            if len(bookings) > 25:
                elements.append(Spacer(1, 8))
                elements.append(Paragraph(
                    f"Showing first 25 of {len(bookings)} bookings",
                    self.styles['Footer']
                ))
        else:
            elements.append(Paragraph("No bookings found for this period", self.styles['TableCell']))
        
        # Footer
        self._add_footer(elements)
        
        doc.build(elements)
        pdf = buffer.getvalue()
        buffer.close()
        return pdf


class PerformanceComparisonPDF(PDFGenerator):
    """Performance Comparison Report - Fixed layout and overflow issues"""
    
    def generate(self, data: dict) -> bytes:
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, 
                               topMargin=0.75*inch, bottomMargin=0.5*inch,
                               leftMargin=0.5*inch, rightMargin=0.5*inch)
        elements = []
        
        # Get period dates
        current = data.get('current_period', {})
        period_start = current.get('start', data.get('period_start', ''))
        period_end = current.get('end', data.get('period_end', ''))
        
        # Header
        self._add_header(elements, "Performance Comparison", period_start, period_end)
        
        # Key Metrics Comparison
        elements.append(Paragraph("Key Metrics Comparison", self.styles['SectionHeader']))
        
        metrics = data.get('metrics_comparison', [])
        if metrics:
            # Calculate column widths
            col_widths = [doc.width * 0.2, doc.width * 0.25, doc.width * 0.25, doc.width * 0.15, doc.width * 0.15]
            
            # Table headers with sky blue
            comparison_data = [[
                Paragraph("<b>Metric</b>", self.styles['TableHeader']),
                Paragraph("<b>Current</b>", self.styles['TableHeader']),
                Paragraph("<b>Previous</b>", self.styles['TableHeader']),
                Paragraph("<b>Change</b>", self.styles['TableHeader']),
                Paragraph("<b>Trend</b>", self.styles['TableHeader'])
            ]]
            
            for metric in metrics:
                current_val = metric.get('current_value', 0)
                previous_val = metric.get('previous_value', 0)
                change_pct = metric.get('change_percentage', 0)
                trend = metric.get('trend', 'neutral')
                
                # Format values based on metric type
                metric_name = metric.get('metric', '')
                if 'Revenue' in metric_name:
                    current_str = f"${current_val:,.2f}" if isinstance(current_val, (int, float)) else str(current_val)
                    previous_str = f"${previous_val:,.2f}" if isinstance(previous_val, (int, float)) else str(previous_val)
                elif 'Occupancy' in metric_name:
                    current_str = f"{current_val:.2f}%" if isinstance(current_val, (int, float)) else str(current_val)
                    previous_str = f"{previous_val:.2f}%" if isinstance(previous_val, (int, float)) else str(previous_val)
                elif 'ADR' in metric_name:
                    current_str = f"${current_val:.2f}" if isinstance(current_val, (int, float)) else str(current_val)
                    previous_str = f"${previous_val:.2f}" if isinstance(previous_val, (int, float)) else str(previous_val)
                else:
                    current_str = str(current_val)
                    previous_str = str(previous_val)
                
                trend_symbol = "▲" if change_pct > 0 else "▼" if change_pct < 0 else "→"
                trend_color = "#28a745" if change_pct > 0 else "#dc3545" if change_pct < 0 else "#6c757d"
                
                comparison_data.append([
                    metric_name,
                    current_str,
                    previous_str,
                    f"{change_pct:+.1f}%",
                    f"{trend_symbol} {abs(change_pct):.1f}%"
                ])
            
            comparison_table = Table(comparison_data, colWidths=col_widths, repeatRows=1)
            comparison_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#00BFFF')),  # Sky Blue
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
                ('ALIGN', (3, 0), (4, -1), 'RIGHT'),
                ('ALIGN', (1, 0), (2, -1), 'RIGHT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('PADDING', (0, 0), (-1, -1), 8),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
            ]))
            elements.append(comparison_table)
            elements.append(Spacer(1, 20))
        
        # Period Summary - Side by side layout
        elements.append(Paragraph("Period Summary", self.styles['SectionHeader']))
        
        current_period = data.get('current_period', {})
        previous_period = data.get('previous_period', {})
        
        # Create side-by-side tables
        col_width = doc.width / 2 - 10
        
        current_data = [
            ["Current Period"],
            ["Revenue", f"${current_period.get('total_revenue', 0):,.2f}"],
            ["Bookings", str(current_period.get('total_bookings', 0))],
            ["ADR", f"${current_period.get('average_daily_rate', 0):,.2f}"],
            ["Occupancy", f"{current_period.get('occupancy_rate', 0):.2f}%"],
            ["Nights", str(current_period.get('total_nights', 0))],
        ]
        
        previous_data = [
            ["Previous Period"],
            ["Revenue", f"${previous_period.get('total_revenue', 0):,.2f}"],
            ["Bookings", str(previous_period.get('total_bookings', 0))],
            ["ADR", f"${previous_period.get('average_daily_rate', 0):,.2f}"],
            ["Occupancy", f"{previous_period.get('occupancy_rate', 0):.2f}%"],
            ["Nights", str(previous_period.get('total_nights', 0))],
        ]
        
        # Create tables with proper formatting
        current_table = Table(current_data, colWidths=[col_width * 0.4, col_width * 0.6])
        previous_table = Table(previous_data, colWidths=[col_width * 0.4, col_width * 0.6])
        
        for table in [current_table, previous_table]:
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e9ecef')),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
                ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
                ('PADDING', (0, 0), (-1, -1), 8),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
            ]))
        
        # Container for side-by-side layout
        summary_container = Table([[current_table, previous_table]], colWidths=[col_width, col_width])
        summary_container.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(summary_container)
        elements.append(Spacer(1, 20))
        
        # Revenue Trend - Fixed date formatting and overflow
        elements.append(Paragraph("Revenue Trend", self.styles['SectionHeader']))
        
        revenue_trend = data.get('revenue_trend', [])
        if revenue_trend:
            # Calculate column widths
            trend_col_widths = [doc.width * 0.3, doc.width * 0.35, doc.width * 0.35]
            
            trend_data = [[
                Paragraph("<b>Period</b>", self.styles['TableHeader']),
                Paragraph("<b>Current</b>", self.styles['TableHeader']),
                Paragraph("<b>Previous</b>", self.styles['TableHeader'])
            ]]
            
            # Filter and format trend data - remove invalid dates
            valid_trends = []
            for trend in revenue_trend:
                period = trend.get('date', '')
                # Validate date format
                if period and len(str(period)) >= 10 and '20' in str(period):
                    # Format date consistently
                    if isinstance(period, str) and len(period) > 10:
                        period = period[:10]
                    valid_trends.append(trend)
            
            # Limit to 15 rows for better display
            for trend in valid_trends[:15]:
                period = self._format_date(trend.get('date', ''))
                current_val = trend.get('current', 0)
                previous_val = trend.get('previous', 0)
                
                trend_data.append([
                    period,
                    f"${current_val:,.2f}" if current_val > 0 else "$0.00",
                    f"${previous_val:,.2f}" if previous_val > 0 else "$0.00"
                ])
            
            if len(trend_data) > 1:  # Has data rows
                trend_table = Table(trend_data, colWidths=trend_col_widths, repeatRows=1)
                trend_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#00BFFF')),  # Sky Blue
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
                    ('ALIGN', (1, 0), (2, -1), 'RIGHT'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('PADDING', (0, 0), (-1, -1), 6),
                    ('FONTSIZE', (0, 0), (-1, 0), 8),
                    ('FONTSIZE', (0, 1), (-1, -1), 7),
                ]))
                elements.append(trend_table)
            else:
                elements.append(Paragraph("No trend data available", self.styles['TableCell']))
        
        # Footer
        self._add_footer(elements)
        
        doc.build(elements)
        pdf = buffer.getvalue()
        buffer.close()
        return pdf


class OwnerStatementPDF(PDFGenerator):
    """Owner Statement Report with fixed layout"""
    
    def generate(self, data: dict) -> bytes:
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, 
                               topMargin=0.75*inch, bottomMargin=0.5*inch,
                               leftMargin=0.5*inch, rightMargin=0.5*inch)
        elements = []
        
        # Header
        self._add_header(elements, "Owner Statement", 
                        data.get('period_start', ''), data.get('period_end', ''))
        
        properties = data.get('properties', [])
        
        for idx, property_data in enumerate(properties):
            # Property name and summary
            property_name = property_data.get('property_name', 'Unknown Property')
            occupancy = property_data.get('occupancy_rate', 0)
            nights = property_data.get('nights_booked', 0)
            adr = property_data.get('average_daily_rate', 0)
            
            elements.append(Paragraph(self._wrap_text(property_name, 40), self.styles['SectionHeader']))
            elements.append(Paragraph(
                f"Occupancy: {occupancy:.2f}% | Nights: {nights} | ADR: ${adr:.2f}",
                self.styles['TableCell']
            ))
            elements.append(Spacer(1, 12))
            
            # Bookings for this property
            bookings = property_data.get('bookings', [])
            if bookings:
                col_widths = [doc.width * 0.27, doc.width * 0.33, doc.width * 0.08, 
                              doc.width * 0.12, doc.width * 0.15]
                
                table_data = [[
                    Paragraph("<b>Guest</b>", self.styles['TableHeader']),
                    Paragraph("<b>Dates</b>", self.styles['TableHeader']),
                    Paragraph("<b>Nts</b>", self.styles['TableHeader']),
                    Paragraph("<b>Channel</b>", self.styles['TableHeader']),
                    Paragraph("<b>Revenue</b>", self.styles['TableHeader'])
                ]]
                
                for booking in bookings[:15]:  # Limit per property
                    check_in = self._format_date(booking.get('check_in', ''))
                    check_out = self._format_date(booking.get('check_out', ''))
                    date_range = f"{check_in} – {check_out}" if check_in and check_out else "N/A"
                    
                    table_data.append([
                        self._wrap_text(booking.get('guest_name', ''), 20),
                        date_range,
                        str(booking.get('nights', 0)),
                        booking.get('channel', '')[:10],
                        f"${booking.get('revenue', 0):,.2f}"
                    ])
                
                bookings_table = Table(table_data, colWidths=col_widths, repeatRows=1)
                bookings_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#00BFFF')),  # Sky Blue
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 8),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
                    ('ALIGN', (2, 0), (2, -1), 'CENTER'),
                    ('ALIGN', (4, 0), (4, -1), 'RIGHT'),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('PADDING', (0, 0), (-1, -1), 6),
                    ('FONTSIZE', (0, 1), (-1, -1), 7),
                ]))
                elements.append(bookings_table)
                elements.append(Spacer(1, 15))
            
            # Financial Summary
            total_revenue = property_data.get('total_revenue', 0)
            channel_fees = property_data.get('channel_fees', 0)
            cleaning_fees = property_data.get('cleaning_fees_collected', 0)
            maintenance = property_data.get('maintenance_expenses', 0)
            net_revenue = property_data.get('net_revenue', 0)
            
            financial_data = [
                ["Revenue", f"${total_revenue:,.2f}"],
                ["Channel Fees", f"-${channel_fees:,.2f}"],
                ["Cleaning", f"-${cleaning_fees:,.2f}"],
                ["Maintenance", f"-${maintenance:,.2f}"],
                ["Net Revenue", f"${net_revenue:,.2f}"]
            ]
            
            financial_table = Table(financial_data, colWidths=[doc.width/2, doc.width/2])
            financial_table.setStyle(TableStyle([
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8f9fa')),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e9ecef')),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
                ('PADDING', (0, 0), (-1, -1), 8),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
            ]))
            elements.append(financial_table)
            elements.append(Spacer(1, 20))
            
            # Add page break between properties except last
            if idx < len(properties) - 1:
                elements.append(PageBreak())
        
        # Global Summary for multiple properties
        if len(properties) > 1:
            elements.append(Paragraph("Global Summary", self.styles['SectionHeader']))
            
            global_data = [
                ["Total Rental Revenue", f"${data.get('rental_revenue', 0):,.2f}"],
                ["Total Services Revenue", f"${data.get('services_revenue', 0):,.2f}"],
                ["Total Revenue", f"${data.get('total_revenue', 0):,.2f}"],
                ["Management Fee (10%)", f"-${data.get('management_fee', 0):,.2f}"],
                ["Total Payout", f"${data.get('total_payout', 0):,.2f}"]
            ]
            
            global_table = Table(global_data, colWidths=[doc.width/2, doc.width/2])
            global_table.setStyle(TableStyle([
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e9ecef')),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
                ('PADDING', (0, 0), (-1, -1), 8),
            ]))
            elements.append(global_table)
        
        # Footer
        self._add_footer(elements)
        
        doc.build(elements)
        pdf = buffer.getvalue()
        buffer.close()
        return pdf


class OccupancyReportPDF(PDFGenerator):
    """Occupancy Report with fixed layout"""
    
    def generate(self, data: dict) -> bytes:
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, 
                               topMargin=0.75*inch, bottomMargin=0.5*inch,
                               leftMargin=0.5*inch, rightMargin=0.5*inch)
        elements = []
        
        # Header
        self._add_header(elements, "Occupancy Report", 
                        data.get('period_start', ''), data.get('period_end', ''))
        
        # Overall metrics
        overall_occupancy = data.get('overall_occupancy', 0)
        total_properties = len(data.get('properties', []))
        total_nights = data.get('total_booked_nights', 0)
        
        metrics_data = [
            [f"{overall_occupancy:.1f}%", str(total_properties), str(total_nights)],
            ["Avg Occupancy", "Properties", "Total Nights"]
        ]
        
        metrics_table = Table(metrics_data, colWidths=[doc.width/3, doc.width/3, doc.width/3])
        metrics_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('ALIGN', (0, 1), (-1, 1), 'CENTER'),
            ('FONTSIZE', (0, 0), (-1, 0), 24),
            ('FONTSIZE', (0, 1), (-1, 1), 10),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('TEXTCOLOR', (0, 1), (-1, 1), colors.HexColor('#6c757d')),
            ('TOPPADDING', (0, 0), (-1, 0), 20),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ]))
        elements.append(metrics_table)
        elements.append(Spacer(1, 25))
        
        # Occupancy by Property
        elements.append(Paragraph("Occupancy by Property", self.styles['SectionHeader']))
        
        properties = data.get('properties', [])
        for prop in properties:
            prop_name = self._wrap_text(prop.get('property_name', 'Unknown'), 35)
            occupancy = prop.get('occupancy_rate', 0)
            elements.append(Paragraph(f"• {prop_name}: {occupancy:.1f}%", self.styles['TableCell']))
            elements.append(Spacer(1, 2))
        
        elements.append(Spacer(1, 20))
        
        # Property Details Table
        elements.append(Paragraph("Property Details", self.styles['SectionHeader']))
        
        if properties:
            col_widths = [doc.width * 0.27, doc.width * 0.12, doc.width * 0.12, 
                          doc.width * 0.12, doc.width * 0.12, doc.width * 0.13, doc.width * 0.12]
            
            details_data = [[
                Paragraph("<b>Property</b>", self.styles['TableHeader']),
                Paragraph("<b>Occupancy</b>", self.styles['TableHeader']),
                Paragraph("<b>Available</b>", self.styles['TableHeader']),
                Paragraph("<b>Booked</b>", self.styles['TableHeader']),
                Paragraph("<b>Blocked</b>", self.styles['TableHeader']),
                Paragraph("<b>Revenue</b>", self.styles['TableHeader']),
                Paragraph("<b>ADR</b>", self.styles['TableHeader'])
            ]]
            
            for prop in properties:
                details_data.append([
                    self._wrap_text(prop.get('property_name', ''), 22),
                    f"{prop.get('occupancy_rate', 0):.1f}%",
                    str(prop.get('available_nights', 0)),
                    str(prop.get('booked_nights', 0)),
                    str(prop.get('blocked_nights', 0)),
                    f"${prop.get('revenue', 0):,.2f}",
                    f"${prop.get('average_daily_rate', 0):,.2f}"
                ])
            
            details_table = Table(details_data, colWidths=col_widths, repeatRows=1)
            details_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#00BFFF')),  # Sky Blue
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 7),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
                ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('PADDING', (0, 0), (-1, -1), 5),
                ('FONTSIZE', (0, 1), (-1, -1), 7),
            ]))
            elements.append(details_table)
        
        # Footer
        self._add_footer(elements)
        
        doc.build(elements)
        pdf = buffer.getvalue()
        buffer.close()
        return pdf


class ServiceRevenuePDF(PDFGenerator):
    """Service Revenue Report with fixed layout"""
    
    def generate(self, data: dict) -> bytes:
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, 
                               topMargin=0.75*inch, bottomMargin=0.5*inch,
                               leftMargin=0.5*inch, rightMargin=0.5*inch)
        elements = []
        
        # Header
        self._add_header(elements, "Service Revenue Report", 
                        data.get('period_start', ''), data.get('period_end', ''))
        
        # Service Performance Table
        elements.append(Paragraph("Service Performance", self.styles['SectionHeader']))
        
        services = data.get('services', [])
        if services:
            col_widths = [doc.width * 0.22, doc.width * 0.15, doc.width * 0.15, 
                          doc.width * 0.15, doc.width * 0.15, doc.width * 0.13]
            
            service_data = [[
                Paragraph("<b>Service</b>", self.styles['TableHeader']),
                Paragraph("<b>Revenue</b>", self.styles['TableHeader']),
                Paragraph("<b>Bookings</b>", self.styles['TableHeader']),
                Paragraph("<b>Avg Price</b>", self.styles['TableHeader']),
                Paragraph("<b>Trend</b>", self.styles['TableHeader']),
                Paragraph("<b>Share</b>", self.styles['TableHeader'])
            ]]
            
            total_rev = data.get('total_revenue', 0)
            for service in services:
                share = (service.get('total_revenue', 0) / total_rev * 100) if total_rev > 0 else 0
                trend = service.get('trend', 0)
                trend_symbol = "▲" if trend > 0 else "▼" if trend < 0 else "→"
                
                service_data.append([
                    self._wrap_text(service.get('service_name', ''), 20),
                    f"${service.get('total_revenue', 0):,.2f}",
                    str(service.get('bookings_count', 0)),
                    f"${service.get('average_price', 0):,.2f}",
                    f"{trend_symbol} {abs(trend):.1f}%",
                    f"{share:.1f}%"
                ])
            
            service_table = Table(service_data, colWidths=col_widths, repeatRows=1)
            service_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#00BFFF')),  # Sky Blue
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
                ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('PADDING', (0, 0), (-1, -1), 6),
                ('FONTSIZE', (0, 1), (-1, -1), 7),
            ]))
            elements.append(service_table)
            elements.append(Spacer(1, 20))
        
        # Revenue by Service
        elements.append(Paragraph("Revenue by Service", self.styles['SectionHeader']))
        
        total_rev = data.get('total_revenue', 0)
        for service in services:
            revenue = service.get('total_revenue', 0)
            share = (revenue / total_rev * 100) if total_rev > 0 else 0
            elements.append(Paragraph(
                f"• {self._wrap_text(service.get('service_name', ''), 25)}: ${revenue:,.2f} ({share:.1f}%)",
                self.styles['TableCell']
            ))
            elements.append(Spacer(1, 2))
        
        elements.append(Spacer(1, 20))
        
        # Top Properties for Services
        elements.append(Paragraph("Top Properties for Services", self.styles['SectionHeader']))
        
        top_properties = data.get('top_properties', [])
        for prop in top_properties[:5]:
            elements.append(Paragraph(
                f"• {self._wrap_text(prop.get('property_name', ''), 30)}: {prop.get('bookings', 0)} services, ${prop.get('revenue', 0):,.2f}",
                self.styles['TableCell']
            ))
            elements.append(Spacer(1, 2))
        
        # Footer
        self._add_footer(elements)
        
        doc.build(elements)
        pdf = buffer.getvalue()
        buffer.close()
        return pdf


class ServiceProviderPDF(PDFGenerator):
    """Service Provider Report with fixed layout"""
    
    def generate(self, data: dict) -> bytes:
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, 
                               topMargin=0.75*inch, bottomMargin=0.5*inch,
                               leftMargin=0.5*inch, rightMargin=0.5*inch)
        elements = []
        
        # Header
        self._add_header(elements, "Service Provider Report", 
                        data.get('period_start', ''), data.get('period_end', ''))
        
        # Provider Info
        elements.append(Paragraph(f"Provider: {data.get('provider_name', 'N/A')}", self.styles['SectionHeader']))
        elements.append(Paragraph(f"Service Type: {data.get('service_type', 'N/A')}", self.styles['TableCell']))
        elements.append(Spacer(1, 15))
        
        # Job Details Table
        elements.append(Paragraph("Job Details", self.styles['SectionHeader']))
        
        jobs = data.get('jobs', [])
        if jobs:
            col_widths = [doc.width * 0.12, doc.width * 0.28, doc.width * 0.18, 
                          doc.width * 0.18, doc.width * 0.1, doc.width * 0.08, doc.width * 0.06]
            
            job_data = [[
                Paragraph("<b>Date</b>", self.styles['TableHeader']),
                Paragraph("<b>Property</b>", self.styles['TableHeader']),
                Paragraph("<b>Guest</b>", self.styles['TableHeader']),
                Paragraph("<b>Service</b>", self.styles['TableHeader']),
                Paragraph("<b>Status</b>", self.styles['TableHeader']),
                Paragraph("<b>Amount</b>", self.styles['TableHeader']),
                Paragraph("<b>Tip</b>", self.styles['TableHeader'])
            ]]
            
            for job in jobs[:20]:
                job_data.append([
                    self._format_date(job.get('date', ''))[:10],
                    self._wrap_text(job.get('property_name', ''), 20),
                    self._wrap_text(job.get('guest_name', ''), 15),
                    self._wrap_text(job.get('service_details', ''), 15),
                    job.get('status', 'Completed')[:10],
                    f"${job.get('amount', 0):,.2f}",
                    f"${job.get('tip', 0):,.2f}"
                ])
            
            job_table = Table(job_data, colWidths=col_widths, repeatRows=1)
            job_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#00BFFF')),  # Sky Blue
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 7),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
                ('ALIGN', (5, 0), (6, -1), 'RIGHT'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('PADDING', (0, 0), (-1, -1), 5),
                ('FONTSIZE', (0, 1), (-1, -1), 7),
            ]))
            elements.append(job_table)
            elements.append(Spacer(1, 20))
        
        # Financial Summary
        elements.append(Paragraph("Financial Summary", self.styles['SectionHeader']))
        
        gross_revenue = data.get('total_revenue', 0)
        commission_rate = data.get('commission_rate', 10)
        commission = data.get('commission_amount', 0)
        net_payout = data.get('net_payout', 0)
        
        summary_data = [
            ["Gross Revenue", f"${gross_revenue:,.2f}"],
            ["Tips", "$0.00"],
            [f"Commission ({commission_rate:.0f}%)", f"-${commission:,.2f}"],
            ["Net Payout", f"${net_payout:,.2f}"]
        ]
        
        summary_table = Table(summary_data, colWidths=[doc.width/2, doc.width/2])
        summary_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8f9fa')),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e9ecef')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('PADDING', (0, 0), (-1, -1), 10),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
        ]))
        elements.append(summary_table)
        
        # Footer
        self._add_footer(elements)
        
        doc.build(elements)
        pdf = buffer.getvalue()
        buffer.close()
        return pdf


# Factory function to get the appropriate generator
def generate_pdf_report(title: str, data: dict) -> bytes:
    """
    Generate PDF report based on title and data.
    This is the main entry point used by report_service.py
    
    Args:
        title: Report title (e.g., "Booking Summary Report")
        data: Dictionary containing report data
    
    Returns:
        PDF bytes
    """
    # Map title to generator
    if "Booking Summary" in title:
        generator = BookingSummaryPDF()
    elif "Owner Statement" in title:
        generator = OwnerStatementPDF()
    elif "Occupancy" in title:
        generator = OccupancyReportPDF()
    elif "Service Revenue" in title:
        generator = ServiceRevenuePDF()
    elif "Service Provider" in title:
        generator = ServiceProviderPDF()
    elif "Performance Comparison" in title:
        generator = PerformanceComparisonPDF()
    else:
        # Default to booking summary
        generator = BookingSummaryPDF()
    
    return generator.generate(data)


# Add this function to report_pdf.py (if not already present)

def get_report_filename(report_type: str, period_start: str = None, period_end: str = None) -> str:
    """
    Generate proper filename based on report type
    
    Args:
        report_type: Type of report (e.g., "Booking Summary", "Performance Comparison")
        period_start: Start date for the report (format: YYYY-MM-DD)
        period_end: End date for the report (format: YYYY-MM-DD)
    
    Returns:
        Proper filename like "booking_summary_2026-02-01_to_2026-02-28.pdf"
    """
    # Convert report type to filename format
    filename_map = {
        "Booking Summary": "booking_summary",
        "Owner Statement": "owner_statement",
        "Occupancy Report": "occupancy_report",
        "Service Revenue": "service_revenue",
        "Service Provider": "service_provider",
        "Performance Comparison": "performance_comparison",
        "Booking Summary Report": "booking_summary",
        "Owner Statement Report": "owner_statement",
        "Occupancy Report": "occupancy_report",
        "Service Revenue Report": "service_revenue",
        "Service Provider Report": "service_provider",
        "Performance Comparison Report": "performance_comparison",
    }
    
    # Clean up report type
    clean_type = report_type.strip()
    base_name = filename_map.get(clean_type, "report")
    
    # Add date range if available
    if period_start and period_end:
        # Remove any slashes or invalid characters from dates
        clean_start = period_start.replace("/", "-").replace("\\", "-")
        clean_end = period_end.replace("/", "-").replace("\\", "-")
        return f"{base_name}_{clean_start}_to_{clean_end}.pdf"
    elif period_start:
        clean_start = period_start.replace("/", "-").replace("\\", "-")
        return f"{base_name}_{clean_start}.pdf"
    else:
        from datetime import datetime
        return f"{base_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"