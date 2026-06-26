# Business Metrics Catalogue

Each metric includes a plain-English definition, the key tables involved,
and a reference SQL query. Use these as canonical patterns when generating
SQL from natural language questions.

---

## 1. Customer & Advisor Metrics

### 1.1 Total Customers per Advisor
Number of customers assigned to each advisor.

**Tables:** `advisors`, `customers`

```sql
SELECT a.advisor_name, a.region,
       COUNT(c.customer_id) AS total_customers
FROM advisors a
LEFT JOIN customers c ON a.advisor_id = c.advisor_id
GROUP BY a.advisor_id, a.advisor_name, a.region
ORDER BY total_customers DESC;
```

---

### 1.2 Customer Tenure (Years)
How long a customer has been with the firm.

**Tables:** `customers`

```sql
SELECT customer_id,
       first_name || ' ' || last_name AS customer_name,
       customer_since,
       ROUND((julianday('now') - julianday(customer_since)) / 365.25, 1) AS tenure_years
FROM customers
ORDER BY tenure_years DESC;
```

---

### 1.3 Customer Demographic Breakdown
Distribution of customers by state or age group.

**Tables:** `customers`

```sql
-- By state
SELECT state, COUNT(*) AS customer_count
FROM customers
GROUP BY state
ORDER BY customer_count DESC;

-- By age bracket
SELECT
  CASE
    WHEN age < 30 THEN 'Under 30'
    WHEN age BETWEEN 30 AND 44 THEN '30-44'
    WHEN age BETWEEN 45 AND 59 THEN '45-59'
    ELSE '60+'
  END AS age_bracket,
  COUNT(*) AS customer_count
FROM customers
GROUP BY age_bracket;
```

---

## 2. Account & Balance Metrics

### 2.1 Total Account Balance per Customer
Sum of all account balances owned by a customer.

**Tables:** `customers`, `accounts`

```sql
SELECT c.customer_id,
       c.first_name || ' ' || c.last_name AS customer_name,
       SUM(ac.balance) AS total_balance
FROM customers c
JOIN accounts ac ON c.customer_id = ac.customer_id
GROUP BY c.customer_id, customer_name
ORDER BY total_balance DESC;
```

---

### 2.2 Account Type Distribution
Count and total balance by account type.

**Tables:** `accounts`

```sql
SELECT account_type,
       COUNT(*)       AS account_count,
       SUM(balance)   AS total_balance,
       AVG(balance)   AS avg_balance
FROM accounts
GROUP BY account_type
ORDER BY total_balance DESC;
```

---

### 2.3 Accounts Opened Over Time (Monthly)
New account openings by month — useful for growth trend analysis.

**Tables:** `accounts`

```sql
SELECT strftime('%Y-%m', open_date) AS month,
       COUNT(*)                     AS new_accounts
FROM accounts
GROUP BY month
ORDER BY month;
```

---

## 3. Portfolio & Investment Metrics

### 3.1 Assets Under Management (AUM) — Total
Total market value of all holdings across all portfolios.

**Tables:** `holdings`, `market_prices`

```sql
SELECT SUM(h.shares * mp.closing_price) AS total_aum
FROM holdings h
JOIN market_prices mp ON h.security_id = mp.security_id
WHERE mp.price_date = (SELECT MAX(price_date) FROM market_prices);
```

---

### 3.2 AUM per Advisor
Market value of all holdings managed under each advisor.

**Tables:** `advisors`, `customers`, `accounts`, `portfolios`, `holdings`, `market_prices`

```sql
SELECT a.advisor_name,
       SUM(h.shares * mp.closing_price) AS aum
FROM advisors a
JOIN customers c      ON a.advisor_id    = c.advisor_id
JOIN accounts ac      ON c.customer_id   = ac.customer_id
JOIN portfolios p     ON ac.account_id   = p.account_id
JOIN holdings h       ON p.portfolio_id  = h.portfolio_id
JOIN market_prices mp ON h.security_id   = mp.security_id
WHERE mp.price_date = (SELECT MAX(price_date) FROM market_prices)
GROUP BY a.advisor_id, a.advisor_name
ORDER BY aum DESC;
```

---

### 3.3 Portfolio Value per Customer
Total market value of each customer's investment portfolios.

**Tables:** `customers`, `accounts`, `portfolios`, `holdings`, `market_prices`

```sql
SELECT c.customer_id,
       c.first_name || ' ' || c.last_name AS customer_name,
       SUM(h.shares * mp.closing_price)   AS portfolio_value
FROM customers c
JOIN accounts ac      ON c.customer_id   = ac.customer_id
JOIN portfolios p     ON ac.account_id   = p.account_id
JOIN holdings h       ON p.portfolio_id  = h.portfolio_id
JOIN market_prices mp ON h.security_id   = mp.security_id
WHERE mp.price_date = (SELECT MAX(price_date) FROM market_prices)
GROUP BY c.customer_id, customer_name
ORDER BY portfolio_value DESC;
```

---

