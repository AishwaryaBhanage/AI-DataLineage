-- Layer 4: Customer lifetime metrics with CTEs and window functions
--
-- INTENTIONALLY BROKEN — contains 6 distinct errors tracing to decisions
-- made in both the staging layer AND the raw layer.
--
-- Errors embedded:
--   1. 'amount'            — should be 'amount_total' (stg_orders renamed it)
--   2. 'price'             — stg_orders dropped this column during staging
--   3. 'customer_name'     — should be 'full_name' (stg_customers renamed it)
--   4. 'email_address'     — typo, doesn't exist anywhere upstream
--   5. 'phone_number'      — exists in raw_customers but stg_customers drops
--                            it for PII compliance (downstream should not use)
--   6. 'membership_level'  — phantom column; the real name is 'loyalty_tier'
--                            (from raw_customers, passed through stg_customers)
--
-- A real data engineer hitting these in production would fix them one at a
-- time over 30-60 minutes.  The LLM should find all 6 in a single pass.

with customer_order_stats as (
    select
        customer_id,
        order_date,
        sum(amount) as order_value,                                                    -- ERROR 1: 'amount' -> 'amount_total'
        row_number() over (partition by customer_id order by order_date) as order_num,
        lag(price) over (partition by customer_id order by order_date) as prev_price   -- ERROR 2: 'price' not in stg_orders
    from {{ ref('stg_orders') }}
    group by customer_id, order_date
),

customer_profile as (
    select
        customer_id,
        customer_name,      -- ERROR 3: 'customer_name' -> 'full_name'
        country,
        signup_date,
        email_address,      -- ERROR 4: typo, no such column anywhere
        phone_number,       -- ERROR 5: exists in raw_customers, dropped in stg for PII
        membership_level    -- ERROR 6: phantom; should be 'loyalty_tier'
    from {{ ref('stg_customers') }}
)

select
    cp.customer_id,
    cp.customer_name,
    cp.country,
    cp.email_address,
    cp.phone_number,
    cp.membership_level,
    cos.order_value,
    cos.order_num,
    cos.prev_price,
    sum(cos.order_value) over (partition by cp.country)      as country_total_value,
    avg(cos.order_value) over (partition by cp.country)      as country_avg_value,
    rank()               over (order by cos.order_value desc) as spending_rank,
    dense_rank()         over (partition by cp.country order by cos.order_value desc) as country_spending_rank
from customer_profile cp
left join customer_order_stats cos on cp.customer_id = cos.customer_id
order by spending_rank
