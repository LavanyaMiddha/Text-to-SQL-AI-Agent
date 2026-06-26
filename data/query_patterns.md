# Cross-Table Query Patterns

Each pattern covers a multi-table intent that cannot be satisfied by a single
table schema chunk. Chunking: one chunk per `##` pattern block.

---

## Pattern 01 — Customer 360 View

**Intent:** full profile / complete summary / everything about a customer  
**Tables:** customers, advisors, accounts, loans, credit_cards, support_tickets  
**Trigger phrases:** "full profile", "360 view", "everything about", "summary for customer"

```sql
SELECT c.customer_id,
       c.first_name || ' ' || c.last_name        AS customer_name,
       c.age, c.city, c.state, c.annual_income,
       c.customer_since,
       a.advisor_name, a.region,
       COUNT(DISTINCT ac.account_id)             AS account_count,
       SUM(ac.balance)                           AS total_cash_balance,
       COUNT(DISTINCT l.loan_id)                 AS loan_count,
       COALESCE(SUM(l.outstanding_balance), 0)   AS total_loan_balance,
       COUNT(DISTINCT cc.card_id)                AS card_count,
       COALESCE(SUM(cc.current_balance), 0)      AS total_cc_balance,
       COUNT(DISTINCT st.ticket_id)              AS open_tickets
FROM customers c
LEFT JOIN advisors a         ON c.advisor_id   = a.advisor_id
LEFT JOIN accounts ac        ON c.customer_id  = ac.customer_id
LEFT JOIN loans l            ON c.customer_id  = l.customer_id
LEFT JOIN credit_cards cc    ON c.customer_id  = cc.customer_id
LEFT JOIN support_tickets st ON c.customer_id  = st.customer_id
                             AND st.status NOT IN ('Resolved', 'Closed')
WHERE c.customer_id = ?
GROUP BY c.customer_id, c.first_name, c.last_name, c.age, c.city,
         c.state, c.annual_income, c.customer_since, a.advisor_name, a.region;
```

---

## Pattern 02 — Estimated Customer Net Worth

**Intent:** net worth / total assets minus liabilities / wealth estimate  
**Tables:** customers, accounts, portfolios, holdings, market_prices, loans, credit_cards  
**Trigger phrases:** "net worth", "total assets", "assets minus liabilities", "wealth"

```sql
SELECT c.customer_id,
       c.first_name || ' ' || c.last_name            AS customer_name,
       COALESCE(cash.total_cash, 0)                  AS total_cash_balance,
       COALESCE(port.portfolio_value, 0)             AS portfolio_value,
       COALESCE(debt.total_loans, 0)                 AS total_loan_debt,
       COALESCE(cc.total_cc, 0)                      AS total_cc_balance,
       (COALESCE(cash.total_cash, 0)
        + COALESCE(port.portfolio_value, 0)
        - COALESCE(debt.total_loans, 0)
        - COALESCE(cc.total_cc, 0))                  AS estimated_net_worth
FROM customers c
LEFT JOIN (
    SELECT customer_id, SUM(balance) AS total_cash
    FROM accounts GROUP BY customer_id
) cash ON c.customer_id = cash.customer_id
LEFT JOIN (
    SELECT c2.customer_id,
           SUM(h.shares * mp.closing_price) AS portfolio_value
    FROM customers c2
    JOIN accounts ac      ON c2.customer_id  = ac.customer_id
    JOIN portfolios p     ON ac.account_id   = p.account_id
    JOIN holdings h       ON p.portfolio_id  = h.portfolio_id
    JOIN market_prices mp ON h.security_id   = mp.security_id
    WHERE mp.price_date = (SELECT MAX(price_date) FROM market_prices)
    GROUP BY c2.customer_id
) port ON c.customer_id = port.customer_id
LEFT JOIN (
    SELECT customer_id, SUM(outstanding_balance) AS total_loans
    FROM loans GROUP BY customer_id
) debt ON c.customer_id = debt.customer_id
LEFT JOIN (
    SELECT customer_id, SUM(current_balance) AS total_cc
    FROM credit_cards GROUP BY customer_id
) cc ON c.customer_id = cc.customer_id
ORDER BY estimated_net_worth DESC;
```

---

## Pattern 03 — Total AUM per Advisor

**Intent:** assets under management by advisor / advisor AUM / how much does each advisor manage  
**Tables:** advisors, customers, accounts, portfolios, holdings, market_prices  
**Trigger phrases:** "AUM", "assets under management", "advisor manages", "advisor portfolio value"

