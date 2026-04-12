-- Layer 1: Raw customer source data
-- Simulates a source table in the warehouse.
-- Includes PII (phone_number) that will be dropped in the staging layer
-- for compliance reasons.
select
    101          as customer_id,
    'Alice Smith'   as customer_name,
    'US'         as country,
    '2024-01-01' as signup_date,
    '+1-555-0101' as phone_number,
    'gold'       as loyalty_tier
union all
select 102, 'Bob Johnson',   'UK', '2024-01-05', '+44-20-7946-0958', 'silver'
union all
select 103, 'Charlie Brown', 'US', '2024-02-10', '+1-555-0103',      'gold'
union all
select 104, 'Diana Prince',  'CA', '2024-03-15', '+1-555-0104',      'platinum'
union all
select 105, 'Eve Adams',     'US', '2024-01-20', '+1-555-0105',      'bronze'
