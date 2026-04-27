from asyncio.log import logger
from flask import Blueprint, render_template, jsonify, request, session
from invoice import _handle_invoice_pdf
from utils import get_db_connection, login_required, get_invoice_id,cancel_order
import mysql.connector
from datetime import datetime
import pytz
import json

ist = pytz.timezone('Asia/Kolkata')
now_ist = datetime.now(ist)
formatted_time = now_ist.strftime("%d-%m-%Y %H:%M")


# Create a Blueprint for manager routes
sales_bp = Blueprint('sales', __name__)

# Sales Dashboard
@sales_bp.route('/sales/dashboard')
@login_required('Sales')
def sales_dashboard():
    return render_template('dashboards/sales/main.html')


@sales_bp.route('/sales/sell')
@login_required('Sales')
def sales():
    return render_template('dashboards/sales/sell.html')


@sales_bp.route('/sales/my-orders')
@login_required('Sales')
def sales_cancel_orders():
    return render_template('dashboards/sales/my_orders.html')


@sales_bp.route('/sales/cancel-orders')
@login_required('Sales')
def sales_my_orders():
    return render_template('dashboards/sales/cancel_orders.html')


@sales_bp.route('/sales/ready-to-go-orders')
@login_required('Sales')
def sales_ready_to_go_orders():
    return render_template('dashboards/sales/ready_to_go.html')

@sales_bp.route('/sales/dasebored-data', methods=['GET'])
@login_required('Sales')
def sales_summary():

    conn = get_db_connection()
    if not conn:
        return jsonify([]), 500 

    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute(f"CALL get_sales_dashboard({session.get('user_id')})")
        result = cursor.fetchone()
        return jsonify({"success":True,"data":result})

    except Exception as e:
        return jsonify({"success":False,"error": str(e)}), 500

    finally:
        cursor.close()
        conn.close()

    
def save_invoice(bill_data):

    products_json = json.dumps(bill_data["products"])
    charges_json  = json.dumps(bill_data["charges"])

    args = [
        int(bill_data["billno"]),                                    # 0
        int(bill_data["customer_id"]),                               # 1
        bill_data["delivery_mode"],                                  # 2
        float(bill_data["grand_total"]),                             # 3
        1 if bill_data.get("gst_included") == "on" else 0,          # 4
        int(bill_data["invoice_created_by_user_id"]),                # 5
        float(bill_data["paid_amount"]),                             # 6
        bill_data["payment_mode"],                                   # 7
        bill_data.get("payment_note", ""),                           # 8
        bill_data.get("sales_note", ""),                             # 9
        bill_data.get("transport_id"),                               # 10
        bill_data.get("event_id"),                                   # 11
        int(bill_data.get("completed", 0)),                          # 12
        products_json,                                               # 13
        charges_json,                                                # 14
        0,    # OUT p_invoice_id     → index 15
        "",   # OUT p_invoice_number → index 16
        "",   # OUT p_error          → index 17
    ]

    conn   = None
    cursor = None
    try:
        conn   = get_db_connection()
        cursor = conn.cursor()

        cursor.callproc("save_invoice_atomic", args)

        # Read the SELECT result set emitted by the SP at the end
        row = None
        for result in cursor.stored_results():
            row = result.fetchone()
            break  # only one result set expected

        print("DEBUG SP row:", row)

        if row is None:
            return {"success": False, "error": "No result set from stored procedure"}

        invoice_id, invoice_number, error = row

        invoice_id     = int(invoice_id)     if invoice_id     is not None else -1
        invoice_number = str(invoice_number) if invoice_number is not None else ""
        error          = str(error)          if error          is not None else ""

        # Map SP error codes → clean user messages
        if error == "DUPLICATE_BILL":
            return {"success": False, "error": "Bill number already exists. Please use a different bill number."}
        if "OUT_OF_STOCK" in error:
            return {"success": False, "error": "One or more products are out of stock. Please update your cart."}
        if "INSERT_INVOICE_ERR" in error:
            return {"success": False, "error": "Failed to save invoice. Please try again."}
        if "INSERT_ITEM_ERR" in error:
            return {"success": False, "error": "Failed to save invoice items. Please try again."}
        if "STOCK_UPDATE_ERR" in error:
            return {"success": False, "error": "Failed to update stock. Please try again."}
        if error:
            return {"success": False, "error": f"Database error: {error}"}
        if invoice_id == -1:
            return {"success": False, "error": "Unknown error occurred. Please try again."}

        return {
            "success":        True,
            "invoice_id":     invoice_id,
            "invoice_number": invoice_number,
        }

    except mysql.connector.Error as exc:
        print(f"DB error in save_invoice: {exc}")
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(exc)}

    finally:
        if cursor:
            try: cursor.close()
            except: pass
        if conn:
            try: conn.close()
            except: pass

@sales_bp.route('/sales/input-transport/<string:input>/<string:id_mode>', methods=['GET'])
@login_required('Sales')
def get_transport_input(input, id_mode):
    
    # Input validation
    if not input or len(input) > 100:
        return jsonify({'error': 'Invalid input'}), 400
    
    conn = get_db_connection()
    if not conn:
        return jsonify([]), 500 

    cursor = conn.cursor(dictionary=True)
    
    try:
        if id_mode == '1':
            # Parameterized query — prevents SQL injection
            cursor.execute(
                "SELECT id, pincode, name, city, days FROM transport WHERE id = %s LIMIT 1",
                (input,)
            )
            result = cursor.fetchone()
            return jsonify([result] if result else [])

        # Sanitize wildcard input for LIKE queries
        safe_input = input.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        pattern = f"{safe_input}%"

        if input.isdigit():
            cursor.execute(
                "SELECT id, pincode, name, city, days FROM transport "
                "WHERE pincode LIKE %s LIMIT 10",
                (pattern,)
            )
        else:
            # Use UNION instead of OR for better index utilization
            cursor.execute(
                "SELECT id, pincode, name, city, days FROM transport "
                "WHERE name LIKE %s "
                "UNION "
                "SELECT id, pincode, name, city, days FROM transport "
                "WHERE city LIKE %s "
                "LIMIT 10",
                (pattern, pattern)
            )

        return jsonify(cursor.fetchall())

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@sales_bp.route('/sales/all_events_details', methods=['GET'])
@login_required('Sales')
def all_market_events():
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'message': 'Database connection error'})

        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT 
                    id, 
                    name, 
                    location
                FROM market_events
                WHERE active = 1
                AND CURDATE() BETWEEN start_date AND end_date
                ORDER BY start_date ASC;
            """)
            events = cursor.fetchall()
        finally:
            cursor.close()
            conn.close()
        if len(events) == 0 or not events:
            return jsonify({'success': True, 'data': []})

        return jsonify({'success': True, 'data': events})

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@sales_bp.route('/sales/input-customers/<string:input_query>', methods=['GET'])
@login_required('Sales')
def get_customers_input(input_query):
    
    # Sanitize and validate input early
    input_query = input_query.strip()
    if not input_query or len(input_query) > 100:
        return jsonify([]), 400

    conn = get_db_connection()
    if not conn:
        return jsonify([]), 500

    cursor = conn.cursor(dictionary=True)
    try:
        # Use parameterized queries — eliminates SQL injection entirely
        if input_query.isdigit():
            cursor.execute(
                "SELECT id, name, address, state, pincode, mobile, transport_id "
                "FROM `buddy` "
                "WHERE mobile LIKE %s "
                "LIMIT 10",
                (f"{input_query}%",)   # prefix match — can use index on `mobile`
            )
        else:
            cursor.execute(
                "SELECT id, name, address, state, pincode, mobile, transport_id "
                "FROM `buddy` "
                "WHERE name LIKE %s "
                "LIMIT 10",
                (f"%{input_query}%",)  # infix match — consider FULLTEXT index for scale
            )

        customers = cursor.fetchall()
        return jsonify(customers), 200

    except Exception as e:
        print(f"Error fetching customers: {e}")
        return jsonify({'error': 'Failed to fetch customers'}), 500

    finally:
        cursor.close()
        conn.close()

@sales_bp.route('/sales/add-customer', methods=['POST'])
@login_required('Sales')
def add_new_customer():
    conn = None
    cursor = None
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Invalid JSON payload'}), 400

        # --- Validation (single pass) ---
        required_fields = ['name', 'address', 'state', 'pincode', 'mobile']
        name     = data.get('name', '').strip()
        address  = data.get('address', '').strip()
        state    = data.get('state', '').strip()
        pincode  = data.get('pincode', '').strip()
        mobile   = data.get('mobile', '').strip()
        city     = data.get('city', '').strip()
        company  = data.get('company', '').strip()
        transport_id = data.get('transportCompany') or None

        if not all([name, address, state, pincode, mobile]):
            return jsonify({'success': False, 'error': 'Please fill in all required fields.'}), 400

        if not mobile.isdigit() or len(mobile) != 10:
            return jsonify({'success': False, 'error': 'Enter a valid 10-digit mobile number.'}), 400

        if not pincode.isdigit() or len(pincode) != 6:
            return jsonify({'success': False, 'error': 'Enter a valid 6-digit pincode.'}), 400

        # --- DB connection ---
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Database connection failed'}), 500

        cursor = conn.cursor(dictionary=True)

        # Check duplicate mobile
        cursor.execute("SELECT id FROM buddy WHERE mobile = %s LIMIT 1", (mobile,))
        if cursor.fetchone():
            return jsonify({'success': False, 'error': f'{mobile}: Customer already exists'}), 409

        # Validate transport if provided
        if transport_id:
            cursor.execute("SELECT id FROM transport WHERE id = %s AND active = 1 LIMIT 1", (transport_id,))
            if not cursor.fetchone():
                return jsonify({'success': False, 'error': 'Selected transport company does not exist'}), 400

        # Insert
        cursor.execute(
            """
            INSERT INTO buddy
                (name, address, state, pincode, mobile, city, company, transport_id, created_by)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (name, address, state, pincode, mobile, city, company, transport_id, session.get('user_id'))
        )
        conn.commit()

        # Return the data we already have — no extra SELECT needed
        return jsonify({
            'success': True,
            'data': {
                'id':      cursor.lastrowid,
                'name':    name,
                'address': address,
                'pincode': pincode,
                'mobile':  mobile,
            }
        }), 201

    except Exception as e:
        if conn:
            conn.rollback()
        import traceback; traceback.print_exc()
        return jsonify({'success': False, 'error': 'Internal server error'}), 500

    finally:
        if cursor: cursor.close()
        if conn:   conn.close()

        
