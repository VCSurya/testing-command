

from __future__ import annotations

import datetime
import logging
from io import BytesIO
from functools import lru_cache
from flask import Blueprint, jsonify, send_file, current_app
from utils import get_db_connection
# ── ReportLab (imported once at module level) ────────────────────────────────
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer,
)

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Module-level style cache  (built once, shared across all requests)
# ─────────────────────────────────────────────────────────────────────────────
_BASE_STYLES = getSampleStyleSheet()

STYLE_TITLE = ParagraphStyle(
    "CompanyTitle",
    parent=_BASE_STYLES["Heading1"],
    fontSize=18,
    fontName="Helvetica-Bold",
    alignment=TA_CENTER,
    spaceAfter=0,
)
STYLE_SUBTITLE = ParagraphStyle(
    "CompanyInfo",
    parent=_BASE_STYLES["Normal"],
    fontSize=9,
    alignment=TA_CENTER,
    spaceAfter=0,
)
STYLE_NORMAL = _BASE_STYLES["Normal"]
STYLE_FOOTER = ParagraphStyle(
    "Footer",
    parent=_BASE_STYLES["Normal"],
    alignment=TA_CENTER,
    fontName="Helvetica-Bold",
)
STYLE_SIGNATURE = ParagraphStyle(
    "SignatureStyle",
    parent=_BASE_STYLES["Normal"],
    alignment=TA_RIGHT,
    fontSize=12,
)

# Pre-built TableStyle objects (immutable – safe to share)
_INVOICE_HEADER_STYLE = TableStyle([
    ("ALIGN",        (0, 0), (1, 0), "LEFT"),
    ("ALIGN",        (0, 1), (1, 1), "LEFT"),
    ("GRID",         (0, 0), (1, 1), 0.5, colors.black),
    ("BACKGROUND",   (0, 0), (1, 0), colors.lightgrey),
    ("VALIGN",       (0, 0), (-1, -1), "TOP"),
    ("LEFTPADDING",  (0, 0), (-1, -1), 6),
    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ("TOPPADDING",   (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
])

_PRODUCT_TABLE_STYLE = TableStyle([
    ("BACKGROUND",   (0, 0), (-1, 0), colors.lightgrey),
    ("TEXTCOLOR",    (0, 0), (-1, 0), colors.black),
    ("ALIGN",        (0, 0), (-1, 0), "CENTER"),
    ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE",     (0, 0), (-1, 0), 9),
    ("BOTTOMPADDING",(0, 0), (-1, 0), 5),
    ("GRID",         (0, 0), (-1, -1), 0.5, colors.black),
    ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
    ("ALIGN",        (0, 1), (0, -1), "CENTER"),
    ("ALIGN",        (2, 1), (2, -1), "CENTER"),
    ("ALIGN",        (3, 1), (6, -1), "RIGHT"),
])

_TOTAL_TABLE_STYLE = TableStyle([
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("GRID",     (0, 0), (-1, -1), 0.5, colors.black),
    ("ALIGN",    (0, 0), (0, -1), "RIGHT"),
    ("ALIGN",    (1, 0), (-1, -1), "RIGHT"),
    ("ALIGN",    (2, 0), (2, 0), "CENTER"),
])

_TAX_TABLE_STYLE = TableStyle([
    ("BACKGROUND",   (0, 0), (-1, 0), colors.lightgrey),
    ("TEXTCOLOR",    (0, 0), (-1, 0), colors.black),
    ("ALIGN",        (0, 0), (-1, 0), "CENTER"),
    ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE",     (0, 0), (-1, 0), 9),
    ("GRID",         (0, 0), (-1, -1), 0.5, colors.black),
    ("ALIGN",        (1, 1), (-1, -1), "CENTER"),
    ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
])

_WORDS_TABLE_STYLE = TableStyle([
    ("BACKGROUND",   (0, 0), (0, 0), colors.lightgrey),
    ("FONTNAME",     (0, 0), (0, 0), "Helvetica-Bold"),
    ("GRID",         (0, 0), (0, -1), 0.5, colors.black),
    ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
])

_TERMS_TABLE_STYLE = TableStyle([
    ("BACKGROUND",   (0, 0), (0, 0), colors.lightgrey),
    ("FONTNAME",     (0, 0), (0, 0), "Helvetica-Bold"),
    ("GRID",         (0, 0), (0, -1), 0.5, colors.black),
    ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
])

_DELIVERY_TABLE_STYLE = TableStyle([
    ("BACKGROUND", (0, 0), (0, -1), colors.lightgrey),
    ("BACKGROUND", (3, 0), (3, -1), colors.lightgrey),
    ("FONTNAME",   (0, 0), (0, -1), "Helvetica-Bold"),
    ("FONTNAME",   (3, 0), (3, -1), "Helvetica-Bold"),
    ("FONTSIZE",   (0, 0), (-1, -1), 9),
    ("ALIGN",      (0, 0), (-1, -1), "LEFT"),
    ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
    ("GRID",       (0, 0), (1, -1), 0.5, colors.black),
    ("GRID",       (3, 0), (4, -1), 0.5, colors.black),
])

_TRANSPORT_TABLE_STYLE = TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
    ("TEXTCOLOR",  (0, 0), (-1, 0), colors.black),
    ("ALIGN",      (0, 0), (-1, 0), "CENTER"),
    ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
    ("ALIGN",      (0, 0), (-1, -1), "LEFT"),
    ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
    ("GRID",       (0, 0), (-1, -1), 0.5, colors.black),
])

