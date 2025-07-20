from flask import Blueprint, render_template, jsonify, request, session
from utils import get_db_connection, login_required, encrypt_password,decrypt_password
import mysql.connector
from datetime import datetime
import pytz

ist = pytz.timezone('Asia/Kolkata')
now_ist = datetime.now(ist)
formatted_time = now_ist.strftime("%d-%m-%Y %H:%M")

# Create a Blueprint for packaging routes
transport_bp = Blueprint('transport', __name__)

@transport_bp.route('/dashboard')
@login_required('Transport')
def transport_dashboard():
    return render_template('dashboards/transport/transport.html')

class TransportModel:
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

    def fetch_transport_orders(self):
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

                        up.username AS pack_by,

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
                        lot.packing_note

                    FROM invoices inv

                    LEFT JOIN buddy b ON inv.customer_id = b.id
                    LEFT JOIN users u ON inv.invoice_created_by_user_id = u.id
                    LEFT JOIN live_order_track lot ON inv.id = lot.invoice_id
                        AND lot.cancel_order_status = 0
                        AND lot.sales_proceed_for_packing = 1
                        AND lot.packing_proceed_for_transport = 1
                    LEFT JOIN users up ON lot.packing_proceed_by = up.id
                    LEFT JOIN invoice_items ii ON inv.id = ii.invoice_id
                    LEFT JOIN products p ON ii.product_id = p.id

                    WHERE lot.transport_proceed_for_builty = 0
                        AND inv.completed = 0
                        AND inv.delivery_mode = 'transport'

                    ORDER BY inv.created_at DESC;
       
                """

        
        self.cursor.execute(query)
        all_order_data = self.cursor.fetchall()
        
        if not all_order_data:
            return []

    
        # Merge products into orders
        merged_orders = self.merge_orders_products(all_order_data)

        return merged_orders

    def fetch_my_transport_orders(self):
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

                        up.username AS pack_by,

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
                        lot.transport_note

                    FROM invoices inv

                    LEFT JOIN buddy b ON inv.customer_id = b.id
                    LEFT JOIN users u ON inv.invoice_created_by_user_id = u.id
                    LEFT JOIN live_order_track lot ON inv.id = lot.invoice_id
                        AND lot.cancel_order_status = 0
                        AND lot.sales_proceed_for_packing = 1
                        AND lot.packing_proceed_for_transport = 1
                        AND lot.transport_proceed_for_builty = 1
                    LEFT JOIN users up ON lot.packing_proceed_by = up.id
                    LEFT JOIN invoice_items ii ON inv.id = ii.invoice_id
                    LEFT JOIN products p ON ii.product_id = p.id

                    WHERE lot.transport_proceed_by = %s
                        AND inv.completed = 0
                        AND inv.delivery_mode = 'transport'

                    ORDER BY inv.created_at DESC;
       
                """

        self.cursor.execute(query,(session.get('user_id'),))
        all_order_data = self.cursor.fetchall()
        
        if not all_order_data:
            return []

    
        # Merge products into orders
        merged_orders = self.merge_orders_products(all_order_data)

        return merged_orders

    def cancel_order(self,data):
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

            self.cursor.execute(insert_query, (data.get('invoice_id'),session.get('user_id'),data.get('reason'),data.get('track_order_id'),))
            self.conn.commit()  # commit on connection, not cursor
            
            return {"success": True, "message": f"Order successfully Cancel"}
            
        except Exception as e:
            self.conn.rollback()  # rollback on connection, not cursor
            return {"success": False, "message": f"Somthing went wrong to cancel order"}

    def done_transportaion(self,data):
        try:
            update_query = """
            UPDATE live_order_track
            SET transport_proceed_for_builty = 1, transport_note = %s, transport_proceed_by = %s,transport_date_time = NOW()
            WHERE id = %s;
            """
            self.cursor.execute(update_query, (data.get('transportNote'),session.get('user_id'),data.get('lot_id'),))
            self.conn.commit() 
            return {"success": True}
            
        except Exception as e:
            self.conn.rollback()  # rollback on connection, not cursor
            return {"success": False,"msg":e}

    def close(self):
        self.cursor.close()
        self.conn.close() # type: ignore
    
@transport_bp.route('/transport/transport-orders-list', methods=['GET'])
@login_required('Transport')
def transport_my_pack_list():
    """
    Fetch the list of orders for the logged-in transport user.
    """    
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not logged in'}), 401
        
        my_pack = TransportModel()
        orders = my_pack.fetch_transport_orders()
        
        my_pack.close()

        if not orders:
            return jsonify([]), 200
        
        return jsonify(orders)

    except Exception as e:
        print(f"Error fetching orders: {e}")
        return jsonify({'error': 'Failed to fetch orders'}), 500

    finally:
        my_pack.close()

@transport_bp.route('/transport/cancel_order', methods=['POST'])
@login_required('Transport')
def cancel_order():
    try:
        data = request.get_json()
        track_order_id = data.get('track_order_id') #reason
        if not track_order_id or not str(track_order_id).isdigit() or not data.get('invoice_id'):
            return jsonify({"success": False, "message": "Invalid Order!"}), 400

        for_cancel_order = TransportModel()
        response = for_cancel_order.cancel_order(data)

        if response.get('success'):
            return jsonify({"success": True, "message": "Order Cancelled Successfully"}), 200
        
        for_cancel_order.close()
        return {"success": False, "message": f"Somthing went wrong!"},500

    except Exception as e:
        return jsonify({"success": False, "message": f"From Server Side: {e}"}), 500

@transport_bp.route('/transport/ready-to-go-for-transport')
@login_required('Transport')
def send_for_transport():
    return render_template('dashboards/transport/ready_transport.html')

@transport_bp.route('/transport/done-transportation', methods=['POST'])
@login_required('Transport')
def done_transportaion():
    try:
        data = request.get_json()
        if not data.get('lot_id'):
            return jsonify({'error': 'Missing Some IMP Information!'}), 400

        transport_obj = TransportModel()
        response = transport_obj.done_transportaion(data)

        if response.get('success'):
            return jsonify({"success": True, "message": "Order Transported Successfully"}),200

        transport_obj.close()
        return jsonify({"success": False, "message": f"Somthing went wrong!"}),500
    
    except Exception as e:
        return jsonify({"success": False, "message": f"From Server Side: {e}"}), 500


@transport_bp.route('/transport/my-transport-orders')
@login_required('Transport')
def my_pack_orders():
    return render_template('dashboards/transport/my_transport_orders.html')

@transport_bp.route('/my-transport-orders', methods=['GET'])
@login_required('Transport')
def my_orders():
    """
    Fetch the list of orders for the logged-in transport user.
    """    
    try:

        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not logged in'}), 401
        
        my_transport = TransportModel()
        orders = my_transport.fetch_my_transport_orders()
        
        my_transport.close()

        if not orders:
            return jsonify([]), 200
        
        return jsonify(orders)

    except Exception as e:
        print(f"Error fetching orders: {e}")
        return jsonify({'error': 'Failed to fetch orders'}), 500