### 3.4 Sector Allocation (Firm-wide)
Percentage of total AUM invested in each sector.

**Tables:** `holdings`, `securities`, `market_prices`

```sql
SELECT s.sector,
       SUM(h.shares * mp.closing_price)                   AS sector_value,
       ROUND(SUM(h.shares * mp.closing_price) * 100.0 /
             SUM(SUM(h.shares * mp.closing_price)) OVER(), 2) AS pct_of_aum
FROM holdings h
JOIN securities s     ON h.security_id  = s.security_id
JOIN market_prices mp ON h.security_id  = mp.security_id
WHERE mp.price_date = (SELECT MAX(price_date) FROM market_prices)
GROUP BY s.sector
ORDER BY sector_value DESC;
```

---

### 3.5 Top Holdings by Market Value
Largest individual positions across all portfolios.

**Tables:** `holdings`, `securities`, `market_prices`

```sql
SELECT s.ticker, s.company_name, s.sector,
       SUM(h.shares)                          AS total_shares,
       mp.closing_price,
       SUM(h.shares * mp.closing_price)       AS total_market_value
FROM holdings h
JOIN securities s     ON h.security_id  = s.security_id
JOIN market_prices mp ON h.security_id  = mp.security_id
WHERE mp.price_date = (SELECT MAX(price_date) FROM market_prices)
GROUP BY s.security_id, s.ticker, s.company_name, s.sector, mp.closing_price
ORDER BY total_market_value DESC
LIMIT 10;
```

---

## 4. Transaction Metrics

### 4.1 Transaction Volume by Type
Count and total dollar amount by transaction category.

**Tables:** `transactions`

```sql
SELECT transaction_type,
       COUNT(*)        AS transaction_count,
       SUM(amount)     AS total_amount,
       AVG(amount)     AS avg_amount
FROM transactions
GROUP BY transaction_type
ORDER BY total_amount DESC;
```

---

### 4.2 Monthly Transaction Spend per Customer
Rolling monthly spend — useful for budgeting and anomaly detection.

**Tables:** `customers`, `accounts`, `transactions`

```sql
SELECT c.customer_id,
       c.first_name || ' ' || c.last_name        AS customer_name,
       strftime('%Y-%m', t.transaction_date)      AS month,
       SUM(CASE WHEN t.amount < 0 THEN ABS(t.amount) ELSE 0 END) AS total_spend
FROM customers c
JOIN accounts ac ON c.customer_id    = ac.customer_id
JOIN transactions t ON ac.account_id = t.account_id
GROUP BY c.customer_id, customer_name, month
ORDER BY c.customer_id, month;
```

---

### 4.3 Top Merchants by Spend
Which merchants receive the most payments.

**Tables:** `transactions`

```sql
SELECT merchant,
       COUNT(*)       AS transaction_count,
       SUM(ABS(amount)) AS total_spent
FROM transactions
WHERE merchant IS NOT NULL
GROUP BY merchant
ORDER BY total_spent DESC
LIMIT 20;
```

---

## 5. Loan Metrics

### 5.1 Total Outstanding Loan Balance
Aggregate unpaid debt across the portfolio.

**Tables:** `loans`

```sql
SELECT loan_type,
       COUNT(*)                    AS loan_count,
       SUM(principal)              AS total_principal,
       SUM(outstanding_balance)    AS total_outstanding,
       AVG(interest_rate * 100)    AS avg_interest_rate_pct
FROM loans
GROUP BY loan_type
ORDER BY total_outstanding DESC;
```

---

### 5.2 Loan-to-Income Ratio per Customer
Outstanding debt relative to annual income — a creditworthiness signal.

**Tables:** `customers`, `loans`

```sql
SELECT c.customer_id,
       c.first_name || ' ' || c.last_name AS customer_name,
       c.annual_income,
       SUM(l.outstanding_balance)         AS total_debt,
       ROUND(SUM(l.outstanding_balance) / NULLIF(c.annual_income, 0), 2) AS debt_to_income_ratio
FROM customers c
JOIN loans l ON c.customer_id = l.customer_id
GROUP BY c.customer_id, customer_name, c.annual_income
ORDER BY debt_to_income_ratio DESC;
```

---

### 5.3 Customers with Multiple Loans
Identifies customers carrying more than one loan product.

**Tables:** `customers`, `loans`

```sql
SELECT c.customer_id,
       c.first_name || ' ' || c.last_name AS customer_name,
       COUNT(l.loan_id) AS loan_count,
       SUM(l.outstanding_balance) AS total_outstanding
FROM customers c
JOIN loans l ON c.customer_id = l.customer_id
GROUP BY c.customer_id, customer_name
HAVING loan_count > 1
ORDER BY loan_count DESC;
```

---

## 6. Credit Card Metrics

### 6.1 Credit Utilization Rate
Current balance as a percentage of credit limit. High utilization (>30%) is a risk signal.

**Tables:** `credit_cards`