@sales_bp.route('/sales/input-products/<string:input>', methods=['GET'])
@login_required('Sales')
def get_products_input(input):
    conn = None
    cursor = None
    try:
        # Sanitize and validate input early
        search = input.strip()
        if not search:
            return jsonify([]), 200
        if len(search) > 100:
            return jsonify({'error': 'Search term too long'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify([]), 500

        cursor = conn.cursor(dictionary=True)

        # Parameterized query — never interpolate user input into SQL
        cursor.execute(
            """
            SELECT id, name, selling_price AS price, quantity
            FROM products
            WHERE name LIKE %s
              AND active = 1
            ORDER BY name ASC
            LIMIT 10
            """,
            (f'%{search}%',)   # <-- wildcard added in Python, not in SQL string
        )

        products = cursor.fetchall()
        return jsonify(products), 200

    except Exception as e:
        print(f"Error fetching products: {e}")
        return jsonify({'error': 'Failed to fetch products'}), 500

    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


def _parse_products(raw_products: list[dict], tax_rate: float) -> tuple[list, str | None]:
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
        "SELECT id FROM buddy WHERE id = %s LIMIT 1",
        (customer_id_raw,)
    )
    return cursor.fetchone()

@sales_bp.route('/sales/save_invoice', methods=['POST'])
def save_invoice_into_database():

    # ── 1. Parse & validate form ────────────────────────────────────────
    form = request.form

    billno       = form.get("billno")
    customer_raw = form.get("customer_id", "")
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
        with get_db_connection() as conn:
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
        return jsonify({"success": False, "error": print(exc)}), 200

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

    result = save_invoice(bill_data)

    if result["success"]:
        return jsonify({
            "success":        True,
            "invoice_number": result["invoice_number"],
            "invoice_id":     result["invoice_id"],
        }), 200
    else:
        return jsonify({"success": False, "error": result["error"]}), 200

@sales_bp.route("/sales/download_invoice_pdf/<string:invoice_number>", methods=["GET"])
def download_invoice_pdf(invoice_number: str):
    """Stream PDF inline (view in browser)."""
    return _handle_invoice_pdf(invoice_number, as_attachment=False)


@sales_bp.route("/sales/share_invoice_pdf/<string:invoice_number>", methods=["POST"])
def share_invoice_pdf(invoice_number: str):
    """Return PDF as a downloadable attachment."""
    return _handle_invoice_pdf(invoice_number, as_attachment=True)


# -------------------- My Orders --------------------------

class MyOrders:
    def __init__(self):
        self.conn = get_db_connection()
        if not self.conn:
            raise Exception("Database connection failed")
        self.cursor = self.conn.cursor(dictionary=True)

    def get_additional_charges(self,invoice_id):
        
        query = '''
            SELECT charge_name,amount FROM `additional_charges` WHERE invoice_id = %s;
        '''

        self.cursor.execute(query, (invoice_id,))
        additional_charges = self.cursor.fetchall()

        if not additional_charges:
            return []

        return additional_charges

    def merge_orders_products(self, data):

        merged = {}

        for item in data:

            # change created_at date formate
            item['created_at'] = item['created_at'].strftime(
                "%d/%m/%Y %I:%M %p")
            
            # passed tracking status with date
            trackingStatus = 0
            trackingDates = []
            if item['sales_proceed_for_packing']:

                if item['sales_date_time']:
                    trackingDates.append(
                        item['sales_date_time'].strftime("%d/%m/%Y %I:%M %p"))
                else:
                    trackingDates.append('')
                trackingStatus = 1

                if item['payment_confirm_status']:

                    if item['payment_date_time']:
                        trackingDates.append(
                            item['payment_date_time'].strftime("%d/%m/%Y %I:%M %p"))
                    else:
                        trackingDates.append('')
                    trackingStatus = 2

                    if item['packing_proceed_for_transport']:

                        if item['packing_proceed_for_transport']:
                            trackingDates.append(
                                item['packing_date_time'].strftime("%d/%m/%Y %I:%M %p"))
                        else:
                            trackingDates.append('')
                        trackingStatus = 3

                        if item['transport_proceed_for_builty']:

                            if item['transport_proceed_for_builty']:
                                trackingDates.append(
                                    item['transport_date_time'].strftime("%d/%m/%Y %I:%M %p"))
                            else:
                                trackingDates.append('')
                            trackingStatus = 4

                            if item['builty_received']:

                                if item['builty_received']:
                                    trackingDates.append(
                                        item['builty_date_time'].strftime("%d/%m/%Y %I:%M %p"))
                                else:
                                    trackingDates.append('')
                                trackingStatus = 5

                                if item['verify_by_manager']:

                                    if item['verify_by_manager']:
                                        trackingDates.append(
                                            item['verify_manager_date_time'].strftime("%d/%m/%Y %I:%M %p"))
                                    else:
                                        trackingDates.append('')
                                    trackingStatus = 6

            item['trackingStatus'] = trackingStatus
            item['trackingDates'] = trackingDates


            # merge products
            order_id = item["id"]
            product_info = {
                "name": item["name"],
                "qty": item["quantity"],
                "price": float(item["price"]),
                "tax_amount": float(item["gst_tax_amount"]),
                "total": float(item["total_amount"]),
                "stock": int(item["stock"]),
            }

            if order_id not in merged:
                # Create a new entry if the id doesn't exist yet
                merged[order_id] = {
                    **{k: v for k, v in item.items() if k not in ["name", "quantity", "price", "gst_tax_amount", "total_amount", "invoices_items_id", "product_id", "products_id"]},
                    "products": [product_info],
                }
            else:
                # If it already exists, just append the product info
                merged[order_id]["products"].append(product_info)

        return list(merged.values())

    def fetch_my_orders(self, user_id):
        query = """

            SELECT 
                inv.id,
                inv.invoice_number,
                DATE_FORMAT(CONVERT_TZ(inv.created_at,'+00:00','+05:30'),'%d/%m/%Y %h:%i %p') AS created_at,

                CASE
                    WHEN lot.verify_by_manager = 1 THEN 6
                    WHEN lot.builty_received = 1 THEN 5
                    WHEN lot.transport_proceed_for_builty = 1 THEN 4
                    WHEN lot.packing_proceed_for_transport = 1 THEN 3
                    WHEN lot.payment_confirm_status = 1 THEN 2
                    WHEN lot.sales_proceed_for_packing = 1 THEN 1
                    ELSE 0
                END AS trackingStatus

            FROM invoices inv
            LEFT JOIN live_order_track lot ON inv.id = lot.invoice_id

            WHERE inv.invoice_created_by_user_id = %s
            AND lot.cancel_order_status = 0
            AND lot.sales_proceed_for_packing = 1
            AND inv.completed = 0
            ORDER BY inv.created_at DESC;

        """

        self.cursor.execute(query, (user_id,))
        all_order_data = self.cursor.fetchall()

        if not all_order_data:
            return []

        return all_order_data

    def fetch_ready_to_go_orders(self):
        query = f"""
            SELECT 

                inv.id,
                inv.invoice_number,
                DATE_FORMAT(inv.created_at, '%d/%m/%Y %h:%i %p') AS date_time

            FROM invoices inv
            LEFT JOIN live_order_track lot ON inv.id = lot.invoice_id
            
            WHERE inv.invoice_created_by_user_id = %s
            AND lot.cancel_order_status = 0
            AND lot.sales_proceed_for_packing = 0
            AND inv.completed = 0   
            ORDER BY inv.created_at DESC; 
 
        """

        self.cursor.execute(query, (session.get('user_id'),))
        all_order_data = self.cursor.fetchall()

        if not all_order_data:
            return []

        return all_order_data
    
    def delete_invoice(self, invoice_id):
        try:
            query = """
                DELETE FROM invoices
                WHERE id = %s and invoice_created_by_user_id = %s;
            """
            self.cursor.execute(query, (invoice_id, session.get('user_id')))
            self.conn.commit()  # commit on connection, not cursor
            if self.cursor.rowcount == 0:
                return {"success": False, "message": f"No invoice found with ID"}
            else:
                return {"success": True, "message": f"Invoice successfully deleted"}
        except Exception as e:
            self.conn.rollback()  # rollback on connection, not cursor
            return {"success": False, "message": f"Error deleting invoice {invoice_id}: {e}"}
                
    def start_shipment(self, invoiceNumber):
        try:
            user_id = session.get('user_id')

            # Pass @out variables as placeholders for OUT params
            self.cursor.execute(
                "CALL sp_start_shipment(%s, %s, @p_success, @p_message)",
                (invoiceNumber, user_id)
            )
            
            # Consume any result sets before reading OUT params
            while self.cursor.nextset():
                pass

            self.cursor.execute("SELECT @p_success AS success, @p_message AS message")
            result = self.cursor.fetchone()

            success = bool(result['success'])
            message = result['message']

            if success:
                self.conn.commit()
            else:
                self.conn.rollback()

            return {"success": success, "message": message}

        except Exception as e:
            self.conn.rollback()
            print(f"Error while shipping order: {e}")
            return {"success": False, "message": f"Something went wrong: {str(e)}"}
    
    def close(self):
        self.cursor.close()
        self.conn.close()


@sales_bp.route('/sales/cancel_order', methods=['POST'])
@login_required('Sales')
def sales_cancel_order():
    try:
        data = request.get_json()
        invoiceNumber = data.get('invoiceNumber')

        if not invoiceNumber:
            return jsonify({"success": False, "message": "Invalid Invoice Number"}), 400

        response = cancel_order(
            invoiceNumber, data.get('reason')
        )

        if response.get('success') == 1:
            return jsonify({"success": True, "message": "Order Cancelled Successfully"}), 200

        return {"success": False, "message": response.get('message')}, 500

    except Exception as e:
        return jsonify({"success": False, "message": "Internal server error"}), 500


@sales_bp.route('/sales/delete_invoice/<string:invoice_number>', methods=['DELETE'])
@login_required('Sales')
def delete_invoice(invoice_number):
    try:
        
        result = get_invoice_id(invoice_number)
        invoice_id = None
        if result['status']:
            invoice_id = result['invoice_id']
        else:
            return jsonify({'error': 'Invoice not found'}), 404


        # Get invoice data from database
        conn = get_db_connection()
        if not conn:
            return jsonify({"success": False, "message": 'Database connection failed'}), 500

        cursor = conn.cursor(dictionary=True)

        # Check invoice_number and invoice_id details
        cursor.execute("""
            SELECT invoice_number
            FROM invoices
            WHERE id = %s;
        """, (invoice_id,))
        invoice_data = cursor.fetchone()

        if invoice_data['invoice_number'] != invoice_number:
            return jsonify({"success": False, "message": "Sorry, there was an issue. We are looking into it."}), 404

        for_delete_invoice = MyOrders()
        response = for_delete_invoice.delete_invoice(invoice_id)

        if response['success']:
            return jsonify({"success": True, "message": 'Invoice successfully deleted!'}), 200

        return jsonify({"success": False, "message": "Something Went Wrong"}), 500

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@sales_bp.route('/sales/my-orders-list', methods=['GET'])
def sales_my_orders_list():
    """
    Fetch the list of orders for the logged-in sales user.
    """
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = conn.cursor(dictionary=True)
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not logged in'}), 401
        my_orders = MyOrders()
        orders = my_orders.fetch_my_orders(user_id)
        my_orders.close()
        if not orders:
            return jsonify([]), 200

        return jsonify(orders)

    except Exception as e:
        print(f"Error fetching orders: {e}")
        return jsonify({'error': 'Failed to fetch orders'}), 500

    finally:
        cursor.close()
        conn.close()


@sales_bp.route('/sales/invoice-details/<invoiceNumber>', methods=['GET'])
@login_required(['Sales'])
def sales_invoice_details(invoiceNumber):
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = conn.cursor(dictionary=True)
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not logged in'}), 401
        
        cursor.callproc('get_sales_invoice_details', (invoiceNumber,))
            
        result = None
        for res in cursor.stored_results():
            result = res.fetchone()

        if not result:
            return None

        for field in ["products", "charges"]:
            if result.get(field):
                try:
                    result[field] = json.loads(result[field])
                except Exception:
                    result[field] = []
            else:
                result[field] = []

        return result

    except Exception as e:
        return jsonify({'error': str(e)}), 500

    finally:
        cursor.close()
        conn.close()


@sales_bp.route('/start-shipment', methods=['POST'])
@login_required('Sales')
def start_shipment():

    try:
        data = request.get_json()
        invoiceNumber = data.get('invoiceNumber')

        if not invoiceNumber:
            return jsonify({'error': 'Missing Invoice Number'}), 400

        shipment_start = MyOrders()
        response = shipment_start.start_shipment(invoiceNumber)

        if response['success']:
            return jsonify({"success": True, "message": 'Order Successfully Shipped!'}), 200

        return jsonify(response), 500

    except Exception as e:
        return jsonify({'success': False, 'message': f'Shipment Failed: {str(e)}'}), 500


@sales_bp.route('/sales/my-ready-to-go-orders-list', methods=['GET'])
@login_required('Sales')
def sales_my_ready_to_go_orders_list():

    try:
        
        my_orders = MyOrders()
        
        orders = my_orders.fetch_ready_to_go_orders()
        
        my_orders.close()

        if not orders:
            return jsonify([]), 200

        return jsonify(orders)

    except Exception as e:
        return jsonify({'error': 'Failed to fetch orders','msg': str(e)}), 500


@sales_bp.route('/sales/ready-to-go-invoice-details/<invoiceNumber>', methods=['GET'])
@login_required('Sales')
def sales_draft_invoice_details(invoiceNumber):
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = conn.cursor(dictionary=True)
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not logged in'}), 401
        
        cursor.callproc('get_sales_draft_invoice_details', (invoiceNumber,))
            
        result = None
        for res in cursor.stored_results():
            result = res.fetchone()

        if not result:
            return None

        for field in ["products", "charges"]:
            if result.get(field):
                try:
                    result[field] = json.loads(result[field])
                except Exception:
                    result[field] = []
            else:
                result[field] = []

        return result

    except Exception as e:
        return jsonify({'error': str(e)}), 500

    finally:
        cursor.close()
        conn.close()




# -------------- Canceled Orders ---------------

class Canceled_Orders:

    def __init__(self):
        self.conn = get_db_connection()
        if not self.conn:
            raise Exception("Database connection failed")
        self.cursor = self.conn.cursor(dictionary=True)

    def merge_orders_products(self, data):

        merged = {}

        for item in data:

            # change created_at date formate
            item['created_at'] = item['created_at'].strftime(
                "%d/%m/%Y %I:%M %p")

            # passed tracking status with date
            trackingStatus = 0
            trackingDates = []

            if item['sales_proceed_for_packing']:

                if item['sales_date_time']:
                    trackingDates.append(
                        item['sales_date_time'].strftime("%d/%m/%Y %I:%M %p"))
                else:
                    trackingDates.append('')
                trackingStatus = 1

                if item['payment_confirm_status']:

                    if item['payment_date_time']:
                        trackingDates.append(
                            item['payment_date_time'].strftime("%d/%m/%Y %I:%M %p"))
                    else:
                        trackingDates.append('')
                    trackingStatus = 2

                    if item['packing_proceed_for_transport']:

                        if item['packing_proceed_for_transport']:
                            trackingDates.append(
                                item['packing_date_time'].strftime("%d/%m/%Y %I:%M %p"))
                        else:
                            trackingDates.append('')
                        trackingStatus = 3

                        if item['transport_proceed_for_builty']:

                            if item['transport_proceed_for_builty']:
                                trackingDates.append(
                                    item['transport_date_time'].strftime("%d/%m/%Y %I:%M %p"))
                            else:
                                trackingDates.append('')
                            trackingStatus = 4

                            if item['builty_received']:

                                if item['builty_received']:
                                    trackingDates.append(
                                        item['builty_date_time'].strftime("%d/%m/%Y %I:%M %p"))
                                else:
                                    trackingDates.append('')
                                trackingStatus = 5

                                if item['verify_by_manager']:

                                    if item['verify_by_manager']:
                                        trackingDates.append(
                                            item['verify_manager_date_time'].strftime("%d/%m/%Y %I:%M %p"))
                                    else:
                                        trackingDates.append('')
                                    trackingStatus = 6

            item['trackingStatus'] = trackingStatus
            item['trackingDates'] = trackingDates
            item['cancelled_at'] = item['cancelled_at'].strftime(
                "%d/%m/%Y %I:%M %p")

            # merge products
            order_id = item["id"]
            product_info = {
                "name": item["name"],
                "qty": item["quantity"],
                "price": float(item["price"]),
                "tax_amount": float(item["gst_tax_amount"]),
                "total": float(item["total_amount"]),
            }

            if order_id not in merged:
                # Create a new entry if the id doesn't exist yet
                merged[order_id] = {
                    **{k: v for k, v in item.items() if k not in ["name", "quantity", "price", "gst_tax_amount", "total_amount", "invoices_items_id", "product_id", "products_id"]},
                    "products": [product_info],
                }
            else:
                # If it already exists, just append the product info
                merged[order_id]["products"].append(product_info)

        return list(merged.values())

    def find_all_canceled_orders(self, user_id):
        query = """
            SELECT 

                inv.id,
                inv.invoice_number,
                DATE_FORMAT(lot.sales_date_time, '%d/%m/%Y %h:%i %p') AS sales_date_time

                
            FROM invoices inv
            LEFT JOIN live_order_track lot ON inv.id = lot.invoice_id
            LEFT JOIN cancelled_orders c ON inv.id = c.invoice_id
            WHERE inv.invoice_created_by_user_id = %s
            AND c.confirm_by_saler = 0
            AND lot.cancel_order_status = 1
            AND (
                lot.sales_proceed_for_packing = 0 
                OR lot.packing_proceed_for_transport = 0 
                OR lot.transport_proceed_for_builty = 0 
                OR lot.builty_received = 0 
                OR lot.payment_confirm_status = 0 
                OR lot.verify_by_manager = 0
            )
            ORDER BY c.cancelled_at DESC

        """
        self.cursor.execute(query, (user_id,))
        all_order_data = self.cursor.fetchall()

        if not all_order_data:
            return []

        return all_order_data

    def find_all_canceled_order_details(self, invoiceNumber):
        query = """
            SELECT 
                -- invoices columns as is
                inv.id,
                inv.invoice_number,
                inv.customer_id,
                inv.grand_total,
                inv.payment_mode,
                inv.paid_amount,
                inv.left_to_paid,
                inv.transport_id,
                inv.sales_note,
                inv.invoice_created_by_user_id,
                inv.payment_note,
                inv.gst_included,
                inv.created_at,
                inv.delivery_mode,
                
                -- buddy columns (all except id) + renamed id column
                b.id AS buddy_id, -- since customer_id is primary key here
                b.name AS customer,
                b.address,
                b.state,
                b.pincode,
                b.mobile,
                -- add other buddy columns here
                
                -- users columns, only rename id column
                u.id AS users_id,
                u.username,
                u.role,
                -- add other user columns
                
                -- invoices_items columns, rename id only
                ii.id AS invoices_items_id,
                ii.product_id,
                ii.quantity,
                ii.price,
                ii.gst_tax_amount,
                ii.total_amount,
                ii.created_at,
                
                -- add other invoices_items columns
                
                -- products columns, rename id only
                p.id AS products_id,
                p.name,
                -- add other products columns
                
                -- live_order_track columns, rename id only
                lot.id AS live_order_track_id,
                lot.sales_proceed_for_packing,
                lot.sales_date_time,
                lot.packing_proceed_for_transport,
                lot.packing_date_time,
                lot.packing_proceed_by,
                lot.transport_proceed_for_builty,
                lot.transport_date_time,
                lot.transport_proceed_by,
                lot.transport_date_time,
                lot.transport_proceed_by,
                lot.builty_proceed_by,
                lot.builty_received,
                lot.builty_date_time,
                lot.payment_confirm_status,
                lot.cancel_order_status,
                lot.verify_by_manager,
                lot.verify_by_manager_id,
                lot.verify_manager_date_time,
                lot.payment_date_time,

                -- cancelled_orders columns
                c.id AS cancelled_orders_id,
                c.cancelled_at,
                c.reason AS cancelled_reason,
                c.confirm_at,

                -- transport_orders columns
                t.pincode AS transport_pincode,
                t.name AS transport_name,
                t.city AS transport_city,
                t.days AS transport_days
                
            FROM invoices inv
            LEFT JOIN buddy b ON inv.customer_id = b.id
            LEFT JOIN invoice_items ii ON inv.id = ii.invoice_id
            LEFT JOIN products p ON ii.product_id = p.id
            LEFT JOIN live_order_track lot ON inv.id = lot.invoice_id
            LEFT JOIN cancelled_orders c ON inv.id = c.invoice_id
            LEFT JOIN users u ON c.cancelled_by = u.id
            LEFT JOIN transport t ON inv.transport_id = t.id
            WHERE inv.invoice_number = %s
            AND c.confirm_by_saler = 0
            AND lot.cancel_order_status = 1
            AND (
                lot.sales_proceed_for_packing = 0 
                OR lot.packing_proceed_for_transport = 0 
                OR lot.transport_proceed_for_builty = 0 
                OR lot.builty_received = 0 
                OR lot.payment_confirm_status = 0 
                OR lot.verify_by_manager = 0
            )
            ORDER BY c.cancelled_at DESC

        """
        self.cursor.execute(query, (invoiceNumber,))
        all_order_data = self.cursor.fetchall()

        if not all_order_data:
            return []

        # Merge products into orders
        merged_orders = self.merge_orders_products(all_order_data)
        
        for invoice_id in merged_orders:
            obj = MyOrders()
            charges = obj.get_additional_charges(invoice_id['id']) 
            invoice_id['charges'] = charges

        return merged_orders[0]


    def confirm_canceled_order(self, id):

        try:

            # update stocks
            fetch_products = "SELECT product_id,quantity FROM `invoice_items` WHERE invoice_id = (SELECT invoice_id from cancelled_orders WHERE id = %s);" 
            self.cursor.execute(fetch_products, (id,))
            products = self.cursor.fetchall()

            for product in products:
                query = """
                    UPDATE products
                    SET quantity = quantity + %s
                    WHERE id = %s
                """
                values = (
                    product['quantity'],
                    product['product_id']
                )

                self.cursor.execute(query, values)

            query = """
                    UPDATE cancelled_orders
                    SET confirm_by_saler = 1,confirm_at = NOW()
                    WHERE id = %s;
            """
            self.cursor.execute(query, (id,))

            self.conn.commit()
            return {"success": True}

        except Exception as e:
            self.conn.rollback()
            return {"success": False, "message": f"Something went wrong while shipping order: {str(e)}"}

    def reject_canceled_order(self, id):

        update_query = """
                UPDATE live_order_track
                SET cancel_order_status = 0
                WHERE id IN (
                    SELECT live_order_track_id FROM cancelled_orders WHERE cancelled_orders.id = %s
                );
        """

        update_query_ = """
            UPDATE invoices
            SET cancel_order_status = 0
            WHERE invoices.id = (SELECT invoice_id from cancelled_orders WHERE cancelled_orders.id = %s );
        """
            

        delete_query = """
                DELETE FROM cancelled_orders WHERE id = %s;
        """

        try:
            self.cursor.execute(update_query, (id,))
            self.cursor.execute(update_query_, (id,))
            self.cursor.execute(delete_query, (id,))
            self.conn.commit()
            return {"success": True}

        except Exception as e:
            self.conn.rollback()
            return {"success": False, "message": f"Something went wrong while shipping order: {str(e)}"}

    def close(self):
        self.cursor.close()
        self.conn.close()


@sales_bp.route('/sales/canceld-orders-list', methods=['GET'])
def sales_cancled_orders_list():
    """
    Fetch the list of canceled orders for the logged-in sales user.
    """

    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not logged in'}), 401
        my_orders = Canceled_Orders()
        orders = my_orders.find_all_canceled_orders(user_id)
        my_orders.close()

        if not orders:
            return jsonify([]), 200

        return jsonify(orders)

    except Exception as e:
        print(f"Error fetching orders: {e}")
        return jsonify({'error': 'Failed to fetch orders'}), 500

    finally:
        my_orders.close()

@sales_bp.route('/sales/canceld-orders-details/<invoiceNumber>', methods=['GET'])
@login_required('Sales')
def sales_cancled_order_details(invoiceNumber):

    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not logged in'}), 401
        my_orders = Canceled_Orders()
        orders = my_orders.find_all_canceled_order_details(invoiceNumber)
        my_orders.close()

        if not orders:
            return jsonify([]), 200

        return jsonify(orders)

    except Exception as e:
        print(f"Error fetching orders: {e}")
        return jsonify({'error': 'Failed to fetch orders'}), 500

    finally:
        my_orders.close()


@sales_bp.route('/sales/canceled-orders-status', methods=['PUT'])
@login_required('Sales')
def update_canceled_orders_status():

    try:

        data = request.get_json()
        id = data.get('invoiceNumber')
        cancel_order_status = data.get('deleteStatus')
        my_obj = Canceled_Orders()

        if cancel_order_status == 1 and id:

            response = my_obj.confirm_canceled_order(id)

            if response['success']:
                my_obj.close()
                return jsonify({'success': True, 'message': 'Done!'}), 200

            else:
                return jsonify({
                    'success': False,
                    'message': f"Something went wrong! {response.get('message', 'Unknown error')}"
                }), 500

        if cancel_order_status == 0 and id:

            response = my_obj.reject_canceled_order(id)

            if response['success']:
                my_obj.close()
                return jsonify({'success': True, 'message': 'Done!'}), 200
            else:
                return jsonify({'success': False, 'message': f'Somthing went wrong!{response["message"]}'}), 500

        return jsonify({'success': False, 'message': f'Somthing went wrong!'}), 500

    except Exception as e:
        print(f"Error fetching orders: {e}")
        return jsonify({'success': False, 'message': f'Somthing went wrong! {e}'}), 500


sales_bp.add_url_rule('/sales/', view_func=sales_dashboard)


# -------------------------------------------------------------------- Edit The Bill --------------------------------------------------------------------------------------------

class EditBill:

    def __init__(self):
        self.conn = get_db_connection()
        if not self.conn:
            raise Exception("Database connection failed")
        self.cursor = self.conn.cursor(dictionary=True)

    def insert_live_order_track(self, invoice_id):
        
        try:
            # Prepare the SQL query to insert the invoice data
            insert_query = """
                INSERT INTO live_order_track (invoice_id)
                VALUES (%s)
            """

            # Extract values from the invoice_data dictionary
            values = (
                invoice_id,
            )

            # Execute the query
            cursor = self.conn.cursor()
            cursor.execute(insert_query, values)
            self.conn.commit()

            return {'success': True}

        except mysql.connector.Error as e:
            self.conn.rollback()
            return {'error': str(e)}

        finally:
            cursor.close()


    def update_invoice_detail(self, invoice_data):
        if not self.conn:
            return {"status": False, "error": "Database connection is not available."}

        try:
            cursor = self.conn.cursor()

            # Prepare invoice data
            gst_included = 1 if invoice_data.get('gst_included') == 'on' else 0
            left_to_paid = invoice_data['grand_total'] - invoice_data['paid_amount']
            invoice_id = invoice_data['invoice_id']

            # Step 1: Update invoice record
            update_invoice_query = """
                UPDATE invoices
                SET customer_id = %s,
                    delivery_mode = %s,
                    grand_total = %s,
                    gst_included = %s,
                    invoice_created_by_user_id = %s,
                    left_to_paid = %s,
                    paid_amount = %s,
                    payment_mode = %s,
                    payment_note = %s,
                    sales_note = %s,
                    transport_id = %s,
                    event_id = %s,
                    completed = %s,
                    created_at = NOW()
                WHERE id = %s
            """
            invoice_values = (
                int(invoice_data['customer_id']),
                invoice_data['delivery_mode'],
                float(invoice_data['grand_total']),
                gst_included,
                int(invoice_data['invoice_created_by_user_id']),
                left_to_paid,
                float(invoice_data['paid_amount']),
                invoice_data['payment_mode'],
                invoice_data['payment_note'],
                invoice_data['sales_note'],
                invoice_data['transport_id'] if invoice_data['transport_id'] else None,
                invoice_data['event_id'] if invoice_data.get('event_id') else None,
                invoice_data.get('completed', 0),
                invoice_id
            )

            cursor.execute(update_invoice_query, invoice_values)

            # Step 2: Fetch & delete old invoice items and charges
            cursor.execute("SELECT id FROM invoice_items WHERE invoice_id = %s;", (invoice_id,))
            all_old_items_ids = cursor.fetchall()

            cursor.execute("SELECT id FROM additional_charges WHERE invoice_id = %s;", (invoice_id,))
            all_old_charges_ids = cursor.fetchall()

            if invoice_data['delivery_mode'] == "porter" or invoice_data['delivery_mode'] == "at_store":
                cursor.execute("DELETE FROM live_order_track WHERE invoice_id = %s;", (invoice_id,))
                result = self.insert_live_order_track(invoice_id)
                if result['success'] != True:
                    self.conn.rollback()
                    return {"status": False, 'error': result['error']}
            
            # Step 3: Insert new invoice items
            insert_item_query = """
                INSERT INTO invoice_items (
                    invoice_id, product_id, quantity, price, total_amount,
                    gst_tax_amount, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """

            for product in invoice_data.get('products', []):
                product_id = int(product[0])
                quantity = int(product[1])
                price = float(product[2])
                gst_tax_amount = float(product[3])
                total_amount = float(product[4])

                cursor.execute(insert_item_query, (
                    invoice_id, product_id, quantity, price, total_amount, gst_tax_amount
                ))

            # Step 4: Insert charges
            insert_charges_query = """
                INSERT INTO additional_charges (
                    invoice_id, charge_name, amount, created_at
                ) VALUES (%s, %s, %s, NOW())
            """

            for charge in invoice_data['charges']:
               
                charge_name = charge['name']
                charge_amount = int(charge['amount'])
                
                item_values = (
                    invoice_id,
                    charge_name,
                    charge_amount
                )

                cursor.execute(insert_charges_query, item_values)

            # Step 5: Final commit
            for (item_id,) in all_old_items_ids:
                cursor.execute("DELETE FROM invoice_items WHERE id = %s;", (item_id,))
            
            for (charges_id,) in all_old_charges_ids:
                cursor.execute("DELETE FROM additional_charges WHERE id = %s;", (charges_id,))

            self.conn.commit()
            return {"status": True, 'msg': "All Things Are Done!"}
        

        except mysql.connector.Error as e:
            self.conn.rollback()
            return {"status": False, 'error': str(e)}

    def close(self):
        self.cursor.close()
        self.conn.close()


@sales_bp.route('/sales/edit-invoice/<invoiceNumber>', methods=['GET'])
@login_required('Sales')
def edit_invoice(invoiceNumber):
    """
    Edit an existing invoice.
    """

    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = conn.cursor(dictionary=True)

    try:
        
        cursor.callproc('Get_Edit_Invoice_Details', (invoiceNumber,))
            
        result = None
        for res in cursor.stored_results():
            result = res.fetchone()

        if not result:
            return None

        for field in ["products", "charges"]:
            if result.get(field):
                try:
                    result[field] = json.loads(result[field])
                except Exception:
                    result[field] = []
            else:
                result[field] = []

        if result is None:
            return render_template('dashboards/sales/ready_to_go.html'), 200
            
        result['number'] = invoiceNumber

        if result['grand_total'] == result['paid_amount']:
            result['payment_type'] = 'full_payment'
        else:
            result['payment_type'] = 'half_payment'

        return render_template('dashboards/sales/edit_invoice.html', data=result), 200

    except Exception as e:
        return render_template('dashboards/sales/sell.html'), 200


@sales_bp.route('/sales/update_invoice', methods=['POST'])
def update_invoice_into_database():
    """Update an existing invoice — delegates all logic to stored procedure."""

    conn   = None
    cursor = None

    try:
        # ══════════════════════════════════════════════════════════════
        # PHASE 1: PARSE & VALIDATE FORM INPUTS
        # ══════════════════════════════════════════════════════════════

        # ── Required fields ───────────────────────────────────────────
        invoice_number = request.form.get('invoice_number', '').strip()
        customer_id    = request.form.get('customerId',     '').strip()
        delivery_mode  = request.form.get('delivery_mode',  '').strip()
        payment_mode   = request.form.get('payment_mode',   '').strip()

        if not invoice_number:
            return jsonify({'success': False, 'error': 'Invoice number is required'}), 400
        if not customer_id:
            return jsonify({'success': False, 'error': 'Customer ID is required'}), 400
        if not delivery_mode:
            return jsonify({'success': False, 'error': 'Delivery mode is required'}), 400
        if not payment_mode:
            return jsonify({'success': False, 'error': 'Payment mode is required'}), 400

        # ── Optional fields ───────────────────────────────────────────
        sales_note   = request.form.get('sales_note',   '').strip()
        payment_note = request.form.get('payment_note', '').strip()
        include_gst  = request.form.get('IncludeGST',   'off').strip()
        transport_id = request.form.get('transport_id') or None
        event_id     = request.form.get('event_id')     or None

        # ── Numeric fields ────────────────────────────────────────────
        try:
            paid_amount = float(request.form.get('paid_amount', 0))
            grand_total = float(request.form.get('grand_total', 0))
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'Invalid amount values'}), 400

        if grand_total <= 0:
            return jsonify({'success': False, 'error': 'Grand total must be greater than 0'}), 400

        # ── Business rules ────────────────────────────────────────────
        if payment_mode == 'not_paid':
            paid_amount = 0.0

        if delivery_mode == 'transport' and not transport_id:
            return jsonify({'success': False, 'error': 'Transport ID is required for transport delivery'}), 400

        if delivery_mode != 'transport':
            transport_id = None

        # ── Parse JSON fields ─────────────────────────────────────────
        try:
            raw_products = request.form.get('products')
            raw_charges  = request.form.get('charges', '[]')

            if not raw_products:
                return jsonify({'success': False, 'error': 'Products data is missing'}), 400

            products = json.loads(raw_products)
            charges  = json.loads(raw_charges)

        except json.JSONDecodeError as e:
            return jsonify({'success': False, 'error': f'Invalid JSON data: {str(e)}'}), 400

        if not products or len(products) == 0:
            return jsonify({'success': False, 'error': 'At least one product is required'}), 400

        # ══════════════════════════════════════════════════════════════
        # PHASE 2: PROCESS PRODUCT DATA
        # ══════════════════════════════════════════════════════════════

        tax_rate     = 18 if include_gst == 'on' else 0
        gst_included = 1  if include_gst == 'on' else 0

        product_rows = []
        for i, product in enumerate(products):
            try:
                product_id   = int(product['id'])
                qty          = int(product['quantity'])
                rate         = float(product['finalPrice'])
                total_amount = float(product['total'])
            except (KeyError, ValueError, TypeError) as e:
                return jsonify({
                    'success': False,
                    'error':   f'Invalid data in product at index {i}: {str(e)}'
                }), 400

            if qty <= 0:
                return jsonify({'success': False, 'error': f'Invalid quantity for product {product_id}'}), 400
            if rate < 0:
                return jsonify({'success': False, 'error': f'Invalid price for product {product_id}'}), 400

            original_price = round(rate / (1 + tax_rate / 100), 2)
            gst_amount     = round(rate - original_price, 2)

            product_rows.append({
                'product_id':      product_id,
                'quantity':        qty,
                'price':           original_price,
                'gst_tax_amount':  gst_amount,
                'total_amount':    round(total_amount, 2),
            })

        # ── Format charges ────────────────────────────────────────────
        charge_rows = []
        for i, charge in enumerate(charges):
            try:
                charge_rows.append({
                    'charge_name': str(charge['name']).strip(),
                    'amount':      round(float(charge['amount']), 2),
                })
            except (KeyError, ValueError, TypeError) as e:
                return jsonify({
                    'success': False,
                    'error':   f'Invalid data in charge at index {i}: {str(e)}'
                }), 400

        # ══════════════════════════════════════════════════════════════
        # PHASE 3: RESOLVE INVOICE ID
        # ══════════════════════════════════════════════════════════════

        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Database connection failed'}), 500

        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT id FROM invoices WHERE invoice_number = %s LIMIT 1",
            (invoice_number,)
        )
        invoice_row = cursor.fetchone()

        if not invoice_row:
            return jsonify({'success': False, 'error': 'Invoice not found'}), 404

        invoice_id = invoice_row['id']

        # ── Validate customer ─────────────────────────────────────────
        cursor.execute(
            "SELECT id FROM buddy WHERE id = %s LIMIT 1",
            (customer_id,)
        )
        customer = cursor.fetchone()

        if not customer:
            return jsonify({'success': False, 'error': 'Customer not found'}), 404

        cursor.close()
        cursor = None

        # ══════════════════════════════════════════════════════════════
        # PHASE 4: CALL STORED PROCEDURE
        # ══════════════════════════════════════════════════════════════

        cursor = conn.cursor()

        sp_args = [
            invoice_id,                                          # p_invoice_id
            int(customer['id']),                                 # p_customer_id
            delivery_mode,                                       # p_delivery_mode
            grand_total,                                         # p_grand_total
            gst_included,                                        # p_gst_included
            int(session.get('user_id')),                         # p_user_id
            paid_amount,                                         # p_paid_amount
            payment_mode,                                        # p_payment_mode
            payment_note,                                        # p_payment_note
            sales_note,                                          # p_sales_note
            int(transport_id) if transport_id else None,         # p_transport_id
            int(event_id)     if event_id     else None,         # p_event_id
            0,                                                   # p_completed
            json.dumps(product_rows),                            # p_products_json
            json.dumps(charge_rows),                             # p_charges_json
            0,                                                   # OUT p_status
            '',                                                  # OUT p_message
        ]

        result  = cursor.callproc('update_invoice', sp_args)

        # ── Read OUT parameters ───────────────────────────────────────
        # callproc returns the full args list with OUT params filled in
        sp_status  = int(result[15]  or 0)   # index of OUT p_status
        sp_message = str(result[16]  or '')   # index of OUT p_message

        conn.commit()

        # ══════════════════════════════════════════════════════════════
        # PHASE 5: RETURN RESPONSE
        # ══════════════════════════════════════════════════════════════

        if sp_status == 1:
            return jsonify({
                'success':        True,
                'message':        sp_message,
                'invoice_number': invoice_number,
                'invoice_id':     invoice_id,
            }), 200
        else:
            return jsonify({
                'success': False,
                'error':   sp_message,
            }), 400

    except Exception as e:
        print(f"[update_invoice] Unexpected error: {e}")
        if conn:
            conn.rollback()
        return jsonify({'success': False, 'error': 'An unexpected error occurred'}), 500

    finally:
        if cursor: cursor.close()
        if conn:   conn.close()