```sql
SELECT a.advisor_id,
       a.advisor_name,
       a.region,
       COUNT(DISTINCT c.customer_id)             AS customer_count,
       SUM(h.shares * mp.closing_price)          AS total_aum
FROM advisors a
JOIN customers c      ON a.advisor_id    = c.advisor_id
JOIN accounts ac      ON c.customer_id   = ac.customer_id
JOIN portfolios p     ON ac.account_id   = p.account_id
JOIN holdings h       ON p.portfolio_id  = h.portfolio_id
JOIN market_prices mp ON h.security_id   = mp.security_id
WHERE mp.price_date = (SELECT MAX(price_date) FROM market_prices)
GROUP BY a.advisor_id, a.advisor_name, a.region
ORDER BY total_aum DESC;
```

---

## Pattern 04 — Total Portfolio Value per Customer

**Intent:** how much is a customer's investment portfolio worth / portfolio value / investment value  
**Tables:** customers, accounts, portfolios, holdings, market_prices  
**Trigger phrases:** "portfolio value", "investment value", "how much invested", "portfolio worth"

```sql
SELECT c.customer_id,
       c.first_name || ' ' || c.last_name        AS customer_name,
       SUM(h.shares * mp.closing_price)          AS total_portfolio_value
FROM customers c
JOIN accounts ac      ON c.customer_id   = ac.customer_id
JOIN portfolios p     ON ac.account_id   = p.account_id
JOIN holdings h       ON p.portfolio_id  = h.portfolio_id
JOIN market_prices mp ON h.security_id   = mp.security_id
WHERE mp.price_date = (SELECT MAX(price_date) FROM market_prices)
GROUP BY c.customer_id, customer_name
ORDER BY total_portfolio_value DESC;
```

---

## Pattern 05 — Sector Allocation Across All Holdings

**Intent:** sector breakdown / sector allocation / which sectors are we invested in / sector exposure  
**Tables:** holdings, securities, market_prices  
**Trigger phrases:** "sector", "allocation", "sector breakdown", "industry exposure", "diversification"

```sql
SELECT s.sector,
       SUM(h.shares * mp.closing_price)              AS sector_value,
       ROUND(
           SUM(h.shares * mp.closing_price) * 100.0
           / SUM(SUM(h.shares * mp.closing_price)) OVER (),
       2)                                            AS pct_of_total_aum
FROM holdings h
JOIN securities s     ON h.security_id  = s.security_id
JOIN market_prices mp ON h.security_id  = mp.security_id
WHERE mp.price_date = (SELECT MAX(price_date) FROM market_prices)
GROUP BY s.sector
ORDER BY sector_value DESC;
```

---

## Pattern 06 — Churn Risk Customers

**Intent:** at-risk customers / churn risk / customers with problems / flag risky customers  
**Tables:** customers, loans, credit_cards, support_tickets  
**Trigger phrases:** "churn risk", "at risk", "problematic customers", "customers with issues", "flag customers"

```sql
SELECT c.customer_id,
       c.first_name || ' ' || c.last_name        AS customer_name,
       c.annual_income,
       COALESCE(dti.dti_ratio, 0)                AS debt_to_income_ratio,
       COALESCE(util.utilization_pct, 0)         AS cc_utilization_pct,
       COALESCE(tix.open_tickets, 0)             AS open_support_tickets
FROM customers c
LEFT JOIN (
    SELECT customer_id,
           ROUND(SUM(outstanding_balance) / NULLIF(c2.annual_income, 0), 2) AS dti_ratio
    FROM loans l
    JOIN customers c2 USING (customer_id)
    GROUP BY l.customer_id
) dti ON c.customer_id = dti.customer_id
LEFT JOIN (
    SELECT customer_id,
           ROUND(SUM(current_balance) / NULLIF(SUM(credit_limit), 0) * 100, 2) AS utilization_pct
    FROM credit_cards
    GROUP BY customer_id
) util ON c.customer_id = util.customer_id
LEFT JOIN (
    SELECT customer_id, COUNT(*) AS open_tickets
    FROM support_tickets
    WHERE status NOT IN ('Resolved', 'Closed')
    GROUP BY customer_id
) tix ON c.customer_id = tix.customer_id
WHERE COALESCE(dti.dti_ratio, 0) > 0.5
   OR COALESCE(util.utilization_pct, 0) > 70
   OR COALESCE(tix.open_tickets, 0) > 2
ORDER BY open_support_tickets DESC, cc_utilization_pct DESC;
```

---

## Pattern 07 — Monthly Transaction Spend per Customer

**Intent:** monthly spending / spend trend / how much does a customer spend per month  
**Tables:** customers, accounts, transactions  
**Trigger phrases:** "monthly spend", "spending trend", "spend per month", "transaction history by month"