# Static content
_TERMS_TEXT = "\n".join([
    "1. Goods once sold will not be taken back or exchanged",
    "2. No cancellation & No changes after confirm booking",
    "3. Your parcel will be dispatched within 3-4 working days",
    "4. packing & forwarding charges will be additional",
    "5. delivery charges not included in packing & forwarding charges",
    "6. Your complaint is only valid if you have a proper opening video of the parcel.\n"
    "   { from the seal pack parcel to the end without pause & cut }",
    "7. Your complaint is only valid for 2 days after you receive .",
    "8. Our Complain Number - 9638095151 ( Do message us on WhatsApp only )",
])

# Column widths (pre-computed tuples)
_COL_PRODUCT = [0.5*inch, 3.8*inch, 0.9*inch, 0.8*inch, 1*inch, 1*inch, 1*inch]
_COL_INVOICE  = [4*inch, 4*inch]
_COL_TAX      = [2*inch, 1.5*inch, 1.5*inch, 1.5*inch, 1.5*inch]
_COL_WORDS    = [8*inch]
_COL_DELIVERY = [1.5*inch, 2.3*inch, 0.2*inch, 1.5*inch, 2.5*inch]
_COL_TRANSPORT= [3.8*inch, 3.4*inch, 0.8*inch]

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _capitalize_words(text: str) -> str:
    """'some_word another' → 'Some Word Another'"""
    return " ".join(
        " ".join(part.capitalize() for part in word.split("_"))
        for word in text.split()
    )