########################################################################
# Builty Manage
########################################################################

@sales_bp.route('/builty/ready-to-gos')
@login_required('Sales')
def send_for_builty():
    return render_template('dashboards/sales/ready_builty.html')

class BuiltyModel:
    def __init__(self):
        self.conn = get_db_connection()
        if not self.conn:
            raise Exception("Database connection failed")
        self.cursor = self.conn.cursor(dictionary=True)

    def merge_orders_products(self,data):

        merged = {}

        for item in data:

            # change created_at date formate 
            item['created_at'] = item['created_at'].strftime("%d/%m/%Y %I:%M %p") 
            item['sales_date_time'] = item['sales_date_time'].strftime("%d/%m/%Y %I:%M %p")
            item['packing_date_time'] = item['packing_date_time'].strftime("%d/%m/%Y %I:%M %p")
            item['transport_date_time'] = item['transport_date_time'].strftime("%d/%m/%Y %I:%M %p")
            # passed tracking status with date            
            trackingStatus = 0
            trackingDates = []

            if item['sales_proceed_for_packing']:

                if item['sales_date_time']:
                    trackingDates.append(item['sales_date_time'])
                else:
                    trackingDates.append('')
                trackingStatus = 1                
            
                if item['packing_proceed_for_transport']:
                    
                    if item['packing_proceed_for_transport']:
                        trackingDates.append(item['packing_date_time'])
                    else:
                        trackingDates.append('')
                    trackingStatus = 2                
                
                    if item['transport_proceed_for_builty']:
                        
                        if item['transport_proceed_for_builty']:
                            trackingDates.append(item['transport_date_time'])
                        else:
                            trackingDates.append('')
                        trackingStatus = 3
            
                        if item['builty_received']:

                            if item['builty_received']:
                                trackingDates.append(item['builty_date_time'].strftime("%d/%m/%Y %I:%M %p"))
                            else:
                                trackingDates.append('')
                            trackingStatus = 4
            
                            if item['verify_by_manager']:
                                
                                if item['verify_by_manager']:
                                    trackingDates.append(item['verify_manager_date_time'].strftime("%d/%m/%Y %I:%M %p"))
                                else:
                                    trackingDates.append('')
                                trackingStatus = 5


            item['trackingStatus'] = trackingStatus
            item['trackingDates'] = trackingDates


            # merge products
            order_id = item["id"]
            product_info = {
                "name": item["name"],
                "qty": item["quantity"],
                "price": float(item["price"]),
                "tax_amount": float(item["gst_tax_amount"]),
                "total": float(item["total_amount"]),
            }

            if order_id not in merged:
                # Create a new entry if the id doesn't exist yet
                merged[order_id] = {
                    **{k: v for k, v in item.items() if k not in ["name", "quantity", "price", "gst_tax_amount", "total_amount", "invoices_items_id", "product_id", "products_id"]},
                    "products": [product_info],
                }
            else:
                # If it already exists, just append the product info
                merged[order_id]["products"].append(product_info)

        return list(merged.values())

    def fetch_builty_orders(self):
        query = f"""
                    SELECT
                        inv.id,
                        inv.invoice_number,
                        DATE_FORMAT(lot.transport_date_time, '%d/%m/%Y %h:%i %p') AS transport_date_time
                        
                    FROM invoices inv

                    LEFT JOIN live_order_track lot ON inv.id = lot.invoice_id
                        AND lot.cancel_order_status = 0
                        AND lot.sales_proceed_for_packing = 1
                        AND lot.packing_proceed_for_transport = 1
                        AND lot.transport_proceed_for_builty = 1
                        AND lot.builty_received = 0

                    LEFT JOIN users up ON lot.packing_proceed_by = up.id
                    LEFT JOIN users ut ON lot.transport_proceed_by = ut.id
                    LEFT JOIN invoice_items ii ON inv.id = ii.invoice_id
                    LEFT JOIN products p ON ii.product_id = p.id
                    LEFT JOIN transport ON inv.transport_id = transport.id

                    WHERE lot.builty_received = 0
                        AND inv.completed = 0
                        AND (inv.delivery_mode = 'transport' OR inv.delivery_mode = 'post') 
                        AND inv.invoice_created_by_user_id = {session.get('user_id')}
                    ORDER BY inv.created_at DESC;
                """

        self.cursor.execute(query)
        all_order_data = self.cursor.fetchall()
        
        if not all_order_data:
            return []

        return all_order_data

    def fetch_builty_order_detailes(self,invoiceNumber):
        query = """
                    SELECT
                        inv.id,
                        inv.invoice_number,
                        inv.customer_id,
                        inv.grand_total,
                        inv.payment_mode,
                        inv.paid_amount,
                        inv.left_to_paid,
                        inv.sales_note,
                        inv.invoice_created_by_user_id,
                        inv.payment_note,
                        inv.gst_included,
                        inv.created_at,
                        inv.delivery_mode,

                        b.id AS buddy_id,
                        b.name AS customer,
                        b.address,
                        b.state,
                        b.pincode,
                        b.mobile,

                        u.id AS users_id,
                        u.username,

                        up.username AS pack_by,
                        ut.username AS trans_by,

                        ii.id AS invoices_items_id,
                        ii.product_id,
                        ii.quantity,
                        ii.price,
                        ii.gst_tax_amount,
                        ii.total_amount,
                        ii.created_at,

                        p.id AS products_id,
                        p.name,

                        lot.id AS live_order_track_id,
                        lot.sales_proceed_for_packing,
                        lot.sales_date_time,
                        lot.packing_proceed_for_transport,
                        lot.packing_date_time,
                        lot.packing_proceed_by,
                        lot.transport_proceed_for_builty,
                        lot.transport_date_time,
                        lot.transport_proceed_by,
                        lot.builty_proceed_by,
                        lot.builty_received,
                        lot.builty_date_time,
                        lot.payment_confirm_status,
                        lot.cancel_order_status,
                        lot.verify_by_manager,
                        lot.verify_by_manager_id,
                        lot.verify_manager_date_time,
                        lot.packing_note,
                        lot.transport_note,
                        
                        transport.pincode AS transport_pincode,
                        transport.name AS transport_name,
                        transport.city AS transport_city,
                        transport.days AS transport_days

                    FROM invoices inv

                    LEFT JOIN buddy b ON inv.customer_id = b.id
                    LEFT JOIN users u ON inv.invoice_created_by_user_id = u.id
                    LEFT JOIN live_order_track lot ON inv.id = lot.invoice_id
                        AND lot.cancel_order_status = 0
                        AND lot.sales_proceed_for_packing = 1
                        AND lot.packing_proceed_for_transport = 1
                        AND lot.transport_proceed_for_builty = 1
                        AND lot.builty_received = 0

                    LEFT JOIN users up ON lot.packing_proceed_by = up.id
                    LEFT JOIN users ut ON lot.transport_proceed_by = ut.id
                    LEFT JOIN invoice_items ii ON inv.id = ii.invoice_id
                    LEFT JOIN products p ON ii.product_id = p.id
                    LEFT JOIN transport ON inv.transport_id = transport.id

                    WHERE lot.builty_received = 0
                        AND inv.completed = 0
                        AND (inv.delivery_mode = 'transport' OR inv.delivery_mode = 'post') 
                        AND inv.invoice_number = %s
                        
                    ORDER BY inv.created_at DESC;
                """

        self.cursor.execute(query, (invoiceNumber,))
        all_order_data = self.cursor.fetchall()
        
        if not all_order_data:
            return []

        # Merge products into orders
        merged_orders = self.merge_orders_products(all_order_data)

        return merged_orders[0]

    def cancel_order(self,data):
        try:
            update_query = """

            UPDATE live_order_track
            SET cancel_order_status = 1
            WHERE id = %s;
            """
            self.cursor.execute(update_query, (data.get('track_order_id'),))
            self.conn.commit()  # commit on connection, not cursor
            
            update_query = """

            UPDATE invoices
            SET cancel_order_status = 1
            WHERE invoices.id = (SELECT invoice_id from live_order_track WHERE id = %s );
            """
            self.cursor.execute(update_query, (data.get('track_order_id'),))
            self.conn.commit()  # commit on connection, not cursor
            

            insert_query = """
                
                INSERT INTO cancelled_orders (
                    invoice_id,cancelled_by, reason,live_order_track_id 
                ) VALUES (%s, %s, %s,%s)
            """

            self.cursor.execute(insert_query, (data.get('invoice_id'),session.get('user_id'),data.get('reason'),data.get('track_order_id'),))
            self.conn.commit()  # commit on connection, not cursor
            
            return {"success": True, "message": f"Order successfully Cancel"}
            
        except Exception as e:
            self.conn.rollback()  # rollback on connection, not cursor
            return {"success": False, "message": f"Somthing went wrong to cancel order"}

    def builty_recived(self,invoice_id,data):
        try:
            update_query = """
            UPDATE live_order_track
            SET builty_received = 1, builty_note = %s, builty_proceed_by = %s,builty_date_time = NOW()
            WHERE invoice_id = %s;
            """
            self.cursor.execute(update_query, (data.get('builtyNote'),session.get('user_id'),invoice_id,))
            self.conn.commit() 
            return {"success": True}
            
        except Exception as e:
            self.conn.rollback()  # rollback on connection, not cursor
            return {"success": False,"msg":e}

    def close(self):
        self.cursor.close()
        self.conn.close() # type: ignore
    
