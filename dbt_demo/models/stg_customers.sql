-- Layer 2: Staging for customers
--
-- Transformations applied here:
--   1. 'customer_name' → 'full_name' (column rename)
--   2. 'signup_date' cast to DATE type
--   3. 'phone_number' INTENTIONALLY DROPPED — PII compliance.
--      Do NOT reference phone_number in downstream models.
--   4. 'loyalty_tier' passed through as-is
--
-- Downstream models that need customer info should:
--   - Use 'full_name' not 'customer_name'
--   - Not reference 'phone_number' (it's been stripped for privacy)
--   - Use 'loyalty_tier' for segmentation

select
    customer_id,
    customer_name as full_name,
    country,
    cast(signup_date as date) as signup_date,
    loyalty_tier
from {{ ref('raw_customers') }}
