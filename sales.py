from flask import Blueprint, render_template, jsonify, request, session, send_file
from utils import get_db_connection, login_required, encrypt_password,decrypt_password
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
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from io import BytesIO
import json



ist = pytz.timezone('Asia/Kolkata')
now_ist = datetime.now(ist)
formatted_time = now_ist.strftime("%d-%m-%Y %H:%M")



# Create a Blueprint for manager routes
sales_bp = Blueprint('sales', __name__)

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
        cursor.execute("INSERT INTO products (name, price, hsn_code, gst_rate, description) VALUES (%s, %s, %s, %s, %s)", (name, price, hsn_code, gst_rate, description))
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'message': 'Product added successfully'}), 200  
    
    except Exception as e:
        print(f"Error adding product: {e}")
        return jsonify({'error': str(e)}), 500  



@sales_bp.route('/sales/generate-bill', methods=['POST'])
def generate_bill():
    try:
        # Import necessary modules
        from reportlab.lib.pagesizes import A4, inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from io import BytesIO
        import json
        import datetime
        
        # Get form data
        customer_id = request.form.get('customer_id')
        bill_no = request.form.get('bill_no')
        delivery_mode = request.form.get('delivery_mode')
        transport_company = request.form.get('transport_company') # if
        payment_mode = request.form.get('payment_mode')
        payment_type = request.form.get('payment_type')
        paid_amount = float(request.form.get('paid_amount', 0))
        grand_total = float(request.form.get('grand_total', 0))
        sales_note = request.form.get('sales_note', '')
        
        # Format current time
        formatted_time = datetime.datetime.now().strftime("%d/%m/%Y %I:%M %p")
        
        # Get products from form data
        products = request.form.get('products')
        if products:
            products = json.loads(products)
        else:
            return jsonify({'error': 'No products in the bill'}), 400

        # Get customer details
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
        
        # Prepare bill data
        bill_data = {
            'bill_no': bill_no,
            'customer': customer,
            'delivery_mode': delivery_mode,
            'transport_company': transport_company,
            'payment_mode': payment_mode,
            'payment_type': payment_type,
            'paid_amount': paid_amount,
            'grand_total': grand_total,
            'sales_note': sales_note,
            'products': products,
            'date': formatted_time
        }

        # Generate PDF
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
            alignment=1,  # Center alignment
            spaceAfter=0
        )
        
        subtitle_style = ParagraphStyle(
            'CompanyInfo',
            parent=styles['Normal'],
            fontSize=9,
            alignment=1,  # Center alignment
            spaceAfter=0
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=10,
            fontName='Helvetica-Bold',
            spaceAfter=2
        )
        
        normal_style = styles['Normal']
        
        # Add company header - match exactly with sample
        elements.append(Paragraph("SMART TRADERS", title_style))
        elements.append(Paragraph("Ahmedabad, Gujarat, 382330, Ahmedabad, Gujarat, 382330", subtitle_style))
        elements.append(Paragraph("GSTIN: 24DCFPS1329A1Z1 Mobile: 9316876474", subtitle_style))
        elements.append(Spacer(1, 10))

        # Add invoice details with table - match exactly with sample
        invoice_data = [
            [Paragraph(f"<b>Invoice No : {bill_no}</b>", normal_style), Paragraph(f"<b>Invoice Date : {formatted_time}</b>", normal_style)],
            [f"BILL TO:\n\n{customer['name']}\n\nMobile:{customer['mobile']}",f"SHIP TO:\n\n{customer['name']}\n\n"]
        ]
        invoice_table = Table(invoice_data, colWidths=[4*inch, 4*inch])
        invoice_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (1, 0), 'LEFT'),
            ('ALIGN', (0, 1), (1, 1), 'LEFT'),
            ('GRID', (0, 0), (1, 1), 0.5, colors.black),
            ('BACKGROUND', (0, 0), (1, 0), colors.lightgrey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(invoice_table)
        elements.append(Spacer(1, 10))

        # Product table - match exactly with sample
        headers = ["S.NO.", "ITEMS","QTY.", "RATE", "TAX", "AMOUNT"]
        col_widths = [0.5*inch, 3.8*inch, 0.9*inch, 0.8*inch, 1*inch, 1*inch, 1*inch]
        
        product_data = [headers]
        
        total_tax_amount = 0
        hsn_tax_summary = {}
        
        for idx, product in enumerate(products, 1):
            # Calculate values
            qty = product['quantity']
            unit = product.get('unit', 'PCS')
            rate = float(product['basePrice'])
            tax_rate = 18  # Assuming 18% as in your example
            tax_amount = float(product['gstAmount'])
            total_amount = float(product['total'])
            hsn_code = product.get('hsn_code', '95059090')  # Default HSN if not provided
            
            # Add to tax summary
            if hsn_code not in hsn_tax_summary:
                hsn_tax_summary[hsn_code] = {
                    'taxable': 0,
                    'tax': 0
                }
            
            taxable_value = total_amount - tax_amount
            hsn_tax_summary[hsn_code]['taxable'] += taxable_value
            hsn_tax_summary[hsn_code]['tax'] += tax_amount
            
            # Add product row - formatted exactly like sample
            product_data.append([
                str(idx),
                product['name'],
                f"{qty} {unit}",
                f"{rate:.1f}",
                f"{tax_amount:.2f}\n({tax_rate}%)",
                f"{total_amount:.0f}"
            ])
            
            total_tax_amount += tax_amount
        
        # Add extra row for additional payment if any - match sample format
        if paid_amount > grand_total:
            extra_paid = paid_amount - grand_total
            product_data.append([
                "-",
                "Extra Paid",
                "-",
                "-",
                f"{extra_paid:.0f}",
                "0\n(0%)",
                f"Rs {extra_paid:.0f}"
            ])
        
        # Create product table with exact formatting as sample
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
            ('ALIGN', (0, 1), (0, -1), 'CENTER'),  # S.NO. centered
            ('ALIGN', (2, 1), (2, -1), 'CENTER'),  # HSN centered
            ('ALIGN', (3, 1), (6, -1), 'RIGHT'),   # Numbers right-aligned
        ]))
        elements.append(product_table)
        
        
        # TOTAL row - separate from product table, exactly like sample
        total_data = [
            ["","GRAND TOTAL", f"{sum(float(p['quantity']) for p in products)}","",f"Rs {total_tax_amount:.2f}", f"Rs {grand_total:.0f}"],
            ["","RECEIVED AMOUNT", "","","", f"Rs {paid_amount:.0f}"],
            ["","BALANCE AMOUNT", "","","", f"Rs {(grand_total - paid_amount):.0f}"],

        ]
        total_table = Table(total_data, colWidths=[0.5*inch, 3.8*inch, 0.9*inch, 0.8*inch, 1*inch, 1*inch, 1*inch])
        total_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ]))
        elements.append(total_table)
        elements.append(Spacer(1, 10))
        
        # Tax summary table - match exactly with sample
        tax_headers = ["HSN/SAC", "Taxable Value", "CGST\nRate Amount", "SGST\nRate Amount", "Total Tax Amount"]
        tax_widths = [2*inch, 1.5*inch, 1.5*inch, 1.5*inch, 1.5*inch]
        
        tax_data = [tax_headers]
        
        for hsn, values in hsn_tax_summary.items():
            taxable = values['taxable']
            tax = values['tax']
            half_tax = tax / 2  # Split between CGST and SGST
            
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
        elements.append(tax_summary_table)
        elements.append(Spacer(1, 10))
        
        # Amount in words - match exactly with sample
        
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
                if num: result += ' '
            if num >= 100000:
                result += number_to_words(num // 100000) + ' Lakh'
                num %= 100000
                if num: result += ' '
            if num >= 1000:
                result += number_to_words(num // 1000) + ' Thousand'
                num %= 1000
                if num: result += ' '
            if num > 0:
                result += three_digits(num)

            return result or 'Zero'
        
        # Convert amount to words - match exactly with sample
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
        elements.append(words_table)
        elements.append(Spacer(1, 10))
        
        # Notes - match exactly with sample
        if sales_note:
            notes_data = [
                ["Notes"],
                [sales_note]
            ]
            
            notes_table = Table(notes_data, colWidths=[8*inch])
            notes_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, 0), colors.lightgrey),
                ('TEXTCOLOR', (0, 0), (0, 0), colors.black),
                ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (0, -1), 0.5, colors.black),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ]))
            elements.append(notes_table)
            elements.append(Spacer(1, 10))
        
        # Terms and conditions - match exactly with sample
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
        elements.append(terms_table)
        elements.append(Spacer(1, 10))
        
        # Footer - match exactly with sample
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
            as_attachment=True,
            download_name=f"bill_{bill_no}.pdf",
            mimetype='application/pdf'
        )

    except Exception as e:
        print(f"Error generating bill: {e}")
        return jsonify({'error': str(e)}), 500



sales_bp.add_url_rule('/sales/', view_func=sales_dashboard)

