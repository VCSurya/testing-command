from flask import Blueprint, render_template, jsonify, request, session, send_file
from utils import get_db_connection, login_required, get_invoice_id
import mysql.connector
from datetime import datetime
import pytz
import json
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.units import inch
from io import BytesIO
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import random
import string
from decimal import Decimal

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
    return render_template('dashboards/sales/sell.html', active_page='sell')


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

# Class ralated sales dasebored
class Dasebored:
    def __init__(self):
        self.conn = get_db_connection()
        if not self.conn:
            raise Exception("Database connection failed")
        self.cursor = self.conn.cursor(dictionary=True)

    def get_dasebored_data(self,user_id):
        query = f"""
        SELECT 
        (SELECT COUNT(*) FROM invoices WHERE invoice_created_by_user_id = {user_id} AND cancel_order_status = 0) AS total_sales_order_count,
        (SELECT IFNULL(SUM(grand_total), 0) FROM invoices WHERE invoice_created_by_user_id = {user_id} AND cancel_order_status = 0) AS total_sales_order_sum,
        
        (SELECT COUNT(*) FROM invoices WHERE invoice_created_by_user_id = {user_id} AND completed = 1 AND cancel_order_status = 0) AS completed_order_count,
        (SELECT IFNULL(SUM(grand_total), 0) FROM invoices WHERE invoice_created_by_user_id = {user_id} AND completed = 1 AND cancel_order_status = 0) AS completed_order_sum,
        
        (SELECT COUNT(*) FROM invoices WHERE invoice_created_by_user_id = {user_id} AND completed = 0 AND cancel_order_status = 0) AS pending_order_count,
        (SELECT IFNULL(SUM(grand_total), 0) FROM invoices WHERE invoice_created_by_user_id = {user_id} AND completed = 0 AND cancel_order_status = 0) AS pending_order_sum,
        
        (SELECT COUNT(*) FROM live_order_track 
            JOIN invoices ON invoices.id = live_order_track.invoice_id 
            WHERE live_order_track.sales_proceed_for_packing = 1 AND invoices.invoice_created_by_user_id = {user_id} AND invoices.completed = 0 AND invoices.cancel_order_status = 0) AS running_order_count,
        
        (SELECT COUNT(*) FROM live_order_track 
            JOIN invoices ON invoices.id = live_order_track.invoice_id      
            WHERE live_order_track.sales_proceed_for_packing = 0 AND invoices.invoice_created_by_user_id = {user_id} AND invoices.completed = 0 AND invoices.cancel_order_status = 0) AS draft_order_count,
        
        (SELECT COUNT(*) from invoices JOIN cancelled_orders on cancelled_orders.invoice_id = invoices.id WHERE invoices.invoice_created_by_user_id = {user_id}) AS total_cancelled_orders,
        (SELECT COUNT(*) from invoices JOIN cancelled_orders on cancelled_orders.invoice_id = invoices.id WHERE invoices.invoice_created_by_user_id = {user_id} AND cancelled_orders.confirm_by_saler = 0) AS pending_cancelled_orders,
        (SELECT COUNT(*) from invoices JOIN cancelled_orders on cancelled_orders.invoice_id = invoices.id WHERE invoices.invoice_created_by_user_id = {user_id} AND cancelled_orders.confirm_by_saler = 1) AS confirmed_cancelled_orders,
        
        (SELECT COUNT(*) FROM invoices WHERE invoice_created_by_user_id = {user_id} AND cancel_order_status = 0 AND DATE(created_at) = CURRENT_DATE()) AS today_order_count,
        (SELECT IFNULL(SUM(grand_total), 0) FROM invoices WHERE invoice_created_by_user_id = {user_id} AND cancel_order_status = 0 AND DATE(created_at) = CURRENT_DATE()) AS today_order_sum,
        
        (SELECT COUNT(*) FROM live_order_track 
            JOIN invoices ON invoices.id = live_order_track.invoice_id 
            WHERE live_order_track.sales_proceed_for_packing = 0 AND invoices.invoice_created_by_user_id = {user_id} AND invoices.completed = 0 AND invoices.cancel_order_status = 0 AND DATE(invoices.created_at) = CURRENT_DATE()) AS today_draft_order_count
        """

        try:    
            self.cursor.execute(query,)
            result = self.cursor.fetchone()
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        finally:
            self.conn.close()

        def safe_int(value):
            return int(value) if value is not None else 0

        def safe_float(value):
            return float(value) if value is not None else 0.0

        response = {
            "total_sales_orders": {
                "count": safe_int(result["total_sales_order_count"]),
            },
            "completed_orders": {
                "count": safe_int(result["completed_order_count"]),
                "sum": safe_float(result["completed_order_sum"])
            },
            "pending_orders": {
                "count": safe_int(result["pending_order_count"]),
                "sum": safe_float(result["pending_order_sum"])
            },
            "running_orders": {
                "count": safe_int(result["running_order_count"])
            },
            "draft_orders": {
                "count": safe_int(result["draft_order_count"])
            },
            "cancelled_orders": {
                "total": safe_int(result["total_cancelled_orders"]),
                "pending_confirmation": safe_int(result["pending_cancelled_orders"]),
                "confirmed": safe_int(result["confirmed_cancelled_orders"])
            },
            "today_orders": {
                "count": safe_int(result["today_order_count"]),
                "sum": safe_float(result["today_order_sum"])
            },
            "today_draft_orders": {
                "count": safe_int(result["today_draft_order_count"])
            }
        }


        return jsonify(response)



@sales_bp.route('/sales/dasebored-data', methods=['GET'])
@login_required('Sales')
def sales_summary():
    obj = Dasebored()
    return obj.get_dasebored_data(session.get('user_id'))



