from flask import Blueprint, render_template, jsonify, request, session, send_file
from utils import get_db_connection, login_required, encrypt_password, decrypt_password
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


ist = pytz.timezone('Asia/Kolkata')
now_ist = datetime.now(ist)
formatted_time = now_ist.strftime("%d-%m-%Y %H:%M")


# Create a Blueprint for manager routes
sales_bp = Blueprint('sales', __name__)


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

    def insert_live_order_track(self, invoice_id,payment_confirm_status):
        """
        Insert a saved invoice into the database live order track table.
        """
        if not self.data_base_connection_check():
            return {'error': 'Database Error!'}

        cursor = self.conn.cursor()

        try:
            # Prepare the SQL query to insert the invoice data
            insert_query = """
                INSERT INTO live_order_track (invoice_id,payment_confirm_status)
                VALUES (%s,%s)
            """

            # Extract values from the invoice_data dictionary
            values = (
                invoice_id,
                payment_confirm_status,
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
                    payment_mode, payment_note, sales_note, transport_company_name,
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
                invoice_data['transport_company_name'],
                invoice_number,
                invoice_data['event_id'] if invoice_data.get('event_id') else None,
                invoice_data.get('completed', 0)  # Default to 0 if not provided
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


@sales_bp.route('/sales/add-customer', methods=['POST'])
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
            return jsonify({'error': 'Database connection failed'}), 500

        cursor = conn.cursor()

        # Insert new product into database
        cursor.execute("INSERT INTO buddy (name, address, state, pincode, mobile,created_by) VALUES (%s, %s, %s, %s, %s,%s)",
                       (name, address, state, pincode, mobile,session.get('user_id')))
        conn.commit()
        cursor.close()
        conn.close()


        # print(f"New customer added with ID: {customer_id}")

        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500


@sales_bp.route('/sales/products')
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


@sales_bp.route('/sales/check-bill-number/<bill_no>')
@login_required('Sales')
def check_bill_number(bill_no):
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = conn.cursor(dictionary=True)
    try:
        # Check if bill number exists in the sales table
        cursor.execute(
            "SELECT COUNT(*) as count FROM sales WHERE bill_no = %s", (bill_no,))
        result = cursor.fetchone()

        return jsonify({
            'exists': result['count'] > 0
        })
    except Exception as e:
        print(f"Error checking bill number: {e}")
        return jsonify({'error': 'Failed to check bill number'}), 500
    finally:
        cursor.close()
        conn.close()


@sales_bp.route('/sales/add_new_product', methods=['POST'])
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
        customer_id = request.form.get('customer_id')
        delivery_mode = request.form.get('delivery_mode')
        transport_company = request.form.get('transport_company')
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

        # Need transport_company name
        if delivery_mode == 'transport':
            if not transport_company:
                return jsonify({'error': 'Some data is Missing in the bill'}), 400

        # Get customer details to validate
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database connection failed'}), 500

        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM buddy WHERE id = %s", (customer_id,))
        customer = cursor.fetchone()
        cursor.close()
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
            'customer_id': customer_id,
            'delivery_mode': delivery_mode,
            'grand_total': grand_total,
            'payment_mode': payment_mode,
            'paid_amount': paid_amount,
            'transport_company_name': transport_company,
            'sales_note': sales_note,
            'invoice_created_by_user_id': session.get('user_id'),
            'payment_note': request.form.get('payment_note', ''),
            'gst_included': IncludeGST,
            'products': product_data_for_sql_table,
            'event_id': event_id,
            'completed' : 1 if (delivery_mode == "at_store" or delivery_mode == "porter") and (payment_type == "full_payment") else 0,
        }

        # Save to database
        sales = Sales()
        if sales.data_base_connection_check():
            result = sales.add_invoice_detail(bill_data)
            print(result)

            if result['invoice_id']:

                payment_confirm_status = 0
                
                if grand_total == paid_amount:
                    payment_confirm_status = 1

                if bill_data['completed'] == 0:
                    # Insert into live order track
                    response = sales.insert_live_order_track(result['invoice_id'],payment_confirm_status)

                    if response['success']:
                        # Successfully inserted into live order track
                        print(
                            f"Live order track inserted for invoice ID: {result['invoice_id']}")
                    else:
                        # If there was an error inserting into live order track
                        print(
                            f"Error inserting live order track: {response['error']}")
                        sales.close_connection()
                        return jsonify({'error': response['error']}), 500


            else:
                return jsonify({'error': result}), 500

            sales.close_connection()

            # Return success with invoice ID
            return jsonify({
                'success': True,
                'invoice_id': result['invoice_id'],
                'invoice_number': result['invoice_number']
            }), 200
        else:
            return jsonify({'error': 'Database Error!'}), 500

    except Exception as e:
        print(f"Error saving invoice: {e}")
        return jsonify({'error': str(e)}), 500