@sales_bp.route('/builty/builty-orders-list', methods=['GET'])
@login_required('Sales')
def builty_my_pack_list():
    """
    Fetch the list of orders for the logged-in transport user.
    """    
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not logged in'}), 401
        
        my_pack = BuiltyModel()
        orders = my_pack.fetch_builty_orders()
        
        my_pack.close()

        if not orders:
            return jsonify([]), 200
        
        return jsonify(orders)

    except Exception as e:
        print(f"Error fetching orders: {e}")
        return jsonify({'error': 'Failed to fetch orders'}), 500

    finally:
        my_pack.close()

@sales_bp.route('/builty/builty-order-details/<invoiceNumber>', methods=['GET'])
@login_required('Sales')
def builty_my_pack_order_detailes(invoiceNumber):
    """
    Fetch the list of orders for the logged-in transport user.
    """    
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not logged in'}), 401
        
        my_pack = BuiltyModel()
        orders = my_pack.fetch_builty_order_detailes(invoiceNumber)
        
        my_pack.close()

        if not orders:
            return jsonify([]), 200
        
        return jsonify(orders)

    except Exception as e:
        print(f"Error fetching orders: {e}")
        return jsonify({'error': 'Failed to fetch orders'}), 500

    finally:
        my_pack.close()


@sales_bp.route('/builty/cancel_order', methods=['POST'])
@login_required('Sales')
def builty_cancel_order():
    try:
        data = request.get_json()
        track_order_id = data.get('track_order_id') #reason
        if not track_order_id or not str(track_order_id).isdigit() or not data.get('invoice_id'):
            return jsonify({"success": False, "message": "Invalid Order!"}), 400

        for_cancel_order = BuiltyModel()
        response = for_cancel_order.cancel_order(data)

        if response.get('success'):
            return jsonify({"success": True, "message": "Order Cancelled Successfully"}), 200
        
        for_cancel_order.close()
        return {"success": False, "message": f"Somthing went wrong!"},500

    except Exception as e:
        return jsonify({"success": False, "message": f"From Server Side: {e}"}), 500