# Pure-Python number-to-words (unchanged logic, extracted for clarity)
_ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _two_digits(n: int) -> str:
    if n < 20:
        return _ONES[n]
    tail = _ONES[n % 10]
    return _TENS[n // 10] + (" " + tail if tail else "")


def _three_digits(n: int) -> str:
    if n < 100:
        return _two_digits(n)
    tail = _two_digits(n % 100)
    return _ONES[n // 100] + " Hundred" + (" and " + tail if tail else "")


def _number_to_words(num: int) -> str:
    if num == 0:
        return "Zero"
    parts: list[str] = []
    for value, label in ((10_000_000, "Crore"), (100_000, "Lakh"), (1_000, "Thousand")):
        if num >= value:
            parts.append(_number_to_words(num // value) + " " + label)
            num %= value
    if num:
        parts.append(_three_digits(num))
    return " ".join(parts)


def _amount_in_words(amount: float) -> str:
    rupees = int(amount)
    paise = round((amount - rupees) * 100)
    text = _number_to_words(rupees) + " Rupees"
    if paise:
        text += f" and {_number_to_words(paise)} Paise"
    return text


# ─────────────────────────────────────────────────────────────────────────────
# Database helpers
# ─────────────────────────────────────────────────────────────────────────────




def _fetch_invoice_data(invoice_number: str) -> tuple[dict | None, list[dict], list[dict]]:
    """
    Call sp_get_invoice_pdf_data with the human-readable invoice number
    (e.g. 'DC1630B510'). The procedure resolves it to the integer id
    internally — no separate Python lookup needed.

    Returns (header_dict, products_list, charges_list).
    header_dict is None when the invoice number is unknown or not eligible.
    """
    conn = get_db_connection()
    if conn is None:
        raise RuntimeError("Database connection failed")

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.callproc("sp_get_invoice_pdf_data", (invoice_number,))

        header: dict | None = None
        products: list[dict] = []
        charges: list[dict] = []

        for idx, result in enumerate(cursor.stored_results()):
            rows = result.fetchall()
            if idx == 0:
                header = rows[0] if rows else None
            elif idx == 1:
                products = rows
            elif idx == 2:
                charges = rows

        cursor.close()
        return header, products, charges
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# PDF builder  (pure function – no I/O, easy to unit-test)
# ─────────────────────────────────────────────────────────────────────────────

def _build_pdf(header: dict, products: list[dict], charges: list[dict]) -> BytesIO:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=30, rightMargin=30,
        topMargin=10, bottomMargin=30,
    )

    # ── Unpack header ────────────────────────────────────────────────────────
    invoice_id       = header["invoice_id"]
    delivery_mode    = header["delivery_mode"]
    payment_mode     = header["payment_mode"]
    paid_amount      = float(header["paid_amount"])
    grand_total      = float(header["grand_total"])
    include_gst      = header["gst_included"]
    pay_confirmed    = header["payment_confirm_status"]
    transport_name   = header.get("transport_name") or ""
    transport_city   = header.get("transport_city") or ""
    transport_pincode= header.get("transport_pincode") or ""
    transport_days   = header.get("transport_days") or ""

    invoice_date = header.get("invoice_date")
    formatted_date = (
        invoice_date.strftime("%d/%m/%Y")
        if isinstance(invoice_date, datetime.datetime)
        else datetime.datetime.now().strftime("%d/%m/%Y")
    )

    customer = {
        "name":     header.get("c_name", ""),
        "mobile":   header.get("c_mobile", ""),
        "address":  header.get("c_address", ""),
        "pincode":  header.get("c_pincode", ""),
        "state":    header.get("c_state", ""),
        "salesman": header.get("salesman_name", ""),
    }

    # ── Products – single pass for table rows AND running totals ─────────────
    tax_rate = 18 if include_gst else 0
    product_rows = [
        ["S.NO.", "ITEMS", "QTY.", "RATE", f"TAX ({tax_rate}%)", "AMOUNT"]
    ]
    total_tax_amount = 0.0
    total_qty = 0

    for idx, p in enumerate(products, 1):
        qty       = int(p["quantity"])
        tax_price = float(p["gst_tax_amount"])
        total_qty       += qty
        total_tax_amount += tax_price
        product_rows.append([
            str(idx),
            p["product_name"],
            f"{qty} PCS",
            str(p["price"]),
            str(tax_price),
            str(p["total_amount"]),
        ])

    product_rows.append([])          # blank separator row
    for charge in charges:
        product_rows.append(["", charge["charge_name"], "", "", "", str(charge["amount"])])

    # ── Invoice header table ─────────────────────────────────────────────────
    bill_to = Paragraph(
        f"<b>BILL TO:</b><br/><br/>{customer['name']}<br/><br/>Mobile: {customer['mobile']}",
        STYLE_NORMAL,
    )
    ship_to = Paragraph(
        f"<b>SHIP TO: </b>{customer['name']}<br/>"
        f"Address: {customer['address']}<br/>"
        f"Pincode: {customer['pincode']}<br/>"
        f"State: {customer['state']}",
        STYLE_NORMAL,
    )
    invoice_header_table = Table(
        [
            [
                Paragraph(f"<b>Invoice No : {invoice_id}</b>", STYLE_NORMAL),
                Paragraph(f"<b>Invoice Date : {formatted_date}</b>", STYLE_NORMAL),
            ],
            [bill_to, ship_to],
        ],
        colWidths=_COL_INVOICE,
    )
    invoice_header_table.setStyle(_INVOICE_HEADER_STYLE)

    # ── Product table ────────────────────────────────────────────────────────
    product_table = Table(product_rows, colWidths=_COL_PRODUCT)
    product_table.setStyle(_PRODUCT_TABLE_STYLE)

    # ── Total table ──────────────────────────────────────────────────────────
    qty_label = f"{total_qty} PCS"
    grand_label = f"Rs {grand_total:.2f}"
    if paid_amount >= grand_total:
        total_rows = [
            ["", "GRAND TOTAL", qty_label, "", "", grand_label],
        ]
    else:
        remaining = grand_total - paid_amount
        total_rows = [
            ["", "GRAND TOTAL",      qty_label, "", "", grand_label],
            ["", "RECEIVED AMOUNT",  "",        "", "", f"Rs {paid_amount:.2f}"],
            ["", "REMAINING AMOUNT", "",        "", "", f"Rs {remaining:.2f}"],
        ]
    total_table = Table(total_rows, colWidths=_COL_PRODUCT)
    total_table.setStyle(_TOTAL_TABLE_STYLE)

    # ── Delivery mode table ──────────────────────────────────────────────────
    delivery_table = Table(
        [[
            "Delivery Mode",
            _capitalize_words(delivery_mode),
            "",
            "Salesman",
            _capitalize_words(customer["salesman"]),
        ]],
        colWidths=_COL_DELIVERY,
    )
    delivery_table.setStyle(_DELIVERY_TABLE_STYLE)

    # ── Transport info table (conditional) ───────────────────────────────────
    transport_table = None
    if delivery_mode == "transport":
        transport_table = Table(
            [
                ["Transport Name", "City", "Pincode"],
                [transport_name, transport_city, transport_pincode],
            ],
            colWidths=_COL_TRANSPORT,
        )
        transport_table.setStyle(_TRANSPORT_TABLE_STYLE)

    # ── GST summary table (conditional) ─────────────────────────────────────
    tax_table = None
    if include_gst:
        half_tax = total_tax_amount / 2
        taxable  = grand_total - total_tax_amount
        tax_table = Table(
            [
                ["HSN/SAC", "Taxable Value", "CGST Amount", "SGST Amount", "Total Tax Amount"],
                [
                    "95059090",
                    f"{taxable:.2f}",
                    f"{half_tax:.2f} (9%)",
                    f"{half_tax:.2f} (9%)",
                    f"Rs {total_tax_amount:.2f}",
                ],
            ],
            colWidths=_COL_TAX,
        )
        tax_table.setStyle(_TAX_TABLE_STYLE)

    # ── Amount in words ──────────────────────────────────────────────────────
    words_table = Table(
        [["Total Amount (in words):"], [_amount_in_words(grand_total)]],
        colWidths=_COL_WORDS,
    )
    words_table.setStyle(_WORDS_TABLE_STYLE)

    # ── Terms ────────────────────────────────────────────────────────────────
    terms_table = Table(
        [["Terms and Conditions"], [_TERMS_TEXT]],
        colWidths=_COL_WORDS,
    )
    terms_table.setStyle(_TERMS_TABLE_STYLE)

    # ── Assemble elements ────────────────────────────────────────────────────
    SP = Spacer(1, 10)
    elements = [
        Paragraph("SMART TRADERS", STYLE_TITLE),
        Paragraph("Ahmedabad, Gujarat, 382330, Ahmedabad, Gujarat, 382330", STYLE_SUBTITLE),
        Paragraph("GSTIN: 24DCFPS1329A1Z1 Mobile: 9316876474", STYLE_SUBTITLE),
        SP,
        invoice_header_table,
        SP,
        product_table,
        total_table,
        SP,
        delivery_table,
    ]
    if transport_table:
        elements += [SP, transport_table]
    elements.append(SP)
    if tax_table:
        elements += [tax_table, SP]
    elements += [
        words_table,
        SP,
        terms_table,
        SP,
        Paragraph("TAX INVOICE ORIGINAL FOR RECIPIENT", STYLE_FOOTER),
        Spacer(1, 45),
        Paragraph("Authorized Signature", STYLE_SIGNATURE),
    ]

    doc.title = customer["name"]
    doc.build(elements)
    buffer.seek(0)
    return buffer


# ─────────────────────────────────────────────────────────────────────────────
# Route handlers
# ─────────────────────────────────────────────────────────────────────────────

def _handle_invoice_pdf(invoice_number: str, as_attachment: bool):
    """Shared logic for download and share endpoints.
    Passes the raw invoice_number string (e.g. 'DC1630B510') straight to
    the stored procedure — no intermediate get_invoice_id() Python call.
    """
    try:
        header, products, charges = _fetch_invoice_data(invoice_number)
    except RuntimeError as exc:
        log.error("DB error for invoice %s: %s", invoice_number, exc)
        return jsonify({"error": "Database connection failed"}), 500

    if header is None:
        return jsonify({"error": "Invoice not found or not eligible"}), 404

    try:
        buffer = _build_pdf(header, products, charges)
    except Exception:
        log.exception("PDF build failed for invoice %s", invoice_number)
        return jsonify({"error": "Failed to generate PDF"}), 500

    customer_name = header.get("c_name", "invoice")
    invoice_id    = header.get("invoice_id", invoice_number)
    filename = f"{customer_name}_{invoice_id}.pdf"

    return send_file(
        buffer,
        as_attachment=as_attachment,
        download_name=filename,
        mimetype="application/pdf",
    )

