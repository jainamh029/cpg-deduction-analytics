-- SYNTHETIC "messy real-world" fixture, loaded into the UNCONSTRAINED raw_dirty schema (as-of 2024-07-31).
-- Each scenario is described where it is asserted: tests/test_messy_conditions.py.
--
-- Invoices:  I1 R1 2024-01-31 1000 (month-end, partial payments)   I5 R2 2024-05-15  300
--            I2 R1 2024-02-10  500 (deduction larger than invoice) I6 R1 2024-03-31  800 (month-end)
--            I3 R2 2024-03-05 2000 (duplicate deductions)          I7 R2 2024-01-10  400
--            I4 R1 2024-04-02  600 (re-filed disputes)

insert into raw_dirty.retailers values
    (1, 'Retailer A', 'grocery', 'National', 30),
    (2, 'Retailer B', 'mass', 'West', 30);

insert into raw_dirty.skus values
    (1, 'Snacks', 100.00, 50.00),
    (2, 'Beverages', 100.00, 50.00);

insert into raw_dirty.invoices values
    (1, 1, '2024-01-31', '2024-03-01', 1000.00),
    (2, 1, '2024-02-10', '2024-03-11',  500.00),
    (3, 2, '2024-03-05', '2024-04-04', 2000.00),
    (4, 1, '2024-04-02', '2024-05-02',  600.00),
    (5, 2, '2024-05-15', '2024-06-14',  300.00),
    (6, 1, '2024-03-31', '2024-04-30',  800.00),
    (7, 2, '2024-01-10', '2024-02-09',  400.00);

insert into raw_dirty.invoice_lines values
    (1, 1, 10, 100.00), (2, 2, 5, 100.00), (3, 1, 20, 100.00), (4, 2, 6, 100.00),
    (5, 1, 3, 100.00), (6, 1, 8, 100.00), (7, 2, 4, 100.00);

insert into raw_dirty.payments values
    (1, 1, '2024-02-20',  400.00),
    (2, 1, '2024-04-05',  400.00),
    (3, 3, '2024-04-10', 1900.00),
    (4, 7, '2024-02-15',  360.00);

insert into raw_dirty.promotions values (1, 1, 1, '2024-01-01', '2024-01-14', 'tpr', 1000.00);

insert into raw_dirty.deductions values
    (1,   1, 1, 1,    '2024-02-15', 100.00, 'shortage', 'disputed'),
    (2,   2, 1, 2,    '2024-02-20', 700.00, 'shortage', 'open'),
    (3,   3, 2, 1,    '2024-03-20',  50.00, 'pricing',  'open'),
    (4,   3, 2, 1,    '2024-03-20',  50.00, 'pricing',  'open'),
    (5,   4, 1, 2,    '2024-04-20', 200.00, 'damage',   'recovered'),
    (6,   5, 2, 1,    '2024-05-20', 100.00, 'shortage', 'disputed'),
    (7,   5, 2, null, '2024-05-22',  80.00, 'pricing',  'recovered'),
    (8,   6, 1, null, '2024-04-30',  60.00, 'other',    'accepted'),
    (9,   6, 1, 1,    '2024-03-25',  40.00, 'other',    'open'),
    (10,  7, 2, 2,    '2024-01-25',  40.00, 'pricing',  'accepted'),
    (11, 999, 1, 1,   '2024-05-01',  30.00, 'other',    'open');

insert into raw_dirty.disputes values
    (1, 5,   '2024-05-01', '2024-05-15', 'lost',      0.00),
    (2, 5,   '2024-05-20', '2024-06-10', 'partial', 120.00),
    (3, 5,   '2024-06-12', '2024-06-25', 'partial', 120.00),
    (4, 6,   '2024-06-01', null,         'pending',   0.00),
    (5, 7,   '2024-05-25', '2024-06-05', 'won',      80.00),
    (6, 1,   '2024-02-20', null,         'pending',   0.00),
    (7, 8,   '2024-05-10', '2024-05-05', 'lost',      0.00),
    (8, 999, '2024-06-01', '2024-06-02', 'won',      25.00);
