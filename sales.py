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

@sales_bp.route('/sales/generate-bill', methods=['POST'])
def generate_bill():
    try:
        # Get form data
        customer_id = request.form.get('customer_id')
        bill_no = request.form.get('bill_no')
        delivery_mode = request.form.get('delivery_mode')
        transport_company = request.form.get('transport_company')
        payment_mode = request.form.get('payment_mode')
        payment_type = request.form.get('payment_type')
        paid_amount = float(request.form.get('paid_amount', 0))
        grand_total = float(request.form.get('grand_total', 0))
        sales_note = request.form.get('sales_note', '')
        
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
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        elements = []

        # Define styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            spaceAfter=30
        )
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=12,
            spaceAfter=10
        )
        normal_style = styles['Normal']

        # Add title
        elements.append(Paragraph("TAX INVOICE", title_style))
        elements.append(Spacer(1, 20))

        # Add company details
        company_details = [
            ["SalesPro", "", "Bill No:", bill_no],
            ["123 Business Street", "", "Date:", formatted_time],
            ["City, State - 123456", "", "Delivery Mode:", delivery_mode.capitalize()],
            ["GSTIN: 12ABCDE1234F1Z5", "", "", ""]
        ]
        company_table = Table(company_details, colWidths=[2*inch, 0.5*inch, 1*inch, 2*inch])
        company_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (0, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ]))
        elements.append(company_table)
        elements.append(Spacer(1, 20))

        # Add customer details
        elements.append(Paragraph("Bill To:", heading_style))
        customer_details = [
            ["Name:", customer['name']],
            ["Address:", customer['address']],
            ["Mobile:", customer['mobile']]
        ]
        customer_table = Table(customer_details, colWidths=[1*inch, 4*inch])
        customer_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(customer_table)
        elements.append(Spacer(1, 20))

        # Add products table
        elements.append(Paragraph("Product Details:", heading_style))
        product_data = [["Product", "Price", "GST", "Qty", "Total"]]
        for product in products:
            product_data.append([
                product['name'],
                f"₹{float(product['basePrice']):.2f}",
                f"₹{float(product['gstAmount']):.2f}",
                str(product['quantity']),
                f"₹{float(product['total']):.2f}"
            ])
        
        product_table = Table(product_data, colWidths=[2.5*inch, 1*inch, 1*inch, 0.5*inch, 1*inch])
        product_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(product_table)
        elements.append(Spacer(1, 20))

        # Add totals
        total_data = [
            ["Subtotal:", f"₹{grand_total:.2f}"],
            ["GST (18%):", f"₹{(grand_total * 0.18):.2f}"],
            ["Total Amount:", f"₹{grand_total:.2f}"],
            ["Amount Paid:", f"₹{paid_amount:.2f}"],
            ["Balance Due:", f"₹{(grand_total - paid_amount):.2f}"]
        ]
        total_table = Table(total_data, colWidths=[2*inch, 1*inch])
        total_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (0, -1), 12),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(total_table)
        elements.append(Spacer(1, 20))

        # Add notes
        if sales_note:
            elements.append(Paragraph("Notes:", heading_style))
            elements.append(Paragraph(sales_note, normal_style))
            elements.append(Spacer(1, 20))

        # Add terms and conditions
        elements.append(Paragraph("Terms & Conditions:", heading_style))
        terms = [
            "1. Goods once sold will not be taken back.",
            "2. Payment should be made within 7 days.",
            "3. Interest @ 18% p.a. will be charged on overdue payments.",
            "4. All disputes are subject to jurisdiction of local courts."
        ]
        for term in terms:
            elements.append(Paragraph(term, normal_style))
            elements.append(Spacer(1, 5))

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