# Class ralated sales routes
class Sales:

    def data_base_connection_check(self):
        # Establish database connection using the utility function
        self.conn = get_db_connection()
        if self.conn:
            self.cursor = self.conn.cursor()
            return True
        else:
            return False

    def generate_unique_invoice_number(self, cursor):
        """Generate a unique alphanumeric invoice number."""
        while True:
            invoice_number = ''.join(random.choices(
                string.ascii_uppercase + string.digits, k=10))
            cursor.execute(
                "SELECT COUNT(*) FROM invoices WHERE invoice_number = %s", (invoice_number,))
            (count,) = cursor.fetchone()
            if count == 0:
                return invoice_number

    def insert_live_order_track(self, invoice_id):
        """
        Insert a saved invoice into the database live order track table.
        """
        if not self.data_base_connection_check():
            return {'error': 'Database Error!'}

        cursor = self.conn.cursor()

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
            cursor.execute(insert_query, values)
            self.conn.commit()

            return {'success': True}

        except mysql.connector.Error as e:
            self.conn.rollback()
            return {'error': str(e)}

        finally:
            cursor.close()

    def add_invoice_detail(self, invoice_data):

        if not self.conn:
            return "Database connection is not available."

        try:
            cursor = self.conn.cursor()

            # Step 1: Generate unique invoice number
            invoice_number = self.generate_unique_invoice_number(cursor)

            # Step 2: Prepare invoice data
            gst_included = 1 if invoice_data.get('gst_included') == 'on' else 0
            left_to_paid = invoice_data['grand_total'] - \
                invoice_data['paid_amount']

            insert_invoice_query = """
                INSERT INTO invoices (
                    customer_id, delivery_mode, grand_total, gst_included,
                    invoice_created_by_user_id, left_to_paid, paid_amount,
                    payment_mode, payment_note, sales_note, transport_id,
                    invoice_number, event_id ,completed,created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,NOW())
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
                invoice_number,
                invoice_data['event_id'] if invoice_data.get(
                    'event_id') else None,
                # Default to 0 if not provided
                invoice_data.get('completed', 0)
            )

            cursor.execute(insert_invoice_query, invoice_values)
            invoice_id = cursor.lastrowid

            # Step 3: Insert invoice_items
            insert_item_query = """
                INSERT INTO invoice_items (
                    invoice_id, product_id, quantity, price, total_amount,
                    gst_tax_amount, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """

            for product in invoice_data['products']:
                product_id = int(product[0])
                # You may want to extract actual quantity from product[2] if needed
                quantity = int(product[1])
                price = float(product[2])
                gst_tax_amount = float(product[3])
                total_amount = float(product[4])

                item_values = (
                    invoice_id,
                    product_id,
                    quantity,
                    price,
                    total_amount,
                    gst_tax_amount
                )

                cursor.execute(insert_item_query, item_values)

            self.conn.commit()
            return {"invoice_id": invoice_id, "invoice_number": invoice_number}

        except mysql.connector.Error as e:
            self.conn.rollback()
            return f"Error: {str(e)}"

    def close_connection(self):
        # Close the database connection if it exists
        if self.conn:
            self.conn.close()

@sales_bp.route('/sales/input-transport/<string:input>', methods=['GET'])
@login_required('Sales')
def get_transport_input(input):
    
    conn = get_db_connection()
    if not conn:
        return jsonify([]), 500  # Return HTTP 500 if DB connection fails

    cursor = conn.cursor(dictionary=True)
    try:
        
        if input.isdigit():
            cursor.execute(f"SELECT id,pincode,name,city,days FROM `transport` WHERE pincode LIKE '{input}%' LIMIT 15;")
        else:
            cursor.execute(f"SELECT id,pincode,name,city,days FROM `transport` WHERE city LIKE '{input}%' LIMIT 15;")

        customers = cursor.fetchall()
        return jsonify(customers)
    
    except Exception as e:
        print(f"Error fetching customers: {e}")
        return jsonify({'error': 'Failed to fetch customers'}), 500
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


@sales_bp.route('/sales/customers', methods=['GET'])
@login_required('Sales')
def get_customers():
    conn = get_db_connection()
    if not conn:
        return jsonify([]), 500  # Return HTTP 500 if DB connection fails

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM buddy")
        customers = cursor.fetchall()
        return jsonify([{
            'id': c['id'],
            'name': c['name'],
            'mobile': c['mobile'],
            'address': c['address']
        } for c in customers])
    except Exception as e:
        print(f"Error fetching customers: {e}")
        return jsonify({'error': 'Failed to fetch customers'}), 500
    finally:
        cursor.close()
        conn.close()

@sales_bp.route('/sales/input-customers/<string:input>', methods=['GET'])
@login_required('Sales')
def get_customers_input(input):
    
    conn = get_db_connection()
    if not conn:
        return jsonify([]), 500  # Return HTTP 500 if DB connection fails

    cursor = conn.cursor(dictionary=True)
    try:
        
        if input.isdigit():
            cursor.execute(f"SELECT name,address,state,pincode,mobile FROM `buddy` WHERE mobile LIKE '{input}%' LIMIT 10;")
        else:
            cursor.execute(f"SELECT name,address,state,pincode,mobile FROM `buddy` WHERE name LIKE '%{input}%' LIMIT 10;")

        customers = cursor.fetchall()
        return jsonify(customers)
    except Exception as e:
        print(f"Error fetching customers: {e}")
        return jsonify({'error': 'Failed to fetch customers'}), 500
    finally:
        cursor.close()
        conn.close()

@sales_bp.route('/sales/add-customer', methods=['POST'])
@login_required('Sales')
def add_new_customer():
    try:
        data = request.get_json()

        required_fields = ['name', 'address', 'pincode', 'mobile']
        if not all(field in data for field in required_fields):
            return jsonify({'error': 'Missing required fields'}), 400

        name = data['name']
        state = data['state']
        address = data['address']
        pincode = data['pincode']
        mobile = data['mobile']

        conn = get_db_connection()

        if not conn:
            return jsonify({'success': False,'error': 'Database connection failed'}), 500

        if not all([name, address, state, pincode, mobile]):
            return jsonify({'success': False,'error': 'Please fill in all fields with valid information.'}),500

        if not mobile.isdigit():
            return jsonify({'success': False,'error': 'Enter valid mobile number'}),500

        if not pincode.isdigit():
            return jsonify({'success': False,'error': 'Enter valid PINCODE number'}),500
    
        cursor = conn.cursor(dictionary=True)

        # Check if username already exists
        cursor.execute("SELECT * FROM buddy WHERE mobile = %s", (mobile,))
        existing_user = cursor.fetchone()
        
        if existing_user:
            return jsonify({'success': False, 'error': f'{mobile}: Customer already exists'})

        # Insert new product into database
        cursor.execute("INSERT INTO buddy (name, address, state, pincode, mobile,created_by) VALUES (%s, %s, %s, %s, %s,%s)",
                       (name, address, state, pincode, mobile, session.get('user_id')))
        conn.commit()
        
        mobile = int(mobile)
        cursor.execute("SELECT name, address,pincode, mobile FROM buddy WHERE mobile = %s",(mobile,))
        exist = cursor.fetchone()
        
        cursor.close()
        conn.close()

        return jsonify({'success': True,"data":exist if exist else {}})

    except Exception as e:
        print(e)
        import traceback
        print(traceback.print_exc())
        return jsonify({'success': False,'error': 'Internal server error'}), 500


@sales_bp.route('/sales/input-products/<string:input>', methods=['GET'])
@login_required('Sales')
def get_products_input(input):
    
    conn = get_db_connection()
    if not conn:
        return jsonify([]), 500  # Return HTTP 500 if DB connection fails

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(f"SELECT id,name,selling_price as price FROM products WHERE name LIKE '%{input}%' LIMIT 30")
        products = cursor.fetchall()
        return jsonify(products)
    except Exception as e:
        print(f"Error fetching products: {e}")
        return jsonify({'error': 'Failed to fetch products'}), 500
    finally:
        cursor.close()
        conn.close()


@sales_bp.route('/sales/products')
@login_required('Sales')
def get_products():
    conn = get_db_connection()
    if not conn:
        return jsonify([]), 500  # Return HTTP 500 if DB connection fails

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM products")
        products = cursor.fetchall()
        return jsonify([{
            'id': p['id'],
            'name': p['name'],
            'price': float(p['selling_price'])
        } for p in products])

    except Exception as e:
        print(f"Error fetching customers: {e}")
        return jsonify({'error': 'Failed to fetch customers'}), 500

    finally:
        cursor.close()
        conn.close()


@sales_bp.route('/sales/add_new_product', methods=['POST'])
@login_required('Sales')
def add_new_product():
    try:
        # Get form data
        name = request.form.get('name')
        price = request.form.get('price')
        hsn_code = request.form.get('hsn_code')
        gst_rate = request.form.get('gst_rate')
        description = request.form.get('description')

        # Connect to database
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database connection failed'}), 500

        cursor = conn.cursor()

        # Insert new product into database
        cursor.execute("INSERT INTO products (name, price, hsn_code, gst_rate, description) VALUES (%s, %s, %s, %s, %s)",
                       (name, price, hsn_code, gst_rate, description))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'message': 'Product added successfully'}), 200

    except Exception as e:
        print(f"Error adding product: {e}")
        return jsonify({'error': str(e)}), 500

# ImmutableMultiDict([('customer_id', '3'), ('delivery_mode', 'transport'), ('transport_company', ''), ('payment_mode', 'cash'), ('payment_note', ''), ('payment_type', 'full_payment'), ('paid_amount', '2000'), ('left_to_pay_display', '0.00'), ('IncludeGST', 'on'), ('grand_total', '2000'), ('sales_note', ''), ('products', '[{"id":9,"name":"\\" it\'s a boy \\" ring fabric ","finalPrice":2000,"quantity":1,"total":2000}]')])


@sales_bp.route('/sales/save_invoice', methods=['POST'])
def save_invoice_into_database():
    """ Save invoice data to database """
    try:

        # Get form data
        customer_id = request.form.get('customerId')
        delivery_mode = request.form.get('delivery_mode')
        transport_id = request.form.get('transport_id')
        payment_mode = request.form.get('payment_mode')
        payment_type = request.form.get('payment_type')
        paid_amount = float(request.form.get('paid_amount', 0))
        grand_total = float(request.form.get('grand_total', 0))
        sales_note = request.form.get('sales_note', '')
        IncludeGST = request.form.get('IncludeGST', 'off')
        event_id = request.form.get('event_id', None)

        if payment_mode == "not_paid":
            paid_amount = 0

        # Get products from form data
        products = request.form.get('products')
        if products or customer_id:
            products = json.loads(products)
        else:
            return jsonify({'error': 'Some data is Missing in the bill'}), 400

        if grand_total < 0:
            return jsonify({'error': 'Some data is Missing in the bill'}), 400

        # Need transport_id 
        if delivery_mode == 'transport':
            if not transport_id:
                return jsonify({'error': 'Some data is Missing in the bill'}), 400

        # Get customer details to validate
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database connection failed'}), 500

        if not customer_id or customer_id == "": 
            return jsonify({'error': 'Invalid mobile number'}), 500

        cursor = conn.cursor(dictionary=True)
        cursor.execute(f"SELECT id FROM buddy WHERE mobile = CAST({customer_id} AS INT)")
        customer = cursor.fetchone()
        conn.close()

        if not customer:
            return jsonify({'error': 'Customer not found'}), 404

        # Process products for database
        tax_rate = 0
        if IncludeGST == 'on':
            tax_rate = 18

        product_data_for_sql_table = []
        for product in products:
            qty = product['quantity']
            rate = float(product['finalPrice'])

            # Calculate the original amount (before GST)
            original_amount = rate / (1 + tax_rate / 100)
            # Calculate the GST amount
            gst_amount = rate - original_amount
            tax_amount = float(f"{gst_amount:.2f}")
            total_amount = float(product['total'])

            product_data_for_sql_table.append([
                product['id'],
                f"{qty}",
                f"{original_amount:.2f}",
                f"{tax_amount:.2f}",
                f"{total_amount:.0f}"
            ])

        # Prepare bill data for database
        bill_data = {
            'customer_id': customer['id'],
            'delivery_mode': delivery_mode,
            'grand_total': grand_total,
            'payment_mode': payment_mode,
            'paid_amount': paid_amount,
            'transport_id': transport_id,
            'sales_note': sales_note,
            'invoice_created_by_user_id': session.get('user_id'),
            'payment_note': request.form.get('payment_note', ''),
            'gst_included': IncludeGST,
            'products': product_data_for_sql_table,
            'event_id': event_id,
            'completed': 0,
        }

        # Save to database
        sales = Sales()
        if sales.data_base_connection_check():
            result = sales.add_invoice_detail(bill_data)
            print(result)
            if result['invoice_id']:

                if bill_data['completed'] == 0:
                    # Insert into live order track
                    response = sales.insert_live_order_track(
                        result['invoice_id'])

                    if not response['success']:
                        sales.close_connection()
                        return jsonify({'error': response['error']}), 500

            else:
                return jsonify({'error': result}), 500

            sales.close_connection()

            # Return success with invoice ID
            return jsonify({
                'success': True,
                'invoice_number': result['invoice_number'],
                'invoice_id' : result['invoice_id']
            }), 200
        else:
            return jsonify({'error': 'Database Error!'}), 500

    except Exception as e:
        print(f"Error saving invoice: {e}")
        import traceback
        print(traceback.print_exc())
        return jsonify({'error': str(e)}), 500


@sales_bp.route('/sales/download_invoice_pdf/<string:invoice_id>', methods=['GET'])
@sales_bp.route('/sales/share_invoice_pdf/<string:invoice_id>', methods=['POST'])
def generate_bill_pdf(invoice_id):
    """
    Second function - Generate PDF from database data using invoice_id
    """
    try:

        result = get_invoice_id(invoice_id)
        invoice_id = None
        if result['status']:
            invoice_id = result['invoice_id']
        else:
            return jsonify({'error': 'Invoice not found'}), 404

        from reportlab.lib.pagesizes import A4, inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
        from reportlab.lib import colors
        from reportlab.lib.units import inch
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from io import BytesIO
        import datetime

        def watermark(canvas, doc):
            width, height = A4

            canvas.saveState()

            # Low opacity
            canvas.setFillAlpha(0.5)

            # Font & color
            canvas.setFont("Helvetica-Bold", 130)
            canvas.setFillColor(colors.lightpink)

            # Center & rotate
            canvas.translate(width / 2, height / 2)
            canvas.rotate(30)

            # Draw text
            canvas.drawCentredString(0, 0, 'UNPAID')

            canvas.restoreState()

        # Get invoice data from database
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database connection failed'}), 500

        cursor = conn.cursor(dictionary=True)

        # Check invoice_number and invoice_id details
        cursor.execute("""
            SELECT invoice_id FROM `live_order_track` WHERE sales_proceed_for_packing = 1 AND cancel_order_status = 0 and invoice_id = %s;
        """, (invoice_id,))
        invoice_data = cursor.fetchone()
        
        if not invoice_data:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Invoice not found'}), 404

        # Get invoice details
        cursor.execute("""
            SELECT i.*, c.name as c_name, c.mobile as c_mobile, c.address as c_address, c.pincode as c_pincode, c.state as c_state, lot.payment_confirm_status, 
            t.pincode AS transport_pincode,
            t.name AS transport_name,
            t.city AS transport_city,
            t.days AS transport_days
            FROM invoices i 
            JOIN buddy c ON i.customer_id = c.id
            JOIN live_order_track lot ON i.id = lot.invoice_id
            LEFT JOIN transport t ON i.transport_id = t.id
            WHERE i.id = %s 
        """, (invoice_id,))

        invoice_data = cursor.fetchone()

        # Extract data from database
        customer = {
            'name': invoice_data.get('c_name',''),
            'mobile': invoice_data.get('c_mobile',''),
            'address': invoice_data.get('c_address',''),
            'pincode': invoice_data.get('c_pincode',''),
            'state': invoice_data.get('c_state','')
        }

        # Get invoice products
        cursor.execute("""
            SELECT ip.*, p.name as product_name 
            FROM invoice_items ip 
            JOIN products p ON ip.product_id = p.id 
            WHERE ip.invoice_id = %s
        """, (invoice_id,))

        products = cursor.fetchall()
        cursor.close()
        conn.close()

        # or however you store bill number
        bill_no = invoice_id
        delivery_mode = invoice_data['delivery_mode']
        transport_name = invoice_data['transport_name']
        transport_city = invoice_data['transport_city']
        transport_days = invoice_data['transport_days']
        transport_pincode = invoice_data['transport_pincode']
        payment_mode = invoice_data['payment_mode']
        paid_amount = float(invoice_data['paid_amount'])
        grand_total = float(invoice_data['grand_total'])
        IncludeGST = invoice_data['gst_included']
        payment_confirm_status = invoice_data['payment_confirm_status']

        # payment_type = invoice_data.get('payment_type', '')

        # Convert products to the format expected by PDF generation
        products_formatted = []
        for product in products:
            products_formatted.append({
                # 'id': product['product_id'],
                'name': product['product_name'],
                'quantity': product['quantity'],
                # 'unit': product.get('unit', 'PCS'),
                # Reconstruct original rate
                'og_price': product['price'],
                'tax_price': product['gst_tax_amount'],
                'total': product['total_amount'],
                'hsn_code': '95059090'
            })

        # Get invoice creation date
        formatted_time = invoice_data['created_at'].strftime("%d/%m/%Y %I:%M %p") if invoice_data.get(
            'created_at') else datetime.datetime.now().strftime("%d/%m/%Y %I:%M %p")

        # Generate PDF (rest of the PDF generation code remains the same)
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4,
                                leftMargin=30, rightMargin=30,
                                topMargin=10, bottomMargin=30)
        elements = []

        # Define styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CompanyTitle',
            parent=styles['Heading1'],
            fontSize=18,
            fontName='Helvetica-Bold',
            alignment=1,
            spaceAfter=0
        )

        subtitle_style = ParagraphStyle(
            'CompanyInfo',
            parent=styles['Normal'],
            fontSize=9,
            alignment=1,
            spaceAfter=0
        )

        normal_style = styles['Normal']

        # Prepare BILL TO and SHIP TO
        bill_to = Paragraph(
            f"<b>BILL TO:</b><br/><br/>{customer['name']}<br/><br/>Mobile: {customer['mobile']}",
            normal_style
        )

        ship_to = Paragraph(
            f"<b>SHIP TO: </b>{customer['name']}<br/>Address: {customer['address']}<br/>Pincode: {customer['pincode']}<br/>State: {customer['state']}",
            normal_style
        )

        # Invoice header
        invoice_header = [
            Paragraph(f"<b>Invoice No : {bill_no}</b>", normal_style),
            Paragraph(f"<b>Invoice Date : {formatted_time}</b>", normal_style)
        ]

        invoice_data_table = [
            invoice_header,
            [bill_to, ship_to],
        ]

        invoice_table = Table(invoice_data_table, colWidths=[
                              4 * inch, 4 * inch])
        invoice_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (1, 0), 'LEFT'),
            ('ALIGN', (0, 1), (1, 1), 'LEFT'),
            ('GRID', (0, 0), (1, 1), 0.5, colors.black),
            ('BACKGROUND', (0, 0), (1, 0), colors.lightgrey),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))

        # Product table
        headers = ["S.NO.", "ITEMS", "QTY.",
                   "RATE", f"TAX ({18 if IncludeGST == 1 else 0}%)", "AMOUNT"]
        col_widths = [0.5*inch, 3.8*inch, 0.9 *
                      inch, 0.8*inch, 1*inch, 1*inch, 1*inch]

        product_data = [headers]
        total_tax_amount = 0
        hsn_tax_summary = {}

        for idx, product in enumerate(products_formatted, 1):

            product_data.append([
                str(idx),
                product['name'],
                f"{product['quantity']} PCS",
                f"{product['og_price']}",
                f"{product['tax_price']}",
                f"{product['total']}"
            ])
            total_tax_amount += float(product['tax_price'])

        product_table = Table(product_data, colWidths=col_widths)
        product_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 5),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 1), (0, -1), 'CENTER'),
            ('ALIGN', (2, 1), (2, -1), 'CENTER'),
            ('ALIGN', (3, 1), (6, -1), 'RIGHT'),
        ]))

        # Total section
        if paid_amount == grand_total:
            total_data = [
                ["", "GRAND TOTAL", f"{sum(int(p['quantity']) for p in products_formatted)} PCS",
                 "", "", f"Rs {grand_total:.2f}"],
            ]

        elif paid_amount < grand_total:
            
            if payment_confirm_status == 1:
                
                total_data = [
                    ["", "GRAND TOTAL", f"{sum(int(p['quantity']) for p in products_formatted)} PCS",
                    "", "", f"Rs {grand_total:.2f}"],
                ]

            else:

                total_data = [
                    ["", "GRAND TOTAL", f"{sum(int(p['quantity']) for p in products_formatted)} PCS",
                    "", "", f"Rs {grand_total:.2f}"],
                    ["", "RECEIVED AMOUNT", "", "", "", f"Rs {paid_amount:.2f}"],
                    ["", "REMAINING AMOUNT", "", "", "",
                        f"Rs {(grand_total - paid_amount):.2f}"],
                ]

        total_table = Table(total_data, colWidths=[
                            0.5*inch, 3.8*inch, 0.9*inch, 0.8*inch, 1*inch, 1*inch, 1*inch])
        total_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('ALIGN', (2, 0), (2, 0), 'CENTER'),
        ]))

        # Tax summary table
        tax_summary_table = None
        if IncludeGST:
            tax_headers = ["HSN/SAC", "Taxable Value",
                           "CGST Amount", "SGST Amount", "Total Tax Amount"]
            tax_widths = [2*inch, 1.5*inch, 1.5*inch, 1.5*inch, 1.5*inch]

            tax_data = [tax_headers]
            # for hsn, values in hsn_tax_summary.items():
            #     taxable = values['taxable']
            #     tax = values['tax']
            half_tax = total_tax_amount / 2

            tax_data.append([
                "95059090",
                f"{grand_total - total_tax_amount}",
                f"{half_tax:0.2f} (9%)",
                f"{half_tax:0.2f} (9%)",
                f"Rs {total_tax_amount:.2f}"
            ])

            tax_summary_table = Table(tax_data, colWidths=tax_widths)
            tax_summary_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))

        def capitalize_each_word(line):
            words = line.split()
            result_words = []
            for word in words:
                parts = word.split('_')
                capitalized_parts = [part.capitalize() for part in parts]
                result_words.append(' '.join(capitalized_parts))
            return ' '.join(result_words)

        delivery_mode_table = [
            ["Delivery Mode", capitalize_each_word(delivery_mode)]
        ]

        delivery_mode_table = Table(delivery_mode_table, colWidths=[2.6*inch, 5.4*inch])
        delivery_mode_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            # Bold only the tag names column
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            # Normal font for values
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ]))


        if delivery_mode == "transport":
            info_data = [
                ["Transport Name", "City" , "Pincode", "Delivery"]
            ]
            info_data.append([transport_name,transport_city,transport_pincode,f"{transport_days} Days"])

            info_table = Table(info_data, colWidths=[3*inch, 3.4*inch,0.8*inch,0.8*inch])
            info_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ]))

        # Amount in words function
        def number_to_words(num):
            ones = ['', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine',
                    'Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen',
                    'Seventeen', 'Eighteen', 'Nineteen']
            tens = ['', '', 'Twenty', 'Thirty', 'Forty',
                    'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety']

            def two_digits(n):
                if n < 20:
                    return ones[n]
                return tens[n // 10] + (' ' + ones[n % 10] if n % 10 != 0 else '')

            def three_digits(n):
                if n < 100:
                    return two_digits(n)
                return ones[n // 100] + ' Hundred' + (' and ' + two_digits(n % 100) if n % 100 != 0 else '')

            result = ''
            if num >= 10000000:
                result += number_to_words(num // 10000000) + ' Crore'
                num %= 10000000
                if num:
                    result += ' '
            if num >= 100000:
                result += number_to_words(num // 100000) + ' Lakh'
                num %= 100000
                if num:
                    result += ' '
            if num >= 1000:
                result += number_to_words(num // 1000) + ' Thousand'
                num %= 1000
                if num:
                    result += ' '
            if num > 0:
                result += three_digits(num)

            return result or 'Zero'

        # Amount in words
        amount_words = number_to_words(int(grand_total)) + " Rupees"
        if grand_total % 1:
            paise = int((grand_total % 1) * 100)
            if paise:
                amount_words += f" and {number_to_words(paise)} Paise"

        words_data = [
            [f"Total Amount (in words):"],
            [amount_words]
        ]

        words_table = Table(words_data, colWidths=[8*inch])
        words_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, 0), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (0, 0), colors.black),
            ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (0, -1), 0.5, colors.black),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))

        # Terms and conditions
        terms_conditions = [
            "1. Goods once sold will not be taken back or exchanged",
            "2. No cancellation & No changes after confirm booking",
            "3. Your parcel will be dispatched within 3-4 working days",
            "4. packing & forwarding charges will be additional",
            "5. delivery charges not included in packing & forwarding charges",
            "6. Your complaint is only valid if you have a proper opening video of the parcel.\n   { from the seal pack parcel to the end without pause & cut }",
            "7. Your complaint is only valid for 2 days after you receive .",
            "8. Our Complain Number - 9638095151 ( Do message us on WhatsApp only )"
        ]

        terms_data = [
            ["Terms and Conditions"],
            ["\n".join(terms_conditions)]
        ]

        terms_table = Table(terms_data, colWidths=[8*inch])
        terms_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, 0), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (0, 0), colors.black),
            ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (0, -1), 0.5, colors.black),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))

        # Build PDF elements
        elements.append(Paragraph("SMART TRADERS", title_style))
        elements.append(Paragraph(
            "Ahmedabad, Gujarat, 382330, Ahmedabad, Gujarat, 382330", subtitle_style))
        elements.append(
            Paragraph("GSTIN: 24DCFPS1329A1Z1 Mobile: 9316876474", subtitle_style))
        elements.append(Spacer(1, 10))

        elements.append(invoice_table)
        elements.append(Spacer(1, 10))
        elements.append(product_table)
        elements.append(total_table)
        elements.append(Spacer(1, 10))
        elements.append(delivery_mode_table)
        if delivery_mode == "transport":
            elements.append(info_table)
        elements.append(Spacer(1, 10))

        if tax_summary_table:
            elements.append(tax_summary_table)
            elements.append(Spacer(1, 10))

        elements.append(words_table)
        elements.append(Spacer(1, 10))
        elements.append(terms_table)
        elements.append(Spacer(1, 10))

        elements.append(Paragraph("TAX INVOICE ORIGINAL FOR RECIPIENT",
                                  ParagraphStyle('Footer',
                                                 parent=normal_style,
                                                 alignment=1,
                                                 fontName='Helvetica-Bold')))

        # Build PDF
        doc.title = f"{customer['name']}"
        doc.build(elements)
        buffer.seek(0)

        # Return PDF file
        return send_file(
            buffer,
            as_attachment=False,
            download_name=f"{customer['name']}_{bill_no}.pdf",
            mimetype='application/pdf'
        )

    except Exception as e:
        import traceback
        print(f"Error generating PDF: {traceback.print_exc()}")
        return jsonify({'error': 'Invoice Not Found!'}), 500


# -------------------------------------------------------------- My Orders -----------------------------------------------------------------------------------------------


class MyOrders:
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

    def fetch_my_orders(self, user_id):
        query = f"""
            SELECT 

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
                b.id AS buddy_id, 
                b.name AS customer,
                b.address,
                b.state,
                b.pincode,
                b.mobile,
                
                u.id AS users_id,
                u.username,

                up.username AS pu_name, 

                ut.username AS tu_name, 

                ub.username AS bu_name, 

                upay.username AS payu_name,

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
                lot.payment_date_time,
                lot.cancel_order_status,
                lot.verify_by_manager,
                lot.verify_by_manager_id,
                lot.verify_manager_date_time,
                transport.pincode AS transport_pincode,
                transport.name AS transport_name,
                transport.city AS transport_city,
                transport.days AS transport_days
            
            FROM invoices inv
            LEFT JOIN buddy b ON inv.customer_id = b.id
            LEFT JOIN invoice_items ii ON inv.id = ii.invoice_id
            LEFT JOIN products p ON ii.product_id = p.id
            LEFT JOIN live_order_track lot ON inv.id = lot.invoice_id
            LEFT JOIN transport ON inv.transport_id = transport.id
            
            LEFT JOIN users u ON inv.invoice_created_by_user_id = u.id 
            LEFT JOIN users up ON lot.packing_proceed_by = up.id 
            LEFT JOIN users ut ON lot.transport_proceed_by = ut.id 
            LEFT JOIN users ub ON lot.builty_proceed_by = ub.id 
            LEFT JOIN users upay ON lot.payment_verify_by = upay.id 

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

        # Merge products into orders
        merged_orders = self.merge_orders_products(all_order_data)

        return merged_orders

    def fetch_ready_to_go_orders(self, user_id):
        query = f"""
            SELECT 

                inv.id,

                inv.invoice_number,

                inv.grand_total,

                inv.payment_mode,

                inv.paid_amount,

                inv.left_to_paid,

                inv.sales_note,

                inv.payment_note,

                inv.gst_included,

                inv.created_at,

                inv.delivery_mode,
            
                b.name AS customer,

                b.address,

                b.state,

                b.pincode,

                b.mobile,
            
                ii.quantity,

                ii.price,

                ii.gst_tax_amount,

                ii.total_amount,
            
                p.name,

                lot.sales_proceed_for_packing,

                transport.pincode AS transport_pincode,
                transport.name AS transport_name,
                transport.city AS transport_city,
                transport.days AS transport_days
                
            
            FROM invoices inv
            LEFT JOIN buddy b ON inv.customer_id = b.id
            LEFT JOIN users u ON inv.invoice_created_by_user_id = u.id
            LEFT JOIN invoice_items ii ON inv.id = ii.invoice_id
            LEFT JOIN products p ON ii.product_id = p.id
            LEFT JOIN live_order_track lot ON inv.id = lot.invoice_id
            LEFT JOIN transport ON inv.transport_id = transport.id

            WHERE inv.invoice_created_by_user_id = %s
            AND lot.cancel_order_status = 0
            AND lot.sales_proceed_for_packing = 0
            AND inv.completed = 0   
            ORDER BY inv.created_at DESC; 
 
        """

        self.cursor.execute(query, (user_id,))
        all_order_data = self.cursor.fetchall()

        if not all_order_data:
            return []

        # Merge products into orders
        merged_orders = self.merge_orders_products(all_order_data)

        return merged_orders

    def delete_invoice(self, invoice_id):
        try:
            query = """
                DELETE FROM invoices
                WHERE id = %s;
            """
            self.cursor.execute(query, (invoice_id,))
            self.conn.commit()  # commit on connection, not cursor
            if self.cursor.rowcount == 0:
                return {"success": False, "message": f"No invoice found with ID"}
            else:
                return {"success": True, "message": f"Invoice successfully deleted"}
        except Exception as e:
            self.conn.rollback()  # rollback on connection, not cursor
            return {"success": False, "message": f"Error deleting invoice {invoice_id}: {e}"}

    def cancel_order(self, invoice_id, data):
        try:
            update_query = """

            UPDATE live_order_track
            SET cancel_order_status = 1
            WHERE invoice_id = %s;
            """
            self.cursor.execute(update_query, (invoice_id,))

            update_query = """

            UPDATE invoices
            SET cancel_order_status = 1
            WHERE id = %s;
            """
            self.cursor.execute(update_query, (invoice_id,))
            
            lot_id_querry = """
            SELECT id from live_order_track WHERE invoice_id = %s;
            """
            self.cursor.execute(lot_id_querry, (invoice_id,))
            lot_id = self.cursor.fetchone()
                
            insert_query = """
                
                INSERT INTO cancelled_orders (
                    invoice_id,cancelled_by, reason,live_order_track_id 
                ) VALUES (%s, %s, %s,%s)
            """

            self.cursor.execute(insert_query, (invoice_id, session.get('user_id'), data.get('reason'), lot_id.get('id'),))
            
            self.conn.commit()  # commit on connection, not cursor

            return {"success": True, "message": f"Order successfully Cancel"}

        except Exception as e:
            self.conn.rollback()  # rollback on connection, not cursor
            return {"success": False, "message": f"Somthing went wrong to cancel order"}

    def start_shipment(self, invoiceNumber):
        try:

            # Get live_order_track_id using invoiceNumber
            select_query = """

                SELECT
                    lot.id,
                    i.delivery_mode,
                    i.left_to_paid,
                    i.payment_mode
                FROM
                    live_order_track AS lot
                JOIN
                    invoices AS i ON i.id = lot.invoice_id
                WHERE
                    i.invoice_number = %s;

            """
            self.cursor.execute(select_query, (invoiceNumber,))
            result = self.cursor.fetchone()
            live_order_track_id = result['id'] if result else None
            delivery_mode = result['delivery_mode'] if result else None
            payment_mode = result['payment_mode'] if result else None
            left_to_paid = int(result['left_to_paid']) if result else None
            user_id = session.get('user_id')
            
            if delivery_mode in ("transport", "post"):
                update_query = """
                    UPDATE live_order_track
                    SET sales_proceed_for_packing = 1,
                        sales_date_time = NOW()
                    WHERE id = %s;
                """
                self.cursor.execute(update_query, (live_order_track_id,))
                self.conn.commit()

            else:
                payment_verify_by = user_id if left_to_paid == 0 else None
                payment_date_time = "NOW()" if left_to_paid == 0 else None
                payment_confirm_status = 1 if left_to_paid == 0 else 0
                left_to_paid_mode = payment_mode if left_to_paid == 0 else "not_paid"

                # Construct query with placeholders
                update_query = """
                    UPDATE live_order_track
                    SET 
                        sales_proceed_for_packing = 1,
                        sales_date_time = NOW(),
                        packing_proceed_for_transport = 1, 
                        packing_date_time = NOW(),
                        packing_proceed_by = %s,
                        transport_proceed_for_builty = 1,
                        transport_date_time = NOW(),
                        transport_proceed_by = %s,
                        builty_proceed_by = %s,
                        builty_received = 1,
                        builty_date_time = NOW(),
                        payment_verify_by = %s,
                        payment_date_time = {payment_date_time},
                        payment_confirm_status = %s,
                        left_to_paid_mode = %s
                    WHERE id = %s;
                """.format(payment_date_time=payment_date_time if payment_date_time else "NULL")

                self.cursor.execute(update_query, (
                    user_id, user_id, user_id,
                    payment_verify_by,
                    payment_confirm_status,
                    left_to_paid_mode,
                    live_order_track_id
                ))
                self.conn.commit()

            
            return {"success": True, "message": "Order successfully shipped"}

        except Exception as e:
            self.conn.rollback()
            print(f"Error while shipping order: {e}")
            return {"success": False, "message": f"Something went wrong while shipping order: {str(e)}"}

    def close(self):
        self.cursor.close()
        self.conn.close()


@sales_bp.route('/sales/cancel_order', methods=['POST'])
@login_required('Sales')
def cancel_order():
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

        for_cancel_order = MyOrders()
        response = for_cancel_order.cancel_order(
            invoice_id, data)

        if response.get('success'):
            return jsonify({"success": True, "message": "Order Cancelled Successfully"}), 200

        return {"success": False, "message": f"Somthing went wrong to cancel order"}, 500

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

        return jsonify({"success": False, "message": str(e)}), 500

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

        return jsonify({'success': False, 'message': 'Shipment Failed: Something Went Wrong!'}), 500

    except Exception as e:
        return jsonify({'success': False, 'message': 'Shipment Failed: Something Went Wrong!'}), 500


@sales_bp.route('/sales/my-ready-to-go-orders-list', methods=['GET'])
@login_required('Sales')
def sales_my_ready_to_go_orders_list():

    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = conn.cursor(dictionary=True)
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not logged in'}), 401
        my_orders = MyOrders()
        orders = my_orders.fetch_ready_to_go_orders(
            user_id)  # 0 for ready to go orders
        my_orders.close()
        if not orders:
            return jsonify([]), 200
        # Format the orders for JSON response

        return jsonify(orders)

    except Exception as e:
        print(f"Error fetching orders: {e}")
        return jsonify({'error': 'Failed to fetch orders'}), 500

    finally:
        cursor.close()
        conn.close()


# -------------------------------------------------------------- Canceled Orders -----------------------------------------------------------------------------------------------

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

        # Merge products into orders
        merged_orders = self.merge_orders_products(all_order_data)

        return merged_orders

    def confirm_canceled_order(self, id):

        query = """
                UPDATE cancelled_orders
                SET confirm_by_saler = 1,confirm_at = NOW()
                WHERE id = %s;
        """
        try:

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

    def verify_invoice_for_edit(self, invoice_id):

        query = "SELECT sales_proceed_for_packing FROM live_order_track WHERE invoice_id = %s"
        self.cursor.execute(query, (invoice_id,))
        invoice = self.cursor.fetchone()

        if not invoice:
            raise Exception("Invoice not found")

        if invoice['sales_proceed_for_packing'] == 0:
            return {'success': True, 'message': 'Invoice can be edited'}

        return {'success': False, 'message': 'Invoice cannot be edited'}

    def get_invoice(self, invoice_id):

        query = """
                SELECT invoices.id,buddy.mobile as c_mobile,buddy.address as c_address,buddy.name as c_name,buddy.pincode as c_pincode, invoices.grand_total,
                invoices.payment_mode, invoices.paid_amount, invoices.transport_id,
                invoices.sales_note, invoices.payment_note, invoices.gst_included, 
                invoices.delivery_mode, invoices.event_id, ip.id, ip.product_id,t.name as t_name,
                t.pincode as t_pincode, t.city as t_city , t.days as t_days,

                ip.quantity, ip.total_amount, p.name as product_name 
                FROM invoice_items ip 
                JOIN products p ON ip.product_id = p.id 
                JOIN invoices ON invoices.id = ip.invoice_id
                JOIN buddy ON invoices.customer_id = buddy.id
                LEFT JOIN transport t ON invoices.transport_id = t.id
                WHERE ip.invoice_id = %s;
        """

        self.cursor.execute(query, (invoice_id,))
        invoice_data = self.cursor.fetchall()

        # Extract common fields
        common_keys = ['c_mobile','c_address','c_name','c_pincode' ,'grand_total', 'payment_mode', 'paid_amount', 'transport_id',
                       't_name','t_pincode', 't_city' , 't_days' ,
                       'sales_note', 'payment_note', 'gst_included', 'delivery_mode', 'event_id']

        # Build the unified dict with Decimal -> float conversion
        unified_dict = {
            key: float(invoice_data[0][key]) if isinstance(
                invoice_data[0][key], Decimal) else invoice_data[0][key]
            for key in common_keys
        }

        # Create products list with basePrice and without total_amount
        unified_dict['products'] = []
        for item in invoice_data:
            quantity = item['quantity']
            total_amount = float(item['total_amount']) if isinstance(
                item['total_amount'], Decimal) else item['total_amount']
            base_price = total_amount / quantity if quantity else 0

            product = {
                'id': item['id'],
                'product_id': item['product_id'],
                'product_name': item['product_name'],
                'quantity': quantity,
                'basePrice': base_price
            }

            unified_dict['products'].append(product)

        return unified_dict

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

            # Step 2: Fetch & delete old invoice items
            cursor.execute("SELECT id FROM invoice_items WHERE invoice_id = %s;", (invoice_id,))
            all_old_items_ids = cursor.fetchall()

            for (item_id,) in all_old_items_ids:
                cursor.execute("DELETE FROM invoice_items WHERE id = %s;", (item_id,))

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

            # Step 4: Final commit
            self.conn.commit()
            return {"status": True, 'msg': "All Things Are Done!"}
        

        except mysql.connector.Error as e:
            self.conn.rollback()
            return {"status": False, 'error': str(e)}

    def close(self):
        self.cursor.close()
        self.conn.close()


@sales_bp.route('/sales/edit-invoice/<invoice_number>', methods=['GET'])
@login_required('Sales')
def edit_invoice(invoice_number):
    """
    Edit an existing invoice.
    """
    try:
        
        # invoice_id = int(invoice_number[10:])
        result = get_invoice_id(invoice_number)
        invoice_id = None
        if result['status']:
            invoice_id = result['invoice_id']
        else:
            return render_template('dashboards/sales/ready_to_go.html'), 200
        
        my_obj = EditBill()
        response = my_obj.verify_invoice_for_edit(invoice_id)

        if not response['success']:
            return jsonify({'success': False, 'message': response['message']}), 400

        invoice_data = my_obj.get_invoice(invoice_id)
        invoice_data['id'] = invoice_number

        if invoice_data['grand_total'] == invoice_data['paid_amount']:
            invoice_data['payment_type'] = 'full_payment'
        else:
            invoice_data['payment_type'] = 'half_payment'

        my_obj.close()

        return render_template('dashboards/sales/edit_invoice.html', data=invoice_data), 200

    except Exception as e:
        return render_template('dashboards/sales/sell.html'), 200


@sales_bp.route('/sales/update_invoice', methods=['POST'])
def update_invoice_into_database():
    """ Save invoice data to database """
    try:

        # Get form data
        customer_id = request.form.get('customerId')
        delivery_mode = request.form.get('delivery_mode')
        transport_id = request.form.get('transport_id',None)
        payment_mode = request.form.get('payment_mode')
        payment_type = request.form.get('payment_type')
        paid_amount = float(request.form.get('paid_amount', 0))
        grand_total = float(request.form.get('grand_total', 0))
        sales_note = request.form.get('sales_note', '')
        IncludeGST = request.form.get('IncludeGST', 'off')
        event_id = request.form.get('event_id', None)
        invoice_number = request.form.get('invoice_number')

        if not invoice_number or invoice_number == "":
            return jsonify({'error': 'Somthing is Missing in the bill'}), 400
        
        result = get_invoice_id(invoice_number)
        invoice_id = None
        if result['status']:
            invoice_id = result['invoice_id']
        else:
            return jsonify({'error': 'Invoice not found'}), 404

        if payment_mode == "not_paid":
            paid_amount = 0

        # Get products from form data
        products = request.form.get('products')
        if products or customer_id:
            products = json.loads(products)
        else:
            return jsonify({'error': 'Some data is Missing in the bill'}), 400

        # Need transport_id
        if delivery_mode == 'transport':
            if not transport_id:
                return jsonify({'error': 'Some data is Missing in the bill'}), 400

        # Get customer details to validate
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database connection failed'}), 500

        if not customer_id or customer_id == "": 
            return jsonify({'error': 'Invalid mobile number'}), 500

        cursor = conn.cursor(dictionary=True)
        cursor.execute(f"SELECT id FROM buddy WHERE mobile = CAST({customer_id} AS INT)")
        customer = cursor.fetchone()
        conn.close()

        if not customer:
            return jsonify({'error': 'Customer not found'}), 404

        # Process products for database
        tax_rate = 0
        if IncludeGST == 'on':
            tax_rate = 18

        product_data_for_sql_table = []
        for product in products:
            qty = product['quantity']
            rate = float(product['finalPrice'])

            # Calculate the original amount (before GST)
            original_amount = rate / (1 + tax_rate / 100)
            # Calculate the GST amount
            gst_amount = rate - original_amount
            tax_amount = float(f"{gst_amount:.2f}")
            total_amount = float(product['total'])

            product_data_for_sql_table.append([
                product['id'],
                f"{qty}",
                f"{original_amount:.2f}",
                f"{tax_amount:.2f}",
                f"{total_amount:.0f}"
            ])

        # Prepare bill data for database
        bill_data = {
            'invoice_id': invoice_id,
            'customer_id': customer['id'],
            'delivery_mode': delivery_mode,
            'grand_total': grand_total,
            'payment_mode': payment_mode,
            'paid_amount': paid_amount,
            'transport_id': transport_id,
            'sales_note': sales_note,
            'invoice_created_by_user_id': session.get('user_id'),
            'payment_note': request.form.get('payment_note', ''),
            'gst_included': IncludeGST,
            'products': product_data_for_sql_table,
            'event_id': event_id,
            'completed': 0,
        }

        # Save to database
        update = EditBill()

        if update:
            result = update.update_invoice_detail(bill_data)
            print(result)
            if result['status']:
                # Return success with invoice ID
                return jsonify({
                    'success': True,
                    'invoice_number': invoice_number
                }), 200
            
            else:
                # Return success with invoice ID
                return jsonify({
                    'success': False,
                    'invoice_number': invoice_number
                }), 200


        # if result['invoice_id']:

            # if bill_data['completed'] == 0:
            #     # Insert into live order track
            #     response = sales.insert_live_order_track(result['invoice_id'])

            #     if response['success']:
            #         # Successfully inserted into live order track
            #         print(
            #             f"Live order track inserted for invoice ID: {result['invoice_id']}")
            #     else:
            #         # If there was an error inserting into live order track
            #         print(
            #             f"Error inserting live order track: {response['error']}")
            #         sales.close_connection()
            #         return jsonify({'error': response['error']}), 500

        # else:
            # return jsonify({'error': result}), 500

        update.close()

        # Return success with invoice ID
        return jsonify({
            'success': True,
            'invoice_number': invoice_number
        }), 200

    except Exception as e:
        print(f"Error saving invoice: {e}")
        return jsonify({'error': str(e)}), 500
    
