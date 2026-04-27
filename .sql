-- 1. buddy: mobile lookup (used in every invoice save for customer lookup)
ALTER TABLE buddy ADD INDEX idx_buddy_mobile (mobile);

-- 2. products: composite index for stock check query
--    WHERE id = ? AND quantity >= ?
ALTER TABLE products ADD INDEX idx_products_qty (id, quantity);

-- 3. invoice_items: lookup by invoice (used heavily in invoice display)
ALTER TABLE invoice_items ADD INDEX idx_items_invoice_id (invoice_id);

-- 4. additional_charges: lookup by invoice
ALTER TABLE additional_charges ADD INDEX idx_charges_invoice_id (invoice_id);


CREATE INDEX idx_products_active_name ON products (active, name);




-- ── Index hints (run once if not already present) ──────────────────────────
-- Ensure the live_order_track lookup is instant
CREATE INDEX IF NOT EXISTS idx_lot_invoice_pack_cancel
    ON live_order_track (invoice_id, sales_proceed_for_packing, cancel_order_status);

-- Ensure invoice_items join is fast
CREATE INDEX IF NOT EXISTS idx_invoice_items_invoice
    ON invoice_items (invoice_id);

-- Ensure additional_charges join is fast
CREATE INDEX IF NOT EXISTS idx_charges_invoice
    ON additional_charges (invoice_id);



-- ============================================================
-- Recommended indexes (run once – skip if already present)
-- ============================================================
 
-- Fast invoice_number lookup (the new entry point)
ALTER TABLE invoices
    ADD INDEX IF NOT EXISTS idx_invoices_invoice_number (invoice_number);
 
-- Fast join from live_order_track back to invoices
ALTER TABLE live_order_track
    ADD INDEX IF NOT EXISTS idx_lot_invoice_id (invoice_id);
 
-- Fast product line-item lookups
ALTER TABLE invoice_items
    ADD INDEX IF NOT EXISTS idx_invoice_items_invoice_id (invoice_id);
 
-- Fast charge lookups
ALTER TABLE additional_charges
    ADD INDEX IF NOT EXISTS idx_additional_charges_invoice_id (invoice_id);



-- Primary lookup — must be unique or at least indexed
ALTER TABLE invoices
    ADD UNIQUE INDEX uq_invoice_number (invoice_number);

-- JOIN targets (add only if not already present)
CREATE INDEX idx_invoice_items_invoice_id
    ON invoice_items (invoice_id);

CREATE INDEX idx_additional_charges_invoice_id
    ON additional_charges (invoice_id);

CREATE INDEX idx_live_order_track_invoice_id
    ON live_order_track (invoice_id, cancel_order_status, sales_proceed_for_packing);




ALTER TABLE transport ADD INDEX idx_pincode (pincode);
ALTER TABLE transport ADD INDEX idx_name (name);
ALTER TABLE transport ADD INDEX idx_city (city);
ALTER TABLE transport ADD FULLTEXT INDEX ft_name_city (name, city);


-- For the digit/mobile path — prefix LIKE uses this index efficiently
ALTER TABLE `buddy` ADD INDEX idx_mobile (mobile);

-- For the name path — FULLTEXT is far faster than LIKE '%...%' at scale
ALTER TABLE `buddy` ADD FULLTEXT INDEX ft_name (name);




SELECT grand_total,paid_amount,payment_mode,left_to_paid, 

DATE(lot.sales_date_time) as invoice_date

from invoices 

JOIN live_order_track as lot ON lot.invoice_id = invoices.id

WHERE

lot.sales_proceed_for_packing = 1

AND lot.cancel_order_status = 0

AND invoices.cancel_order_status = 0

AND invoices.event_id = 6;


SELECT 
    name,
    location,
    
    CASE 
        WHEN CURDATE() BETWEEN start_date AND end_date THEN 'Ongoing'
        WHEN CURDATE() > end_date THEN 'Completed'
        ELSE 'Upcoming'
    END AS status,
    
    CASE 
        WHEN CURDATE() >= start_date 
        THEN DATEDIFF(LEAST(CURDATE(), end_date), start_date) + 1
        ELSE 0
    END AS completed_days

FROM market_events
WHERE id = 6 AND active = 1;