```sql
SELECT card_id, customer_id,
       credit_limit, current_balance,
       ROUND(current_balance / NULLIF(credit_limit, 0) * 100, 2) AS utilization_pct
FROM credit_cards
ORDER BY utilization_pct DESC;
```

---

### 6.2 High-Utilization Customers (>70%)
Customers at risk of credit stress.

**Tables:** `customers`, `credit_cards`

```sql
SELECT c.first_name || ' ' || c.last_name AS customer_name,
       cc.credit_limit, cc.current_balance,
       ROUND(cc.current_balance / NULLIF(cc.credit_limit, 0) * 100, 2) AS utilization_pct
FROM customers c
JOIN credit_cards cc ON c.customer_id = cc.customer_id
WHERE (cc.current_balance / NULLIF(cc.credit_limit, 0)) > 0.70
ORDER BY utilization_pct DESC;
```

---

### 6.3 Total Rewards Points by Customer
Aggregated across all cards a customer holds.

**Tables:** `customers`, `credit_cards`

```sql
SELECT c.customer_id,
       c.first_name || ' ' || c.last_name AS customer_name,
       SUM(cc.rewards_points)             AS total_rewards_points
FROM customers c
JOIN credit_cards cc ON c.customer_id = cc.customer_id
GROUP BY c.customer_id, customer_name
ORDER BY total_rewards_points DESC;
```

---

## 7. Support & Service Metrics

### 7.1 Open Ticket Count per Customer
Customers with unresolved issues — a churn risk indicator.

**Tables:** `customers`, `support_tickets`

```sql
SELECT c.customer_id,
       c.first_name || ' ' || c.last_name AS customer_name,
       COUNT(st.ticket_id) AS open_tickets
FROM customers c
JOIN support_tickets st ON c.customer_id = st.customer_id
WHERE st.status NOT IN ('Resolved', 'Closed')
GROUP BY c.customer_id, customer_name
ORDER BY open_tickets DESC;
```

---

### 7.2 Ticket Volume by Category
Which issue types are most common.

**Tables:** `support_tickets`

```sql
SELECT category,
       COUNT(*)                                      AS total_tickets,
       SUM(CASE WHEN status IN ('Resolved','Closed') THEN 1 ELSE 0 END) AS resolved,
       SUM(CASE WHEN status NOT IN ('Resolved','Closed') THEN 1 ELSE 0 END) AS open
FROM support_tickets
GROUP BY category
ORDER BY total_tickets DESC;
```

---

### 7.3 Average Resolution Time (Days)
How long tickets stay open on average.
> Note: Requires a `resolved_date` column. Currently schema only has `created_date`.
> This query is a placeholder for when `resolved_date` is added.

```sql
-- Placeholder — extend schema with resolved_date to enable this
SELECT category,
       AVG(julianday(resolved_date) - julianday(created_date)) AS avg_days_to_resolve
FROM support_tickets
WHERE status IN ('Resolved', 'Closed')
  AND resolved_date IS NOT NULL
GROUP BY category;
```

---

## 8. Cross-Domain / 360° Customer Metrics

### 8.1 Customer Net Worth Estimate
Cash balances + portfolio value − outstanding loans − credit card debt.

```sql
SELECT c.customer_id,
       c.first_name || ' ' || c.last_name AS customer_name,
       COALESCE(bal.total_balance, 0)          AS cash_balance,
       COALESCE(port.portfolio_value, 0)       AS portfolio_value,
       COALESCE(loan.total_debt, 0)            AS total_loan_debt,
       COALESCE(cc.total_cc_balance, 0)        AS total_cc_balance,
       (COALESCE(bal.total_balance, 0) +
        COALESCE(port.portfolio_value, 0) -
        COALESCE(loan.total_debt, 0) -
        COALESCE(cc.total_cc_balance, 0))      AS estimated_net_worth
FROM customers c
LEFT JOIN (
    SELECT customer_id, SUM(balance) AS total_balance
    FROM accounts GROUP BY customer_id
) bal ON c.customer_id = bal.customer_id
LEFT JOIN (
    SELECT c2.customer_id, SUM(h.shares * mp.closing_price) AS portfolio_value
    FROM customers c2
    JOIN accounts ac ON c2.customer_id = ac.customer_id
    JOIN portfolios p ON ac.account_id = p.account_id
    JOIN holdings h ON p.portfolio_id = h.portfolio_id
    JOIN market_prices mp ON h.security_id = mp.security_id
    WHERE mp.price_date = (SELECT MAX(price_date) FROM market_prices)
    GROUP BY c2.customer_id
) port ON c.customer_id = port.customer_id
LEFT JOIN (
    SELECT customer_id, SUM(outstanding_balance) AS total_debt
    FROM loans GROUP BY customer_id
) loan ON c.customer_id = loan.customer_id
LEFT JOIN (
    SELECT customer_id, SUM(current_balance) AS total_cc_balance
    FROM credit_cards GROUP BY customer_id
) cc ON c.customer_id = cc.customer_id
ORDER BY estimated_net_worth DESC;
```