@sales_bp.route('/builty/builty-recived', methods=['POST'])
@login_required('Sales')
def builty_recived():
    try:
        data = request.get_json()
        invoiceNumber = data.get('invoiceNumber')

        if not invoiceNumber:
            return jsonify({"success": False, "message": "Invalid Invoice Number"}), 400

        result = get_invoice_id(invoiceNumber)

        invoice_id = None
        if result['status']:
            invoice_id = result['invoice_id']
        else:
            return jsonify({'error': 'Invoice not found'}), 404

        if invoice_id is None:
            return jsonify({"success": False, "message": "Order not found"}), 404

        builty_obj = BuiltyModel()
        response = builty_obj.builty_recived(invoice_id,data)

        if response.get('success'):
            return jsonify({"success": True, "message": "Builty Recived Successfully"}),200

        builty_obj.close()
        return jsonify({"success": False, "message": f"Somthing went wrong!"}),500
    
    except Exception as e:
        return jsonify({"success": False, "message": f"From Server Side: {e}"}), 500



########################################################################
# Payments Manage
########################################################################

@sales_bp.route('/sales/payments')
@login_required('Sales')
def send_for_payments():
    return render_template('dashboards/sales/payments.html')

@sales_bp.route('/sales/payments/customers', methods=['GET'])
def get_customers_for_payments():
    search = request.args.get('search', '').strip()

    if not search:
        return jsonify([])

    try:

        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database connection failed'}), 500

        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT id, name as customer_name, mobile as number
            FROM buddy
            WHERE active = 1
            AND (
                name LIKE %s
                OR mobile LIKE %s
            )
            LIMIT 10
        """

        like_pattern = f"%{search}%"
        cursor.execute(query, (like_pattern, like_pattern))
        results = cursor.fetchall()

        cursor.close()
        conn.close()

        return jsonify(results)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@sales_bp.route('/sales/payments/customer', methods=['GET'])
def get_customers_balance():
    search = request.args.get('balance', '').strip()

    if not search:
        return jsonify({'balance': 0})

    try:

        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database connection failed'}), 500

        cursor = conn.cursor(dictionary=True)
        query = """
        SELECT 
            (SELECT 
                        COALESCE(SUM(inv.left_to_paid), 0)
                        FROM invoices inv 
                        LEFT JOIN live_order_track lot ON inv.id = lot.invoice_id 
                        where
                        lot.cancel_order_status = 0 
                        AND lot.sales_proceed_for_packing = 1
                        AND inv.left_to_paid > 0
                        AND inv.customer_id = %s) -
            (SELECT COALESCE(SUM(amount), 0) FROM `payment_transations` WHERE customer_id = %s and active = 1 and payment_verified_by is not null ) as balance;
        """
        cursor.execute(query, (search, search))
        results = cursor.fetchone()

        cursor.close()
        conn.close()

        import time
        time.sleep(5)  # Simulate processing delay

        return jsonify({'balance': int(results['balance']) if results['balance'] else 0})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@sales_bp.route('/sales/add-transaction', methods=['POST'])
@login_required('Sales')
def add_transaction():
    try:
        data = request.get_json()
        amount = data.get('amount', 0)
        customer_id = data.get('customer_id', None)
        payment_mode = data.get('mode', None)
        payment_note = data.get('note', None)

        conn = get_db_connection()

        if not conn:
            return jsonify({'success': False,'error': 'Database connection failed'}), 500

        if amount < 0 or customer_id is None or payment_mode is None:
            return jsonify({'success': False,'error': 'Please fill in all fields with valid information.'}),500

        if payment_mode not in ['Cash', 'Online',]:
            return jsonify({'success': False,'error': 'Invalid payment mode.'}), 400

        cursor = conn.cursor(dictionary=True)

        # Check if customer exists
        cursor.execute("SELECT id FROM buddy WHERE id = %s and active = 1", (customer_id,))
        existing_customer = cursor.fetchone()
        
        if not existing_customer:
            return jsonify({'success': False, 'error': f'Customer not exists'})
                
        # Insert into database
        cursor.execute("INSERT INTO payment_transations (payment_received_by, payment_received_at, payment_method, amount, customer_id,note) VALUES (%s, %s, %s, %s, %s,%s)",
                                          (session.get('user_id'), datetime.now(), payment_mode, amount, customer_id,payment_note))
        
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'success': True, "msg":"Payment added successfully"}), 200
        
    except Exception as e:
        conn.rollback()
        import traceback
        print(traceback.print_exc())
        return jsonify({'success': False,'error': 'Internal server error'}), 500

@sales_bp.route('/sales/my-transactions', methods=['GET'])
@login_required('Sales')
def fetch_my_transactions():
    try:
        
        conn = get_db_connection()

        if not conn:
            return jsonify({'success': False,'error': 'Database connection failed'}), 500

        
        cursor = conn.cursor(dictionary=True)
        
        query = f"""
            SELECT 
            pt.id, 
            pt.payment_method,
            pt.payment_received_at,
            ur.username as received_by,
            pt.amount,
            pt.note,
            b.name as customer_name
            FROM `payment_transations` pt
            LEFT JOIN users ur ON ur.id = payment_received_by
            LEFT JOIN buddy b ON b.id = pt.customer_id
            WHERE pt.payment_received_by = {session.get('user_id')}
            AND pt.active = 1
            AND pt.payment_verified_by is null
            ORDER BY pt.payment_received_at DESC;
        """
        cursor.execute(query,)
        results = cursor.fetchall()
        cursor.close()
        conn.close()

        formatted_results = []

        for item in results:
            received_at = item.get("payment_received_at")

            formatted_item = {
                "id": f"{item['id']}",
                "amount": float(item["amount"]),
                "mode": item["payment_method"],
                "received_by": item["received_by"],
                "customer_name": item["customer_name"],
                "note": item["note"],
                "received_date": received_at.strftime("%Y-%m-%d") if received_at else None,
                "received_time": received_at.strftime("%I:%M %p") if received_at else None,
                "verified": False            
            }

            formatted_results.append(formatted_item)

        import time
        time.sleep(5)  # Simulate processing delay


        return jsonify({'success': True, "data": formatted_results}), 200
        
    except Exception as e:
        conn.rollback()
        import traceback
        print(traceback.print_exc())
        return jsonify({'success': False,'error': 'Internal server error'}), 500



@sales_bp.route('/sales/payments/fetch-customer-transactions', methods=['POST'])
@login_required('Sales')
def fetch_customer_transactions():
    try:
        data = request.get_json()
        customer_id = data.get('customer_id', None)

        conn = get_db_connection()

        if not conn:
            return jsonify({'success': False,'error': 'Database connection failed'}), 500

        if customer_id is None:
            return jsonify({'success': False,'error': 'Please select a customer.'}),500


        cursor = conn.cursor(dictionary=True)

        # Check if customer exists
        cursor.execute("SELECT id FROM buddy WHERE id = %s and active = 1", (customer_id,))
        existing_customer = cursor.fetchone()
        
        if not existing_customer:
            return jsonify({'success': False, 'error': f'Customer not exists'})
                
        query = f"""
            SELECT 
            pt.id, 
            pt.payment_method,
            pt.payment_received_at,
            ur.username as received_by,
            pt.payment_verified_at,
            uv.username as verified_by,
            pt.amount,
            pt.note,
            pt.verify_note
            FROM `payment_transations` pt
            LEFT JOIN users ur ON ur.id = payment_received_by
            LEFT JOIN users uv ON uv.id = payment_verified_by
            WHERE pt.customer_id = {customer_id}
            AND pt.active = 1
            ORDER BY pt.payment_received_at DESC;
        """
        cursor.execute(query,)
        results = cursor.fetchall()
        cursor.close()
        conn.close()

        formatted_results = []

        for item in results:
            received_at = item.get("payment_received_at")
            verified_at = item.get("payment_verified_at")

            formatted_item = {
                "id": f"{item['id']}",
                "amount": float(item["amount"]),
                "mode": item["payment_method"],
                "received_by": item["received_by"],
                "note": item["note"],
                "verify_note": item["verify_note"],
                "received_date": received_at.strftime("%Y-%m-%d") if received_at else None,
                "received_time": received_at.strftime("%I:%M %p") if received_at else None,
                "verified": bool(item["verified_by"] and item["received_by"]),
                "verified_by": item["verified_by"],
                "verified_date": verified_at.strftime("%Y-%m-%d") if verified_at else None,
                "verified_time": verified_at.strftime("%I:%M %p") if verified_at else None,
            }

            formatted_results.append(formatted_item)

        import time
        time.sleep(5)  # Simulate processing delay


        return jsonify({'success': True, "data": formatted_results}), 200
        
    except Exception as e:
        conn.rollback()
        import traceback
        print(traceback.print_exc())
        return jsonify({'success': False,'error': 'Internal server error'}), 500


@sales_bp.route('/sales/delete-transaction', methods=['POST'])
@login_required('Sales')
def delete_transaction():
    try:
        data = request.get_json()

        transaction_id = data.get('transaction_id', None)

        conn = get_db_connection()

        if not conn:
            return jsonify({'success': False,'error': 'Database connection failed'}), 500

        if transaction_id is None:
            return jsonify({'success': False,'error': 'Please select a transaction to delete.'}),500

        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM payment_transations WHERE id = %s and active = 1 and payment_received_by is not null and payment_verified_by is null", (transaction_id,))
        
        existing_transaction = cursor.fetchone()

        if not existing_transaction:
            return jsonify({'success': False, 'error': f'Transaction does not exist'}), 400

        cursor = conn.cursor(dictionary=True)

        # Check if customer exists
        cursor.execute("UPDATE payment_transations SET active = 0 WHERE id = %s", (transaction_id,))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'success': True, "msg":"Transaction deleted successfully"}), 200
        
    except Exception as e:
        conn.rollback()
        import traceback
        print(traceback.print_exc())
        return jsonify({'success': False,'error': 'Internal server error'}), 500