@sales_bp.route('/sales/download_invoice_pdf/<string:invoice_id>', methods=['GET'])
@sales_bp.route('/sales/share_invoice_pdf/<string:invoice_id>', methods=['POST'])
def generate_bill_pdf(invoice_id):
    """
    Second function - Generate PDF from database data using invoice_id
    """
    try:

        invoice_number = invoice_id[:10]
        invoice_id = int(invoice_id[10:])

        from reportlab.lib.pagesizes import A4, inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from io import BytesIO
        import datetime

        # Get invoice data from database
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database connection failed'}), 500

        cursor = conn.cursor(dictionary=True)

        # Check invoice_number and invoice_id details
        cursor.execute("""
            SELECT invoice_number
            FROM invoices
            WHERE id = %s;
        """, (invoice_id,))
        invoice_data = cursor.fetchone()

        if invoice_data['invoice_number'] != invoice_number:
            return jsonify({'error': 'Invoice not found'}), 404

        # Get invoice details
        cursor.execute("""
            SELECT i.*, c.name, c.mobile, c.address, c.pincode, c.state 
            FROM invoices i 
            JOIN buddy c ON i.customer_id = c.id 
            WHERE i.id = %s
        """, (invoice_id,))

        invoice_data = cursor.fetchone()
        if not invoice_data:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Invoice not found'}), 404

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

        # Extract data from database
        customer = {
            'name': invoice_data['name'],
            'mobile': invoice_data['mobile'],
            'address': invoice_data['address'],
            'pincode': invoice_data['pincode'],
            'state': invoice_data['state']
        }

        # or however you store bill number
        bill_no = invoice_data['invoice_number'] + str(invoice_data['id'])
        delivery_mode = invoice_data['delivery_mode']
        transport_company = invoice_data['transport_company_name']
        payment_mode = invoice_data['payment_mode']
        paid_amount = float(invoice_data['paid_amount'])
        grand_total = float(invoice_data['grand_total'])
        IncludeGST = invoice_data['gst_included']

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
        elif paid_amount == 0:
            total_data = [
                ["", "GRAND TOTAL Not Paid", f"{sum(int(p['quantity']) for p in products_formatted)} PCS",
                 "", "", f"Rs {grand_total:.2f}"],
            ]
        elif paid_amount < grand_total:
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

        info_data = [
            ["Payment Mode", capitalize_each_word(payment_mode)],
            ["Delivery Mode", capitalize_each_word(delivery_mode)]
        ]

        if delivery_mode == "transport":
            info_data.append(["Transport Company", transport_company])

        info_table = Table(info_data, colWidths=[2*inch, 6*inch])
        info_table.setStyle(TableStyle([
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
        # elements.append(info_table)
        # elements.append(Spacer(1, 10))

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
        print(f"Error generating PDF: {e}")
        return jsonify({'error': 'Invoice Not Found!'}), 500


# -------------------------------------------------------------- My Orders -----------------------------------------------------------------------------------------------


class MyOrders:
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

            # passed tracking status with date            
            trackingStatus = 0
            trackingDates = []

            if item['sales_proceed_for_packing']:

                if item['sales_date_time']:
                    trackingDates.append(item['sales_date_time'].strftime("%d/%m/%Y %I:%M %p"))
                else:
                    trackingDates.append('')
                trackingStatus = 1                
            
                if item['packing_proceed_for_transport']:
                    
                    if item['packing_proceed_for_transport']:
                        trackingDates.append(item['packing_date_time'].strftime("%d/%m/%Y %I:%M %p"))
                    else:
                        trackingDates.append('')
                    trackingStatus = 2                
                
                    if item['transport_proceed_for_builty']:
                        
                        if item['transport_proceed_for_builty']:
                            trackingDates.append(item['transport_date_time'].strftime("%d/%m/%Y %I:%M %p"))
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

    def fetch_my_orders(self, user_id,start_shipment):
        query = f"""
            SELECT 

                inv.id,

                inv.invoice_number,

                inv.customer_id,

                inv.grand_total,

                inv.payment_mode,

                inv.paid_amount,

                inv.left_to_paid,

                inv.transport_company_name,

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

                lot.verify_manager_date_time
            
            FROM invoices inv

            LEFT JOIN buddy b ON inv.customer_id = b.id

            LEFT JOIN users u ON inv.invoice_created_by_user_id = u.id

            LEFT JOIN invoice_items ii ON inv.id = ii.invoice_id

            LEFT JOIN products p ON ii.product_id = p.id

            LEFT JOIN live_order_track lot ON inv.id = lot.invoice_id

                AND lot.cancel_order_status = 0

                AND lot.sales_proceed_for_packing = {start_shipment}

                AND (

                    lot.packing_proceed_for_transport = 0 

                    OR lot.transport_proceed_for_builty = 0 

                    OR lot.builty_received = 0 

                    OR lot.payment_confirm_status = 0 

                    OR lot.verify_by_manager = 0

                )

            WHERE inv.invoice_created_by_user_id = %s

            AND (

                inv.completed = 1

                OR (inv.completed = 0 AND lot.invoice_id IS NOT NULL)

            )

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

                inv.customer_id,

                inv.grand_total,

                inv.payment_mode,

                inv.paid_amount,

                inv.left_to_paid,

                inv.transport_company_name,

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

                lot.verify_manager_date_time
            
            FROM invoices inv

            LEFT JOIN buddy b ON inv.customer_id = b.id

            LEFT JOIN users u ON inv.invoice_created_by_user_id = u.id

            LEFT JOIN invoice_items ii ON inv.id = ii.invoice_id

            LEFT JOIN products p ON ii.product_id = p.id

            LEFT JOIN live_order_track lot ON inv.id = lot.invoice_id

            WHERE inv.invoice_created_by_user_id = %s

            AND inv.completed = 0

            AND lot.cancel_order_status = 0

            AND lot.sales_proceed_for_packing = 0

            
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

    def cancel_order(self, invoice_id,data):
        try:
            update_query = """

            UPDATE live_order_track
            SET cancel_order_status = 1
            WHERE id = %s;
            """
            self.cursor.execute(update_query, (data.get('track_order_id'),))
            self.conn.commit()  # commit on connection, not cursor
            
            insert_query = """
                
                INSERT INTO cancelled_orders (
                    invoice_id,cancelled_by, reason,live_order_track_id 
                ) VALUES (%s, %s, %s,%s)
            """

            self.cursor.execute(insert_query, (invoice_id,session.get('user_id'),data.get('reason'),data.get('track_order_id'),))
            self.conn.commit()  # commit on connection, not cursor
            
            return {"success": True, "message": f"Order successfully Cancel"}
            
        except Exception as e:
            self.conn.rollback()  # rollback on connection, not cursor
            return {"success": False, "message": f"Somthing went wrong to cancel order"}

    def start_shipment(self, live_order_track_id):
        try:
            update_query = """
            UPDATE live_order_track
            SET sales_proceed_for_packing = 1,
                sales_date_time = NOW()
            WHERE id = %s;
            """
            self.cursor.execute(update_query, (live_order_track_id,))
            self.conn.commit()

            return {"success": True, "message": "Order successfully shipped"}

        except Exception as e:
            self.conn.rollback()
            return {"success": False, "message": f"Something went wrong while shipping order: {str(e)}"}

    def close(self):
        self.cursor.close()
        self.conn.close()

@sales_bp.route('/sales/cancel_order' ,methods=['POST'])     
@login_required('Sales')
def cancel_order():
    try:
        data = request.get_json()
        track_order_id = data.get('track_order_id')

        if not track_order_id or not str(track_order_id).isdigit():
            return jsonify({"success": False, "message": "Invalid track_order_id"}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({"success": False, "message": 'Database connection failed'}), 500

        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT invoice_id
            FROM live_order_track
            WHERE id = %s;
        """, (track_order_id,))
        invoice_data = cursor.fetchone()
        
        if invoice_data is None:
            return jsonify({"success": False, "message": "Order not found"}), 404

        for_cancel_order = MyOrders()
        response = for_cancel_order.cancel_order(invoice_data['invoice_id'],data)

        if response.get('success'):
            return jsonify({"success": True, "message": "Order Cancelled Successfully"}), 200
        
        return {"success": False, "message": f"Somthing went wrong to cancel order"},500

    except Exception as e:
        return jsonify({"success": False, "message": "Internal server error"}), 500

@sales_bp.route('/sales/delete_invoice/<string:invoice_id>' ,methods=['DELETE'])     
@login_required('Sales')
def delete_invoice(invoice_id):
    try:
        invoice_number = invoice_id[:10]
        invoice_id = int(invoice_id[10:])

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
            return jsonify({"success": False, "message":"Sorry, there was an issue. We are looking into it."}), 404
        
        for_delete_invoice = MyOrders()
        response = for_delete_invoice.delete_invoice(invoice_id)
        
        if response['success']:
            return jsonify({"success": True, "message": 'Invoice successfully deleted!'}),200

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
        orders = my_orders.fetch_my_orders(user_id,1)
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

@sales_bp.route('/start-shipment', methods=['POST'])
@login_required('Sales')
def start_shipment():
    
    try:
        data = request.get_json()
        live_order_track_id = data.get('live_order_track_id')

        if not live_order_track_id:
            return jsonify({'error': 'Missing Order ID'}), 400

        shipment_start = MyOrders()
        response = shipment_start.start_shipment(live_order_track_id)

        if response['success']:
            return jsonify({"success": True, "message": 'Order Successfully Shiped!'}),200

        return jsonify({'success': False, 'message': 'Shipment Fails Somthing Went Wrong!'}),500

    except Exception as e:
        return jsonify({'success': False, 'message': 'Shipment Fails Somthing Went Wrong!'})
    
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
        orders = my_orders.fetch_ready_to_go_orders(user_id)  # 0 for ready to go orders
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

    def merge_orders_products(self,data):

        merged = {}

        for item in data:

            # change created_at date formate 
            item['created_at'] = item['created_at'].strftime("%d/%m/%Y %I:%M %p") 

            # passed tracking status with date            
            trackingStatus = 0
            trackingDates = []

            if item['sales_proceed_for_packing']:

                if item['sales_date_time']:
                    trackingDates.append(item['sales_date_time'].strftime("%d/%m/%Y %I:%M %p"))
                else:
                    trackingDates.append('')
                trackingStatus = 1                
            
                if item['packing_proceed_for_transport']:
                    
                    if item['packing_proceed_for_transport']:
                        trackingDates.append(item['packing_date_time'].strftime("%d/%m/%Y %I:%M %p"))
                    else:
                        trackingDates.append('')
                    trackingStatus = 2                
                
                    if item['transport_proceed_for_builty']:
                        
                        if item['transport_proceed_for_builty']:
                            trackingDates.append(item['transport_date_time'].strftime("%d/%m/%Y %I:%M %p"))
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
            item['cancelled_at'] = item['cancelled_at'].strftime("%d/%m/%Y %I:%M %p")


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
                inv.transport_company_name,
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

                -- cancelled_orders columns
                c.id AS cancelled_orders_id,
                c.cancelled_at,
                c.reason AS cancelled_reason,
                c.confirm_at


            FROM invoices inv
            LEFT JOIN buddy b ON inv.customer_id = b.id
            LEFT JOIN invoice_items ii ON inv.id = ii.invoice_id
            LEFT JOIN products p ON ii.product_id = p.id
            LEFT JOIN live_order_track lot ON inv.id = lot.invoice_id
            LEFT JOIN cancelled_orders c ON inv.id = c.invoice_id
            LEFT JOIN users u ON c.cancelled_by = u.id
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
            ORDER BY inv.created_at DESC

        """
        self.cursor.execute(query, (user_id,))
        all_order_data = self.cursor.fetchall()
        
        if not all_order_data:
            return []

    
        # Merge products into orders
        merged_orders = self.merge_orders_products(all_order_data)

        return merged_orders

    def confirm_canceled_order(self,id):

        query = """
                UPDATE cancelled_orders
                SET confirm_by_saler = 1,confirm_at = NOW()
                WHERE id = %s;
        """
        try:
            
            self.cursor.execute(query,(id,))
            self.conn.commit()

            return {"success": True}

        except Exception as e:
            self.conn.rollback()
            return {"success": False, "message": f"Something went wrong while shipping order: {str(e)}"}
            
    def reject_canceled_order(self,id):
        
        update_query = """
                UPDATE live_order_track
                SET cancel_order_status = 0
                WHERE id IN (
                    SELECT live_order_track_id FROM cancelled_orders WHERE cancelled_orders.id = %s
                );
        """

        delete_query = """
                DELETE FROM cancelled_orders WHERE id = %s;
        """

        try:
            self.cursor.execute(update_query,(id,))
            self.cursor.execute(delete_query,(id,))
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
                return jsonify({'success':True,'message':'Done!'}),200

            else:
                return jsonify({'success':False,'message':f'Somthing went wrong!{response['message']}'}),500

        if cancel_order_status == 0 and id:

            response = my_obj.reject_canceled_order(id)

            if response['success']:
                my_obj.close()
                return jsonify({'success':True,'message':'Done!'}),200
            else:
                return jsonify({'success':False,'message':f'Somthing went wrong!{response['message']}'}),500

    
        return jsonify({'success':False,'message':f'Somthing went wrong!'}),500

    except Exception as e:
        print(f"Error fetching orders: {e}")
        return jsonify({'success':False,'message':f'Somthing went wrong! {e}'}),500



sales_bp.add_url_rule('/sales/', view_func=sales_dashboard)
