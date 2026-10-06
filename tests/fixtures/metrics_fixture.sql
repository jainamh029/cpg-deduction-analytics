-- Tiny SYNTHETIC fixture for metric tests. Built into the constrained `raw` schema. As-of date for
-- the fixture build is 2024-06-30. Expected values are hand-computed in tests/test_metrics.py.
--
-- Invoices (gross = sum of lines):
--   I1 R1 2024-01-10  1000 = 10x50 + 5x100        paid 900 on 2024-02-14  (deductions 60 + 40)
--   I2 R1 2024-02-15  2000 = 20x100               paid 1800 on 2024-03-26 (deductions 120 + 80)
--   I3 R2 2024-01-20  3000 = 30x100               paid 2700 on 2024-03-05 (deductions 200 + 100)
--   I4 R2 2024-05-01   700 =  7x100               unpaid                  (deduction 50)

insert into raw.retailers values
    (1, 'Retailer A', 'grocery', 'National', 30),
    (2, 'Retailer B', 'mass', 'West', 30);

insert into raw.skus values
    (1, 'Snacks', 100.00, 50.00),
    (2, 'Beverages', 100.00, 50.00);

insert into raw.invoices values
    (1, 1, '2024-01-10', '2024-02-09', 1000.00),
    (2, 1, '2024-02-15', '2024-03-16', 2000.00),
    (3, 2, '2024-01-20', '2024-02-19', 3000.00),
    (4, 2, '2024-05-01', '2024-05-31', 700.00);

insert into raw.invoice_lines values
    (1, 1, 10, 50.00), (1, 2, 5, 100.00),
    (2, 1, 20, 100.00),
    (3, 2, 30, 100.00),
    (4, 1, 7, 100.00);

insert into raw.payments values
    (1, 1, '2024-02-14', 900.00),
    (2, 2, '2024-03-26', 1800.00),
    (3, 3, '2024-03-05', 2700.00);

insert into raw.promotions values
    (1, 1, 1, '2024-01-01', '2024-01-14', 'tpr', 1000.00);

insert into raw.deductions values
    (1, 1, 1, 1,    '2024-01-25',  60.00, 'shortage',        'recovered'),
    (2, 1, 1, null, '2024-02-05',  40.00, 'promo',           'written_off'),
    (3, 2, 1, 2,    '2024-03-01', 120.00, 'compliance_fine', 'accepted'),
    (4, 2, 1, 1,    '2024-03-10',  80.00, 'pricing',         'disputed'),
    (5, 3, 2, 2,    '2024-02-10', 200.00, 'shortage',        'recovered'),
    (6, 3, 2, null, '2024-04-15', 100.00, 'damage',          'open'),
    (7, 4, 2, 1,    '2024-05-10',  50.00, 'shortage',        'open');

insert into raw.disputes values
    (1, 1, '2024-02-05', '2024-03-06', 'won',     60.00),
    (2, 3, '2024-03-31', '2024-04-20', 'lost',     0.00),
    (3, 4, '2024-06-01', null,         'pending',  0.00),
    (4, 5, '2024-02-20', '2024-03-21', 'partial', 120.00);
