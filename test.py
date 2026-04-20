BEGIN

    DECLARE v_left_to_paid DECIMAL(10,2);
    DECLARE v_invoice_number VARCHAR(20);

    SET v_left_to_paid = p_grand_total - p_paid_amount;
    SET v_invoice_number = UUID();

    INSERT INTO invoices (
        id, customer_id, grand_total, paid_amount,
        left_to_paid, payment_mode, transport_id,
        sales_note, invoice_created_by_user_id,
        invoice_number, created_at
    )
    VALUES (
        p_billno, p_customer_id, p_grand_total, p_paid_amount,
        v_left_to_paid, p_payment_mode, p_transport_id,
        p_sales_note, p_user_id,
        v_invoice_number, NOW()
    );

    SELECT LAST_INSERT_ID() AS invoice_id;

END