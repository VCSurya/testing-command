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