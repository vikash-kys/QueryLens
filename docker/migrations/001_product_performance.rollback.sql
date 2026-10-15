-- Restores the previous view logic; does not change table data.
BEGIN;
CREATE OR REPLACE VIEW product_performance AS
SELECT
    p.product_id, p.name, p.category, p.subcategory,
    SUM(oi.quantity) AS units_sold,
    SUM(oi.quantity * oi.unit_price) AS revenue,
    SUM(oi.quantity * (oi.unit_price - p.cost_price)) AS gross_profit,
    ROUND(100.0 * SUM(oi.quantity * (oi.unit_price - p.cost_price)) / NULLIF(SUM(oi.quantity * oi.unit_price),0), 2) AS margin_pct
FROM products p
LEFT JOIN order_items oi ON oi.product_id = p.product_id
LEFT JOIN orders o ON o.order_id = oi.order_id AND o.status NOT IN ('cancelled','refunded')
GROUP BY 1,2,3,4;

COMMIT;