```sql
SELECT c.customer_id,
       c.first_name || ' ' || c.last_name         AS customer_name,
       strftime('%Y-%m', t.transaction_date)       AS month,
       COUNT(t.transaction_id)                     AS transaction_count,
       SUM(ABS(t.amount))                          AS total_spend
FROM customers c
JOIN accounts ac     ON c.customer_id  = ac.customer_id
JOIN transactions t  ON ac.account_id  = t.account_id
WHERE t.transaction_type IN ('Purchase', 'Payment', 'Withdrawal')
GROUP BY c.customer_id, customer_name, month
ORDER BY c.customer_id, month;
```

---

## Pattern 08 — Top Customers by Total Relationship Value

**Intent:** best customers / top customers / most valuable customers / rank customers by value  
**Tables:** customers, accounts, portfolios, holdings, market_prices, loans, credit_cards  
**Trigger phrases:** "top customers", "most valuable", "best clients", "rank customers", "highest value customers"

```sql
SELECT c.customer_id,
       c.first_name || ' ' || c.last_name        AS customer_name,
       c.annual_income,
       COALESCE(cash.total_cash, 0)              AS cash_balance,
       COALESCE(port.portfolio_value, 0)         AS portfolio_value,
       COALESCE(cash.total_cash, 0)
         + COALESCE(port.portfolio_value, 0)     AS total_assets
FROM customers c
LEFT JOIN (
    SELECT customer_id, SUM(balance) AS total_cash
    FROM accounts GROUP BY customer_id
) cash ON c.customer_id = cash.customer_id
LEFT JOIN (
    SELECT c2.customer_id,
           SUM(h.shares * mp.closing_price) AS portfolio_value
    FROM customers c2
    JOIN accounts ac      ON c2.customer_id  = ac.customer_id
    JOIN portfolios p     ON ac.account_id   = p.account_id
    JOIN holdings h       ON p.portfolio_id  = h.portfolio_id
    JOIN market_prices mp ON h.security_id   = mp.security_id
    WHERE mp.price_date = (SELECT MAX(price_date) FROM market_prices)
    GROUP BY c2.customer_id
) port ON c.customer_id = port.customer_id
ORDER BY total_assets DESC
LIMIT 20;
```

---

## Pattern 09 — Holdings for a Specific Customer with Current Value

**Intent:** what stocks does a customer hold / customer holdings / customer investments / customer positions  
**Tables:** customers, accounts, portfolios, holdings, securities, market_prices  
**Trigger phrases:** "holdings", "positions", "what stocks", "what does X own", "investments for customer"

```sql
SELECT c.first_name || ' ' || c.last_name   AS customer_name,
       p.portfolio_name,
       s.ticker,
       s.company_name,
       s.sector,
       h.shares,
       mp.closing_price,
       ROUND(h.shares * mp.closing_price, 2) AS market_value
FROM customers c
JOIN accounts ac      ON c.customer_id   = ac.customer_id
JOIN portfolios p     ON ac.account_id   = p.account_id
JOIN holdings h       ON p.portfolio_id  = h.portfolio_id
JOIN securities s     ON h.security_id   = s.security_id
JOIN market_prices mp ON h.security_id   = mp.security_id
WHERE c.customer_id = ?
  AND mp.price_date = (SELECT MAX(price_date) FROM market_prices)
ORDER BY market_value DESC;
```

---

## Pattern 10 — Advisor Region Performance Summary

**Intent:** performance by region / regional breakdown / which region has most AUM or customers  
**Tables:** advisors, customers, accounts, portfolios, holdings, market_prices  
**Trigger phrases:** "by region", "regional", "region performance", "region comparison"

```sql
SELECT a.region,
       COUNT(DISTINCT a.advisor_id)               AS advisor_count,
       COUNT(DISTINCT c.customer_id)              AS customer_count,
       SUM(ac.balance)                            AS total_cash_balance,
       SUM(h.shares * mp.closing_price)           AS total_aum,
       ROUND(SUM(h.shares * mp.closing_price)
             / NULLIF(COUNT(DISTINCT c.customer_id), 0), 2) AS aum_per_customer
FROM advisors a
JOIN customers c      ON a.advisor_id    = c.advisor_id
JOIN accounts ac      ON c.customer_id   = ac.customer_id
JOIN portfolios p     ON ac.account_id   = p.account_id
JOIN holdings h       ON p.portfolio_id  = h.portfolio_id
JOIN market_prices mp ON h.security_id   = mp.security_id
WHERE mp.price_date = (SELECT MAX(price_date) FROM market_prices)
GROUP BY a.region
ORDER BY total_aum DESC;
```

---

## Pattern 11 — Customers with No Investment Portfolio

**Intent:** customers without portfolios / uninvested customers / no holdings / cash-only customers  
**Tables:** customers, accounts, portfolios  
**Trigger phrases:** "no portfolio", "not invested", "no holdings", "cash only", "without investments"

