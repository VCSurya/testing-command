# sales.py
from __future__ import annotations
import json
import logging
from contextlib import contextmanager
from typing import Any

import mysql.connector

from db_pool import get_db_connection

logger = logging.getLogger(__name__)


@contextmanager
def managed_connection():
    """Context manager: auto-returns connection to pool on exit."""
    conn = get_db_connection()
    try:
        yield conn
    finally:
        try:
            conn.close()          # returns to pool, does NOT close the socket
        except Exception:
            pass


class Sales:
    """
    Stateless helper — no instance-level connection.
    Every method borrows a connection from the pool and returns it immediately.
    """

    # ------------------------------------------------------------------ #
    #  PUBLIC: single entry-point for the entire invoice-save workflow     #
    # ------------------------------------------------------------------ #

    def save_invoice(self, bill_data: dict[str, Any]) -> dict[str, Any]:
        """
        Calls the MySQL stored procedure that handles:
          • duplicate bill-number check
          • stock check (atomic, row-level)
          • invoice + items + charges insert
          • live_order_track insert
          • stock decrement
        Everything inside a single DB transaction — one round-trip.
        """
        products_json = json.dumps(bill_data["products"])
        charges_json  = json.dumps(bill_data["charges"])

        args = [
            int(bill_data["billno"]),
            int(bill_data["customer_id"]),
            bill_data["delivery_mode"],
            float(bill_data["grand_total"]),
            1 if bill_data.get("gst_included") == "on" else 0,
            int(bill_data["invoice_created_by_user_id"]),
            float(bill_data["paid_amount"]),
            bill_data["payment_mode"],
            bill_data.get("payment_note", ""),
            bill_data.get("sales_note", ""),
            bill_data.get("transport_id"),          # None → NULL
            bill_data.get("event_id"),              # None → NULL
            int(bill_data.get("completed", 0)),
            products_json,
            charges_json,
            0,   # OUT p_invoice_id
            "",  # OUT p_invoice_number
            "",  # OUT p_error
        ]

        try:
            with managed_connection() as conn:
                cursor = conn.cursor()
                cursor.callproc("save_invoice_atomic", args)

                # Read OUT params from the second result set
                out_params = {}
                for row in cursor.stored_results():
                    out_params = dict(zip(
                        ["p_invoice_id", "p_invoice_number", "p_error"],
                        row.fetchone() or []
                    ))

                # Fallback: query @-variables directly if stored_results() is empty
                if not out_params:
                    cursor.execute(
                        "SELECT @_save_invoice_atomic_15, "
                        "       @_save_invoice_atomic_16, "
                        "       @_save_invoice_atomic_17"
                    )
                    row = cursor.fetchone()
                    if row:
                        out_params = {
                            "p_invoice_id":     row[0],
                            "p_invoice_number": row[1],
                            "p_error":          row[2],
                        }

                cursor.close()

            invoice_id     = int(out_params.get("p_invoice_id", -1))
            invoice_number = out_params.get("p_invoice_number", "")
            error          = out_params.get("p_error", "")

            if error == "DUPLICATE_BILL":
                return {"success": False, "error": "Bill number already exists."}
            if error == "OUT_OF_STOCK":
                return {"success": False, "error": "Some products are out of stock."}
            if error or invoice_id == -1:
                return {"success": False, "error": error or "Unknown DB error"}

            return {
                "success":        True,
                "invoice_id":     invoice_id,
                "invoice_number": invoice_number,
            }

        except mysql.connector.Error as exc:
            logger.exception("save_invoice DB error")
            return {"success": False, "error": str(exc)}
        



# routes/sales_routes.py
from __future__ import annotations
import json
import logging

from flask import Blueprint, jsonify, request, session

from db_pool import get_db_connection
from sales import Sales, managed_connection

sales_bp = Blueprint("sales_bp", __name__)
logger   = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
#  Helpers                                                             #
# ------------------------------------------------------------------ #

def _parse_products(raw_products: list[dict], tax_rate: float) -> tuple[list, str | None]:
    """
    Validate + transform products from the request.
    Returns (product_rows, error_message_or_None).
    """
    rows: list = []
    for product in raw_products:
        qty_raw = product.get("quantity")
        try:
            qty = int(qty_raw)
            if qty <= 0:
                raise ValueError
        except (ValueError, TypeError):
            return [], "Invalid Quantity!"

        rate          = float(product["finalPrice"])
        original      = rate / (1 + tax_rate / 100)
        gst_amount    = round(rate - original, 2)
        total_amount  = float(product["total"])

        rows.append([
            int(product["id"]),
            qty,
            round(original, 2),
            gst_amount,
            round(total_amount, 0),
        ])
    return rows, None


