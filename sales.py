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

    def generate_unique_invoice_number(self,cursor):
        """Generate a unique alphanumeric invoice number."""
        while True:
            invoice_number = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
            cursor.execute("SELECT COUNT(*) FROM invoices WHERE invoice_number = %s", (invoice_number,))
            (count,) = cursor.fetchone()
            if count == 0:
                return invoice_number

    def add_invoice_detail(self, invoice_data):


        if not self.conn:
            return "Database connection is not available."

        try:
            cursor = self.conn.cursor()

            # Step 1: Generate unique invoice number
            invoice_number = self.generate_unique_invoice_number(cursor)

            # Step 2: Prepare invoice data
            gst_included = 1 if invoice_data.get('gst_included') == 'on' else 0
            left_to_paid = invoice_data['grand_total'] - invoice_data['paid_amount']

            insert_invoice_query = """
                INSERT INTO invoices (
                    customer_id, delivery_mode, grand_total, gst_included,
                    invoice_created_by_user_id, left_to_paid, paid_amount,
                    payment_mode, payment_note, sales_note, transport_company_name,
                    invoice_number, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
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
                invoice_number
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
                quantity = int(product[1])  # You may want to extract actual quantity from product[2] if needed
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


# # Example usage:
# if __name__ == "__main__":
#     sales = Sales()
#     result = sales.add_invoice_detail('John Doe', 250.75, '2025-05-26')
#     print(result)  # This will print the success message with the invoice ID
#     sales.close_connection()  # Ensure to close the connection when done


# Manager Dashboard
@sales_bp.route('/sales/dashboard')
@login_required('Sales')
def sales_dashboard():
    return render_template('dashboards/sales/main.html')


@sales_bp.route('/sales/sell')
@login_required('Sales')
def sales():
    return render_template('dashboards/sales/sell.html')


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
        cursor.execute("INSERT INTO buddy (name, address, state, pincode, mobile) VALUES (%s, %s, %s, %s, %s)",
                       (name, address, state, pincode, mobile))
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

@sales_bp.route('/sales/generate-bill', methods=['POST'])
def generate():
    
    print(request.form)

    return jsonify({'error': 'Internal server error'}), 500



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

        if paid_amount == 0:
            payment_mode = "not_paid"

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
        }

        # Save to database
        sales = Sales()
        if sales.data_base_connection_check():
            result = sales.add_invoice_detail(bill_data)
            print(result)
            
            # Return success with invoice ID
            return jsonify({
                'success': True,
                'invoice_id':result['invoice_id'],
                'invoice_number':result['invoice_number']
            }), 200
        else:
            return jsonify({'error': 'Database Error!'}), 500

    except Exception as e:
        print(f"Error saving invoice: {e}")
        return jsonify({'error': str(e)}), 500

@sales_bp.route('/sales/share_invoice_pdf/<string:invoice_id>',methods=['POST'])
def generate_bill_pdf(invoice_id):
    """
    Second function - Generate PDF from database data using invoice_id
    """
    try:

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
        
        bill_no = invoice_data['invoice_number'] + str(invoice_data['id'])  # or however you store bill number
        delivery_mode = invoice_data['delivery_mode']
        transport_company = invoice_data['transport_company_name']
        payment_mode = invoice_data['payment_mode']
        payment_type = invoice_data.get('payment_type', '')
        paid_amount = float(invoice_data['paid_amount'])
        grand_total = float(invoice_data['grand_total'])
        sales_note = invoice_data['sales_note']
        IncludeGST = invoice_data['gst_included']
        

        # Convert products to the format expected by PDF generation
        products_formatted = []
        for product in products:
            products_formatted.append({
                'id': product['product_id'],
                'name': product['product_name'],
                'quantity': product['quantity'],
                'unit': product.get('unit', 'PCS'),
                'finalPrice': float(product['price']) + float(product['gst_tax_amount']),  # Reconstruct original rate
                'total': float(product['total_amount']),
                'hsn_code': product.get('hsn_code', '95059090')
            })

        tax_rate = 0
        if IncludeGST == 'on':
            tax_rate = 18

        # Get invoice creation date
        formatted_time = invoice_data['created_at'].strftime("%d/%m/%Y %I:%M %p") if invoice_data.get('created_at') else datetime.datetime.now().strftime("%d/%m/%Y %I:%M %p")

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

        invoice_table = Table(invoice_data_table, colWidths=[4 * inch, 4 * inch])
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
        headers = ["S.NO.", "ITEMS", "QTY.", "RATE", f"TAX ({tax_rate}%)", "AMOUNT"]
        col_widths = [0.5*inch, 3.8*inch, 0.9*inch, 0.8*inch, 1*inch, 1*inch, 1*inch]

        product_data = [headers]
        total_tax_amount = 0
        hsn_tax_summary = {}

        for idx, product in enumerate(products_formatted, 1):
            qty = product['quantity']
            unit = product.get('unit', 'PCS')
            rate = float(product['finalPrice'])

            original_amount = rate / (1 + tax_rate / 100)
            gst_amount = rate - original_amount
            tax_amount = float(f"{gst_amount:.2f}")
            total_amount = float(product['total'])
            
            hsn_code = product.get('hsn_code', '95059090')

            if hsn_code not in hsn_tax_summary:
                hsn_tax_summary[hsn_code] = {'taxable': 0, 'tax': 0}

            taxable_value = total_amount - tax_amount
            hsn_tax_summary[hsn_code]['taxable'] += taxable_value
            hsn_tax_summary[hsn_code]['tax'] += tax_amount

            product_data.append([
                str(idx),
                product['name'],
                f"{qty} {unit}",
                f"{original_amount:.2f}",
                f"{tax_amount:.2f}",
                f"{total_amount:.0f}"
            ])

            total_tax_amount += tax_amount

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
        if payment_type == "half_payment" and payment_mode != "not_paid":
            total_data = [
                ["", "GRAND TOTAL", f"{sum(float(p['quantity']) for p in products_formatted)}",
                 "", "", f"Rs {grand_total:.0f}"],
                ["", "RECEIVED AMOUNT", "", "", "", f"Rs {paid_amount:.0f}"],
                ["", "REMAINING AMOUNT", "", "", "", f"Rs {(grand_total - paid_amount):.0f}"],
            ]
        else:
            if payment_mode != "not_paid":
                total_data = [
                    ["", "GRAND TOTAL", f"{sum(float(p['quantity']) for p in products_formatted)}",
                     "", "", f"Rs {grand_total:.0f}"],
                ]

        if payment_mode == "not_paid":
            total_data = [
                ["", "GRAND TOTAL Not Paid", f"{sum(float(p['quantity']) for p in products_formatted)}",
                 "", "", f"Rs {grand_total:.0f}"],
            ]

        total_table = Table(total_data, colWidths=[0.5*inch, 3.8*inch, 0.9*inch, 0.8*inch, 1*inch, 1*inch, 1*inch])
        total_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ]))

        # Tax summary table
        tax_summary_table = None
        if IncludeGST == 'on':
            tax_headers = ["HSN/SAC", "Taxable Value", "CGST\nRate Amount", "SGST\nRate Amount", "Total Tax Amount"]
            tax_widths = [2*inch, 1.5*inch, 1.5*inch, 1.5*inch, 1.5*inch]

            tax_data = [tax_headers]
            for hsn, values in hsn_tax_summary.items():
                taxable = values['taxable']
                tax = values['tax']
                half_tax = tax / 2

                tax_data.append([
                    hsn,
                    f"{taxable:.2f}",
                    f"9% {half_tax:.2f}",
                    f"9% {half_tax:.2f}",
                    f"Rs {tax:.2f}"
                ])

            tax_summary_table = Table(tax_data, colWidths=tax_widths)
            tax_summary_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))

        # Amount in words function
        def number_to_words(num):
            ones = ['', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine',
                    'Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen',
                    'Seventeen', 'Eighteen', 'Nineteen']
            tens = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety']

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
        elements.append(Paragraph("Ahmedabad, Gujarat, 382330, Ahmedabad, Gujarat, 382330", subtitle_style))
        elements.append(Paragraph("GSTIN: 24DCFPS1329A1Z1 Mobile: 9316876474", subtitle_style))
        elements.append(Spacer(1, 10))
        
        elements.append(invoice_table)
        elements.append(Spacer(1, 10))
        elements.append(product_table)
        elements.append(total_table)
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
        return jsonify({'error': str(e)}), 500


# @sales_bp.route('/sales/generate', methods=['POST'])
# def generate_bill():
#     try:
#         # Import necessary modules
#         from reportlab.lib.pagesizes import A4, inch
#         from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
#         from reportlab.lib import colors
#         from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
#         from io import BytesIO
#         import json
#         import datetime

        
#         # Get form data
#         customer_id = request.form.get('customer_id')
#         # bill_no = request.form.get('bill_no')
#         bill_no = 123
#         delivery_mode = request.form.get('delivery_mode')
#         transport_company = request.form.get('transport_company')  # if
#         payment_mode = request.form.get('payment_mode')
#         payment_type = request.form.get('payment_type')
#         paid_amount = float(request.form.get('paid_amount', 0))
#         grand_total = float(request.form.get('grand_total', 0))
#         sales_note = request.form.get('sales_note', '')
#         IncludeGST = request.form.get('IncludeGST', 'off')


#         if paid_amount == 0:
#             payment_mode = "not_paid"

#         tax_rate = 0
#         if IncludeGST == 'on':
#             tax_rate = 18  # Assuming 18% as in your example

#         # Format current time
#         formatted_time = datetime.datetime.now().strftime("%d/%m/%Y %I:%M %p")

#         # Get products from form data
#         products = request.form.get('products')
#         if products or customer_id:
#             products = json.loads(products)
#         else:
#             return jsonify({'error': 'Some data is Missing in the bill'}), 400

#         #need transport_company name
#         if delivery_mode == 'transport':
#             if not transport_company:
#                 return jsonify({'error': 'Some data is Missing in the bill'}), 400
            
#         # Get customer details
#         conn = get_db_connection()
#         if not conn:
#             return jsonify({'error': 'Database connection failed'}), 500

#         cursor = conn.cursor(dictionary=True)
#         cursor.execute("SELECT * FROM buddy WHERE id = %s", (customer_id,))
#         customer = cursor.fetchone()
#         cursor.close()
#         conn.close()

#         if not customer:
#             return jsonify({'error': 'Customer not found'}), 404

#         # Generate PDF
#         buffer = BytesIO()
#         doc = SimpleDocTemplate(buffer, pagesize=A4,
#                                 leftMargin=30, rightMargin=30,
#                                 topMargin=10, bottomMargin=30)
#         elements = []

#         # Define styles
#         styles = getSampleStyleSheet()
#         title_style = ParagraphStyle(
#             'CompanyTitle',
#             parent=styles['Heading1'],
#             fontSize=18,
#             fontName='Helvetica-Bold',
#             alignment=1,  # Center alignment
#             spaceAfter=0
#         )

#         subtitle_style = ParagraphStyle(
#             'CompanyInfo',
#             parent=styles['Normal'],
#             fontSize=9,
#             alignment=1,  # Center alignment
#             spaceAfter=0
#         )

#         heading_style = ParagraphStyle(
#             'CustomHeading',
#             parent=styles['Heading2'],
#             fontSize=10,
#             fontName='Helvetica-Bold',
#             spaceAfter=2
#         )

#         normal_style = styles['Normal']

        
#         from reportlab.platypus import Table, TableStyle, Paragraph, Spacer
#         from reportlab.lib.styles import getSampleStyleSheet
#         from reportlab.lib import colors
#         from reportlab.lib.units import inch


#         styles = getSampleStyleSheet()
#         normal_style = styles["Normal"]

#         # Prepare BILL TO and SHIP TO as Paragraphs for wrapping
#         bill_to = Paragraph(
#             f"<b>BILL TO:</b><br/><br/>{customer['name']}<br/><br/>Mobile: {customer['mobile']}",
#             normal_style
#         )

#         ship_to = Paragraph(
#             f"<b>SHIP TO: </b>{customer['name']}<br/>Address: {customer['address']}<br/>Pincode: {customer['pincode']}<br/>State: {customer['state']}",
#             normal_style
#         )

#         # Invoice header row
#         invoice_header = [
#             Paragraph(f"<b>Invoice No : {bill_no}</b>", normal_style),
#             Paragraph(f"<b>Invoice Date : {formatted_time}</b>", normal_style)
#         ]

#         # Final table data
#         invoice_data = [
#             invoice_header,
#             [bill_to, ship_to],
#         ]

#         # Create the table with fixed column widths (adjust if needed)
#         invoice_table = Table(invoice_data, colWidths=[4 * inch, 4 * inch])
#         invoice_table.setStyle(TableStyle([
#             ('ALIGN', (0, 0), (1, 0), 'LEFT'),
#             ('ALIGN', (0, 1), (1, 1), 'LEFT'),
#             ('GRID', (0, 0), (1, 1), 0.5, colors.black),
#             ('BACKGROUND', (0, 0), (1, 0), colors.lightgrey),
#             ('VALIGN', (0, 0), (-1, -1), 'TOP'),
#             ('LEFTPADDING', (0, 0), (-1, -1), 6),
#             ('RIGHTPADDING', (0, 0), (-1, -1), 6),
#             ('TOPPADDING', (0, 0), (-1, -1), 4),
#             ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
#         ]))



#         # Product table - match exactly with sample
#         headers = ["S.NO.", "ITEMS", "QTY.", "RATE", f"TAX ({tax_rate}%)", "AMOUNT"]
#         col_widths = [0.5*inch, 3.8*inch, 0.9 *
#                       inch, 0.8*inch, 1*inch, 1*inch, 1*inch]

#         product_data = [headers]
#         product_data_for_sql_table = []

#         total_tax_amount = 0
#         hsn_tax_summary = {}
        

#         for idx, product in enumerate(products, 1):
#             # Calculate values
#             qty = product['quantity']
#             unit = product.get('unit', 'PCS')
#             rate = float(product['finalPrice'])

#             # Calculate the original amount (before GST)
#             original_amount = rate / (1 + tax_rate / 100)

#             # Calculate the GST amount
#             gst_amount = rate - original_amount

#             # Calculate tax amount and total amount

#             tax_amount = float(f"{gst_amount:.2f}")
#             total_amount = float(product['total'])
            
#             # Default HSN if not provided
#             hsn_code = product.get('hsn_code', '95059090')

#             # Add to tax summary
#             if hsn_code not in hsn_tax_summary:
#                 hsn_tax_summary[hsn_code] = {
#                     'taxable': 0,
#                     'tax': 0
#                 }

#             taxable_value = total_amount - tax_amount
#             hsn_tax_summary[hsn_code]['taxable'] += taxable_value
#             hsn_tax_summary[hsn_code]['tax'] += tax_amount

#             # Add product row - formatted exactly like sample
#             product_data.append([
#                 str(idx),
#                 product['name'],
#                 f"{qty} {unit}",
#                 f"{original_amount:.2f}",
#                 f"{tax_amount:.2f}",
#                 f"{total_amount:.0f}"
#             ])

#             product_data_for_sql_table.append([
#                 product['id'],
#                 f"{qty}",
#                 f"{original_amount:.2f}",
#                 f"{tax_amount:.2f}",
#                 f"{total_amount:.0f}"
#             ])

#             total_tax_amount += tax_amount

#         # # Add extra row for additional payment if any - match sample format
#         # if paid_amount > grand_total:
#         #     extra_paid = paid_amount - grand_total
#         #     product_data.append([
#         #         "-",
#         #         "Extra Paid",
#         #         "-",
#         #         "-",
#         #         f"{extra_paid:.0f}",
#         #         "0\n(0%)",
#         #         f"Rs {extra_paid:.0f}"
#         #     ])

#         # Create product table with exact formatting as sample
#         product_table = Table(product_data, colWidths=col_widths)
#         product_table.setStyle(TableStyle([
#             ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
#             ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
#             ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
#             ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
#             ('FONTSIZE', (0, 0), (-1, 0), 9),
#             ('BOTTOMPADDING', (0, 0), (-1, 0), 5),
#             ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
#             ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
#             ('ALIGN', (0, 1), (0, -1), 'CENTER'),  # S.NO. centered
#             ('ALIGN', (2, 1), (2, -1), 'CENTER'),  # HSN centered
#             ('ALIGN', (3, 1), (6, -1), 'RIGHT'),   # Numbers right-aligned
#         ]))

#         # TOTAL row - separate from product table, exactly like sample

#         if payment_type == "half_payment" and payment_mode != "not_paid":
#             total_data = [
#                 ["", "GRAND TOTAL", f"{sum(float(p['quantity']) for p in products)}",
#                  "", "", f"Rs {grand_total:.0f}"],
#                 ["", "RECEIVED AMOUNT", "", "", "", f"Rs {paid_amount:.0f}"],
#                 ["", "REMAINING AMOUNT", "", "", "",
#                     f"Rs {(grand_total - paid_amount):.0f}"],
#             ]
#         else:
#             if payment_mode != "not_paid":
#                 total_data = [
#                     ["", "GRAND TOTAL", f"{sum(float(p['quantity']) for p in products)}",
#                      "", "", f"Rs {grand_total:.0f}"],
#                 ]

#         if payment_mode == "not_paid":
#             total_data = [
#                 ["", "GRAND TOTAL Not Paid", f"{sum(float(p['quantity']) for p in products)}",
#                  "", "", f"Rs {grand_total:.0f}"],
#             ]

#         total_table = Table(total_data, colWidths=[
#                             0.5*inch, 3.8*inch, 0.9*inch, 0.8*inch, 1*inch, 1*inch, 1*inch])
#         total_table.setStyle(TableStyle([
#             ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
#             ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
#             ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
#             ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
#         ]))

#         tax_summary_table = None

#         if IncludeGST == 'on':
#             # Tax summary table - match exactly with sample
#             tax_headers = ["HSN/SAC", "Taxable Value",
#                         "CGST\nRate Amount", "SGST\nRate Amount", "Total Tax Amount"]
#             tax_widths = [2*inch, 1.5*inch, 1.5*inch, 1.5*inch, 1.5*inch]

#             tax_data = [tax_headers]

#             for hsn, values in hsn_tax_summary.items():
#                 taxable = values['taxable']
#                 tax = values['tax']
#                 half_tax = tax / 2  # Split between CGST and SGST

#                 tax_data.append([
#                     hsn,
#                     f"{taxable:.2f}",
#                     f"9% {half_tax:.2f}",
#                     f"9% {half_tax:.2f}",
#                     f"Rs {tax:.2f}"
#                 ])

#             tax_summary_table = Table(tax_data, colWidths=tax_widths)
#             tax_summary_table.setStyle(TableStyle([
#                 ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
#                 ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
#                 ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
#                 ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
#                 ('FONTSIZE', (0, 0), (-1, 0), 9),
#                 ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
#                 ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
#                 ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
#             ]))


#         # Amount in words - match exactly with sample

#         def number_to_words(num):
#             ones = ['', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine',
#                     'Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen',
#                     'Seventeen', 'Eighteen', 'Nineteen']
#             tens = ['', '', 'Twenty', 'Thirty', 'Forty',
#                     'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety']

#             def two_digits(n):
#                 if n < 20:
#                     return ones[n]
#                 return tens[n // 10] + (' ' + ones[n % 10] if n % 10 != 0 else '')

#             def three_digits(n):
#                 if n < 100:
#                     return two_digits(n)
#                 return ones[n // 100] + ' Hundred' + (' and ' + two_digits(n % 100) if n % 100 != 0 else '')

#             result = ''
#             if num >= 10000000:
#                 result += number_to_words(num // 10000000) + ' Crore'
#                 num %= 10000000
#                 if num:
#                     result += ' '
#             if num >= 100000:
#                 result += number_to_words(num // 100000) + ' Lakh'
#                 num %= 100000
#                 if num:
#                     result += ' '
#             if num >= 1000:
#                 result += number_to_words(num // 1000) + ' Thousand'
#                 num %= 1000
#                 if num:
#                     result += ' '
#             if num > 0:
#                 result += three_digits(num)

#             return result or 'Zero'

#         # Convert amount to words - match exactly with sample
#         amount_words = number_to_words(int(grand_total)) + " Rupees"
#         if grand_total % 1:
#             paise = int((grand_total % 1) * 100)
#             if paise:
#                 amount_words += f" and {number_to_words(paise)} Paise"

#         words_data = [
#             [f"Total Amount (in words):"],
#             [amount_words]
#         ]

#         words_table = Table(words_data, colWidths=[8*inch])
#         words_table.setStyle(TableStyle([
#             ('BACKGROUND', (0, 0), (0, 0), colors.lightgrey),
#             ('TEXTCOLOR', (0, 0), (0, 0), colors.black),
#             ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
#             ('GRID', (0, 0), (0, -1), 0.5, colors.black),
#             ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
#         ]))


#         # # Notes - match exactly with sample
#         # if sales_note:
#         #     notes_data = [
#         #         ["Notes"],
#         #         [sales_note]
#         #     ]

#         #     notes_table = Table(notes_data, colWidths=[8*inch])
#         #     notes_table.setStyle(TableStyle([
#         #         ('BACKGROUND', (0, 0), (0, 0), colors.lightgrey),
#         #         ('TEXTCOLOR', (0, 0), (0, 0), colors.black),
#         #         ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
#         #         ('GRID', (0, 0), (0, -1), 0.5, colors.black),
#         #         ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
#         #     ]))
#         #     elements.append(notes_table)
#         #     elements.append(Spacer(1, 10))

#         # Terms and conditions - match exactly with sample

#         terms_conditions = [
#             "1. Goods once sold will not be taken back or exchanged",
#             "2. No cancellation & No changes after confirm booking",
#             "3. Your parcel will be dispatched within 3-4 working days",
#             "4. packing & forwarding charges will be additional",
#             "5. delivery charges not included in packing & forwarding charges",
#             "6. Your complaint is only valid if you have a proper opening video of the parcel.\n   { from the seal pack parcel to the end without pause & cut }",
#             "7. Your complaint is only valid for 2 days after you receive .",
#             "8. Our Complain Number - 9638095151 ( Do message us on WhatsApp only )"
#         ]

#         terms_data = [
#             ["Terms and Conditions"],
#             ["\n".join(terms_conditions)]
#         ]

#         terms_table = Table(terms_data, colWidths=[8*inch])
#         terms_table.setStyle(TableStyle([
#             ('BACKGROUND', (0, 0), (0, 0), colors.lightgrey),
#             ('TEXTCOLOR', (0, 0), (0, 0), colors.black),
#             ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
#             ('GRID', (0, 0), (0, -1), 0.5, colors.black),
#             ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
#         ]))



#         # Add company header - match exactly with sample
#         elements.append(Paragraph("SMART TRADERS", title_style))
#         elements.append(Paragraph(
#             "Ahmedabad, Gujarat, 382330, Ahmedabad, Gujarat, 382330", subtitle_style))
#         elements.append(
#             Paragraph("GSTIN: 24DCFPS1329A1Z1 Mobile: 9316876474", subtitle_style))
#         elements.append(Spacer(1, 10))
#         # Add to elements
#         elements.append(invoice_table)
#         elements.append(Spacer(1, 10))

#         elements.append(product_table)

#         elements.append(total_table)
#         elements.append(Spacer(1, 10))

#         elements.append(tax_summary_table)
#         elements.append(Spacer(1, 10))

#         elements.append(words_table)
#         elements.append(Spacer(1, 10))

#         elements.append(terms_table)
#         elements.append(Spacer(1, 10))

#         # Footer - match exactly with sample
#         elements.append(Paragraph("TAX INVOICE ORIGINAL FOR RECIPIENT",
#                                   ParagraphStyle('Footer',
#                                                  parent=normal_style,
#                                                  alignment=1,
#                                                  fontName='Helvetica-Bold')))
        
        
#         # Prepare bill data
#         bill_data = {
#             'customer_id': customer_id,
#             'delivery_mode':delivery_mode,
#             'grand_total': grand_total,
#             'payment_mode':payment_mode,
#             'paid_amount':paid_amount,
#             # 'left_to_paid':left_to_paid,
#             'transport_company_name': transport_company,
#             'sales_note':sales_note,
#             'invoice_created_by_user_id': session.get('user_id'),
#             'payment_note': request.form.get('payment_note', ''),
#             'gst_included': IncludeGST,
#             'products': product_data_for_sql_table,
#         }


#         sales = Sales()

#         if sales.data_base_connection_check():
            
#             result = sales.add_invoice_detail(bill_data)
#             print(result)
            
#         else:
#             e = 'Database Error!'
#             return jsonify({'error': str(e)}), 500


#         # Build PDF
#         doc.build(elements)
#         buffer.seek(0)

#         # Return PDF file
#         return send_file(
#             buffer,
#             as_attachment=True,
#             download_name=f"bill_{bill_no}.pdf",
#             mimetype='application/pdf'
#         )

#     except Exception as e:
#         print(f"Error generating bill: {e}")
#         return jsonify({'error': str(e)}), 500


sales_bp.add_url_rule('/sales/', view_func=sales_dashboard)