```sql
SELECT c.customer_id,
       c.first_name || ' ' || c.last_name  AS customer_name,
       c.annual_income,
       SUM(ac.balance)                     AS total_cash_balance
FROM customers c
LEFT JOIN accounts ac   ON c.customer_id = ac.customer_id
LEFT JOIN portfolios p  ON ac.account_id = p.account_id
WHERE p.portfolio_id IS NULL
GROUP BY c.customer_id, customer_name, c.annual_income
ORDER BY total_cash_balance DESC;
```

---

## Pattern 12 — Debt-to-Income Ratio with Credit Utilization

**Intent:** financial health / debt analysis / risk score / creditworthiness  
**Tables:** customers, loans, credit_cards  
**Trigger phrases:** "debt to income", "DTI", "financial health", "creditworthiness", "credit risk"

```sql
SELECT c.customer_id,
       c.first_name || ' ' || c.last_name          AS customer_name,
       c.annual_income,
       COALESCE(SUM(l.outstanding_balance), 0)      AS total_loan_balance,
       COALESCE(SUM(cc.current_balance), 0)         AS total_cc_balance,
       COALESCE(SUM(cc.credit_limit), 0)            AS total_credit_limit,
       ROUND(
           COALESCE(SUM(l.outstanding_balance), 0)
           / NULLIF(c.annual_income, 0),
       2)                                           AS loan_dti_ratio,
       ROUND(
           COALESCE(SUM(cc.current_balance), 0)
           / NULLIF(SUM(cc.credit_limit), 0) * 100,
       2)                                           AS cc_utilization_pct
FROM customers c
LEFT JOIN loans l         ON c.customer_id = l.customer_id
LEFT JOIN credit_cards cc ON c.customer_id = cc.customer_id
GROUP BY c.customer_id, customer_name, c.annual_income
ORDER BY loan_dti_ratio DESC;
```

---

## Pattern 13 — Support Tickets with Customer and Advisor Context

**Intent:** support issues / tickets with full context / escalations with advisor / ticket details  
**Tables:** support_tickets, customers, advisors  
**Trigger phrases:** "support tickets", "open issues", "escalated", "ticket with advisor", "complaints"

```sql
SELECT st.ticket_id,
       st.created_date,
       st.category,
       st.status,
       c.first_name || ' ' || c.last_name   AS customer_name,
       c.city, c.state,
       a.advisor_name, a.region
FROM support_tickets st
JOIN customers c      ON st.customer_id  = c.customer_id
LEFT JOIN advisors a  ON c.advisor_id    = a.advisor_id
WHERE st.status NOT IN ('Resolved', 'Closed')
ORDER BY
  CASE st.status WHEN 'Escalated' THEN 1 WHEN 'In Progress' THEN 2 ELSE 3 END,
  st.created_date ASC;
```

---

## Pattern 14 — Account Balance + Portfolio Value Combined (Total Wealth per Account)

**Intent:** total value per account / account wealth / cash plus investments per account  
**Tables:** accounts, portfolios, holdings, market_prices  
**Trigger phrases:** "total account value", "account wealth", "cash and investments", "combined value"

```sql
SELECT ac.account_id,
       ac.account_type,
       ac.balance                              AS cash_balance,
       COALESCE(SUM(h.shares * mp.closing_price), 0) AS investment_value,
       ac.balance
         + COALESCE(SUM(h.shares * mp.closing_price), 0) AS total_account_value
FROM accounts ac
LEFT JOIN portfolios p     ON ac.account_id  = p.account_id
LEFT JOIN holdings h       ON p.portfolio_id = h.portfolio_id
LEFT JOIN market_prices mp ON h.security_id  = mp.security_id
                           AND mp.price_date = (SELECT MAX(price_date) FROM market_prices)
GROUP BY ac.account_id, ac.account_type, ac.balance
ORDER BY total_account_value DESC;
```

---

## Pattern 15 — Customers Who Have Both Loans and High Credit Utilization

**Intent:** over-leveraged customers / customers in debt / high risk dual exposure  
**Tables:** customers, loans, credit_cards  
**Trigger phrases:** "over-leveraged", "both loans and credit card debt", "dual debt", "high debt customers"

```sql
SELECT c.customer_id,
       c.first_name || ' ' || c.last_name          AS customer_name,
       c.annual_income,
       SUM(l.outstanding_balance)                  AS total_loan_balance,
       ROUND(SUM(cc.current_balance)
             / NULLIF(SUM(cc.credit_limit), 0) * 100, 2) AS cc_utilization_pct
FROM customers c
JOIN loans l         ON c.customer_id = l.customer_id
JOIN credit_cards cc ON c.customer_id = cc.customer_id
GROUP BY c.customer_id, customer_name, c.annual_income
HAVING cc_utilization_pct > 50
ORDER BY total_loan_balance DESC;
```