def _lookup_customer(cursor, customer_id_raw: str) -> dict | None:
    cursor.execute(
        "SELECT id FROM buddy WHERE mobile = CAST(%s AS UNSIGNED) LIMIT 1",
        (customer_id_raw,)
    )
    return cursor.fetchone()


# ------------------------------------------------------------------ #
#  Route                                                               #
# ------------------------------------------------------------------ #

@sales_bp.route("/sales/save_invoice", methods=["POST"])
def save_invoice_into_database():
    """Save invoice — fast path via stored procedure (single DB round-trip)."""

    # ── 1. Parse & validate form ────────────────────────────────────────
    form = request.form

    billno       = form.get("billno")
    customer_raw = form.get("customerId", "")
    delivery     = form.get("delivery_mode", "")
    transport_id = form.get("transport_id") or None
    payment_mode = form.get("payment_mode", "")
    sales_note   = form.get("sales_note", "")
    payment_note = form.get("payment_note", "")
    gst_flag     = form.get("IncludeGST", "off")
    event_id     = form.get("event_id") or None

    try:
        grand_total  = float(form.get("grand_total", 0))
        paid_amount  = float(form.get("paid_amount", 0)) if payment_mode != "not_paid" else 0.0
    except ValueError:
        return jsonify({"success": False, "error": "Invalid amount values"}), 200

    if grand_total < 0:
        return jsonify({"success": False, "error": "Grand total cannot be negative"}), 200

    if not customer_raw:
        return jsonify({"success": False, "error": "Invalid mobile number"}), 200

    raw_products = form.get("products")
    raw_charges  = form.get("charges", "[]")

    if not raw_products:
        return jsonify({"success": False, "error": "No products in the bill"}), 200

    try:
        products_list = json.loads(raw_products)
        charges_list  = json.loads(raw_charges)
    except json.JSONDecodeError:
        return jsonify({"success": False, "error": "Malformed products/charges data"}), 200

    tax_rate = 18.0 if gst_flag == "on" else 0.0
    product_rows, err = _parse_products(products_list, tax_rate)
    if err:
        return jsonify({"success": False, "error": err}), 200

    # ── 2. Single lightweight pre-flight DB query ───────────────────────
    #       (customer lookup + optional transport update)
    #       Uses one pooled connection, returned immediately.
    try:
        with managed_connection() as conn:
            cursor = conn.cursor(dictionary=True)

            customer = _lookup_customer(cursor, customer_raw)
            if not customer:
                return jsonify({"success": False, "error": "Customer not found"}), 200

            if delivery == "transport":
                if not transport_id:
                    return jsonify({"success": False, "error": "Transport ID required"}), 200
                cursor.execute(
                    "UPDATE buddy SET transport_id = %s WHERE id = %s",
                    (transport_id, customer["id"])
                )
                conn.commit()
            else:
                transport_id = None

            cursor.close()

    except Exception as exc:
        logger.exception("Pre-flight DB error")
        return jsonify({"success": False, "error": "Database error"}), 200

    # ── 3. Delegate everything else to stored procedure ─────────────────
    bill_data = {
        "billno":                     billno,
        "customer_id":                customer["id"],
        "delivery_mode":              delivery,
        "grand_total":                grand_total,
        "paid_amount":                paid_amount,
        "payment_mode":               payment_mode,
        "payment_note":               payment_note,
        "sales_note":                 sales_note,
        "transport_id":               transport_id,
        "event_id":                   event_id,
        "gst_included":               gst_flag,
        "invoice_created_by_user_id": session.get("user_id"),
        "products":                   product_rows,
        "charges":                    charges_list,
        "completed":                  0,
    }

    result = Sales().save_invoice(bill_data)

    if result["success"]:
        return jsonify({
            "success":        True,
            "invoice_number": result["invoice_number"],
            "invoice_id":     result["invoice_id"],
        }), 200
    else:
        return jsonify({"success": False, "error": result["error"]}), 200
    



    # routes/sales_routes.py
from __future__ import annotations
import json
import logging

from flask import Blueprint, jsonify, request, session

from db_pool import get_db_connection
from sales import Sales, managed_connection

sales_bp = Blueprint("sales_bp", __name__)
logger   = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
#  Helpers                                                             #
# ------------------------------------------------------------------ #

