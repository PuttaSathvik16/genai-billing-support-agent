-- Task 5: Conversation Insights — Promise Fulfillment Analytics
--
-- Expected schema for billing_conversations (not created by this repo,
-- provided by the production conversation-logging pipeline):
--
--   conversation_id   STRING
--   call_date         DATE
--   promise_type      STRING   -- 'refund' | 'credit' | 'follow_up' | 'callback'
--   amount            NUMERIC
--   timeframe         STRING
--   fulfilled         BOOL     -- set by a downstream reconciliation job
--
-- Run with:
--   bq query --use_legacy_sql=false < sql/promise_analytics.sql

SELECT
  promise_type,
  COUNT(*) AS promise_count,
  ROUND(AVG(amount), 2) AS avg_amount,
  ROUND(
    SUM(CASE WHEN fulfilled THEN 1 ELSE 0 END) / COUNT(*) * 100,
    1
  ) AS fulfillment_rate_pct
FROM `YOUR_PROJECT.billing.billing_conversations`
WHERE call_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 4 WEEK)
GROUP BY promise_type
ORDER BY promise_count DESC;

-- Business value: a dropping fulfillment_rate_pct for any promise_type is an
-- early signal that agents are committing to refunds/credits faster than the
-- backend can honor them — a leading indicator of repeat calls and churn
-- before it shows up in CSAT scores.