def _parse_products(raw_products: list[dict], tax_rate: float) -> tuple[list, str | None]:
    """
    Validate + transform products from the request.
    Returns (product_rows, error_message_or_None).
    """
    rows: list = []
    for product in raw_products:
        qty_raw = product.get("quantity")
        try:
            qty = int(qty_raw)
            if qty <= 0:
                raise ValueError
        except (ValueError, TypeError):
            return [], "Invalid Quantity!"

        rate          = float(product["finalPrice"])
        original      = rate / (1 + tax_rate / 100)
        gst_amount    = round(rate - original, 2)
        total_amount  = float(product["total"])

        rows.append([
            int(product["id"]),
            qty,
            round(original, 2),
            gst_amount,
            round(total_amount, 0),
        ])
    return rows, None





# ------------------------------------------------------------------ #
#  Route                                                               #
# ------------------------------------------------------------------ #

@sales_bp.route("/sales/save_invoice", methods=["POST"])
def save_invoice_into_database():
    """Save invoice — fast path via stored procedure (single DB round-trip)."""

    # ── 1. Parse & validate form ────────────────────────────────────────
    form = request.form

    billno       = form.get("billno")
    customer_raw = form.get("customerId", "")
    delivery     = form.get("delivery_mode", "")
    transport_id = form.get("transport_id") or None
    payment_mode = form.get("payment_mode", "")
    sales_note   = form.get("sales_note", "")
    payment_note = form.get("payment_note", "")
    gst_flag     = form.get("IncludeGST", "off")
    event_id     = form.get("event_id") or None

    try:
        grand_total  = float(form.get("grand_total", 0))
        paid_amount  = float(form.get("paid_amount", 0)) if payment_mode != "not_paid" else 0.0
    except ValueError:
        return jsonify({"success": False, "error": "Invalid amount values"}), 200

    if grand_total < 0:
        return jsonify({"success": False, "error": "Grand total cannot be negative"}), 200

    if not customer_raw:
        return jsonify({"success": False, "error": "Invalid mobile number"}), 200

    raw_products = form.get("products")
    raw_charges  = form.get("charges", "[]")

    if not raw_products:
        return jsonify({"success": False, "error": "No products in the bill"}), 200

    try:
        products_list = json.loads(raw_products)
        charges_list  = json.loads(raw_charges)
    except json.JSONDecodeError:
        return jsonify({"success": False, "error": "Malformed products/charges data"}), 200

    tax_rate = 18.0 if gst_flag == "on" else 0.0
    product_rows, err = _parse_products(products_list, tax_rate)
    if err:
        return jsonify({"success": False, "error": err}), 200

    # ── 2. Single lightweight pre-flight DB query ───────────────────────
    #       (customer lookup + optional transport update)
    #       Uses one pooled connection, returned immediately.
    try:
        with managed_connection() as conn:
            cursor = conn.cursor(dictionary=True)

            customer = _lookup_customer(cursor, customer_raw)
            if not customer:
                return jsonify({"success": False, "error": "Customer not found"}), 200

            if delivery == "transport":
                if not transport_id:
                    return jsonify({"success": False, "error": "Transport ID required"}), 200
                cursor.execute(
                    "UPDATE buddy SET transport_id = %s WHERE id = %s",
                    (transport_id, customer["id"])
                )
                conn.commit()
            else:
                transport_id = None

            cursor.close()

    except Exception as exc:
        logger.exception("Pre-flight DB error")
        return jsonify({"success": False, "error": "Database error"}), 200

    # ── 3. Delegate everything else to stored procedure ─────────────────
    bill_data = {
        "billno":                     billno,
        "customer_id":                customer["id"],
        "delivery_mode":              delivery,
        "grand_total":                grand_total,
        "paid_amount":                paid_amount,
        "payment_mode":               payment_mode,
        "payment_note":               payment_note,
        "sales_note":                 sales_note,
        "transport_id":               transport_id,
        "event_id":                   event_id,
        "gst_included":               gst_flag,
        "invoice_created_by_user_id": session.get("user_id"),
        "products":                   product_rows,
        "charges":                    charges_list,
        "completed":                  0,
    }

    result = Sales().save_invoice(bill_data)

    if result["success"]:
        return jsonify({
            "success":        True,
            "invoice_number": result["invoice_number"],
            "invoice_id":     result["invoice_id"],
        }), 200
    else:
        return jsonify({"success": False, "error": result["error"]}), 200