-- Synthetic demo additions, versioned separately from immutable baseline seeds.
INSERT INTO contact (
    tenant_id, contact_id, contact_type, full_name, mobile, mobile_country_code, email,
    date_of_birth, opt_in_email, e_statement_opt_in,
    data_source, created_by_user_id
)
VALUES
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000037', 'Client', 'Demo Client AK', '80000037', '+65', 'demo.client.ak@example.test', '1991-08-26', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000038', 'Client', 'Demo Client AL', '80000038', '+65', 'demo.client.al@example.test', '1991-08-27', FALSE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000039', 'Client', 'Demo Client AM', '80000039', '+65', 'demo.client.am@example.test', '1981-08-26', FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000040', 'Prospect', 'Demo Client AN', '80000040', '+65', 'demo.client.an@example.test', '1981-09-03', TRUE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000041', 'Client', 'Demo Client AO', '80000041', '+65', 'demo.client.ao@example.test', '1981-08-27', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000042', 'Client', 'Demo Client AP', '80000042', '+65', 'demo.client.ap@example.test', '1971-08-26', FALSE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000043', 'Prospect', 'Demo Client AQ', '80000043', '+65', 'demo.client.aq@example.test', '1971-08-27', FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000044', 'Client', 'Demo Client AR', '80000044', '+65', 'demo.client.ar@example.test', '1961-08-26', TRUE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000045', 'Client', 'Demo Client AS', '80000045', '+65', 'demo.client.as@example.test', '1961-08-27', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000046', 'Prospect', 'Demo Client AT', '80000046', '+65', 'demo.client.at@example.test', '1992-02-29', FALSE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000047', 'Client', 'Demo Client AU', '80000047', '+65', 'demo.client.au@example.test', '1971-08-22', FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000048', 'Client', 'Demo Client AV', '80000048', '+65', 'demo.client.av@example.test', '1967-01-01', TRUE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000049', 'Prospect', 'Demo Client AW', '80000049', '+65', 'demo.client.aw@example.test', '1962-06-08', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000050', 'Client', 'Demo Client AX', '80000050', '+65', 'demo.client.ax@example.test', '1961-11-15', FALSE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000051', 'Client', 'Demo Client AY', '80000051', '+65', 'demo.client.ay@example.test', '1957-04-22', FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000052', 'Prospect', 'Demo Client AZ', '80000052', '+65', 'demo.client.az@example.test', '1952-09-01', TRUE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000053', 'Client', 'Demo Client BA', '80000053', '+65', 'demo.client.ba@example.test', '1947-02-08', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000054', 'Client', 'Demo Client BB', '80000054', '+65', 'demo.client.bb@example.test', '1942-07-15', FALSE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000055', 'Prospect', 'Demo Client BC', '80000055', '+65', 'demo.client.bc@example.test', '2008-12-22', FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000056', 'Client', 'Demo Client BD', '80000056', '+65', 'demo.client.bd@example.test', '2002-05-01', TRUE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000057', 'Client', 'Demo Client BE', '80000057', '+65', 'demo.client.be@example.test', '1997-10-08', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000058', 'Prospect', 'Demo Client BF', '80000058', '+65', 'demo.client.bf@example.test', '1992-03-15', FALSE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000059', 'Client', 'Demo Client BG', '80000059', '+65', 'demo.client.bg@example.test', '1991-08-22', FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000060', 'Client', 'Demo Client BH', '80000060', '+65', 'demo.client.bh@example.test', '1987-01-01', TRUE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000061', 'Prospect', 'Demo Client BI', '80000061', '+65', 'demo.client.bi@example.test', '1982-06-08', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000062', 'Client', 'Demo Client BJ', '80000062', '+65', 'demo.client.bj@example.test', '1981-11-15', FALSE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000063', 'Client', 'Demo Client BK', '80000063', '+65', 'demo.client.bk@example.test', '1977-04-22', FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000064', 'Prospect', 'Demo Client BL', '80000064', '+65', 'demo.client.bl@example.test', '1972-09-01', TRUE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000065', 'Client', 'Demo Client BM', '80000065', '+65', 'demo.client.bm@example.test', '1971-02-08', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000066', 'Client', 'Demo Client BN', '80000066', '+65', 'demo.client.bn@example.test', '1967-07-15', FALSE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000067', 'Prospect', 'Demo Client BO', '80000067', '+65', 'demo.client.bo@example.test', '1962-12-22', FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000068', 'Client', 'Demo Client BP', '80000068', '+65', 'demo.client.bp@example.test', '1961-05-01', TRUE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000069', 'Client', 'Demo Client BQ', '80000069', '+65', 'demo.client.bq@example.test', '1957-10-08', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000070', 'Prospect', 'Demo Client BR', '80000070', '+65', 'demo.client.br@example.test', '1952-04-16', FALSE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000071', 'Client', 'Demo Client BS', '80000071', '+65', 'demo.client.bs@example.test', '1947-08-22', FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000072', 'Client', 'Demo Client BT', '80000072', '+65', 'demo.client.bt@example.test', '1942-01-01', TRUE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000073', 'Prospect', 'Demo Client BU', '80000073', '+65', 'demo.client.bu@example.test', '2008-06-08', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000074', 'Client', 'Demo Client BV', '80000074', '+65', 'demo.client.bv@example.test', '2002-11-15', FALSE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000075', 'Client', 'Demo Client BW', '80000075', '+65', 'demo.client.bw@example.test', '1997-04-22', FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000076', 'Prospect', 'Demo Client BX', '80000076', '+65', 'demo.client.bx@example.test', '1992-09-01', TRUE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000077', 'Client', 'Demo Client BY', '80000077', '+65', 'demo.client.by@example.test', '1991-02-08', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000078', 'Client', 'Demo Client BZ', '80000078', '+65', 'demo.client.bz@example.test', '1987-07-15', FALSE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000079', 'Prospect', 'Demo Client CA', '80000079', '+65', 'demo.client.ca@example.test', '1982-12-22', FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000080', 'Client', 'Demo Client CB', '80000080', '+65', 'demo.client.cb@example.test', '1981-05-01', TRUE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000081', 'Client', 'Demo Client CC', '80000081', '+65', 'demo.client.cc@example.test', '1977-10-08', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000082', 'Prospect', 'Demo Client CD', '80000082', '+65', 'demo.client.cd@example.test', '1972-03-15', FALSE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000083', 'Client', 'Demo Client CE', '80000083', '+65', 'demo.client.ce@example.test', '1971-08-22', FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000084', 'Client', 'Demo Client CF', '80000084', '+65', 'demo.client.cf@example.test', '1967-01-01', TRUE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000085', 'Prospect', 'Demo Client CG', '80000085', '+65', 'demo.client.cg@example.test', '1962-06-08', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000086', 'Client', 'Demo Client CH', '80000086', '+65', 'demo.client.ch@example.test', '1961-11-15', FALSE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000087', 'Client', 'Demo Client CI', '80000087', '+65', 'demo.client.ci@example.test', '1957-04-22', FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000088', 'Prospect', 'Demo Client CJ', '80000088', '+65', 'demo.client.cj@example.test', '1952-09-01', TRUE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000089', 'Client', 'Demo Client CK', '80000089', '+65', 'demo.client.ck@example.test', '1947-02-08', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000090', 'Client', 'Demo Client CL', '80000090', '+65', 'demo.client.cl@example.test', '1942-07-15', FALSE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000091', 'Prospect', 'Demo Client CM', '80000091', '+65', 'demo.client.cm@example.test', '2008-12-22', FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000092', 'Client', 'Demo Client CN', '80000092', '+65', 'demo.client.cn@example.test', '2002-05-01', TRUE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000093', 'Client', 'Demo Client CO', '80000093', '+65', 'demo.client.co@example.test', '1997-10-08', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000094', 'Prospect', 'Demo Client CP', '80000094', '+65', 'demo.client.cp@example.test', '1992-03-15', FALSE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000095', 'Client', 'Demo Client CQ', '80000095', '+65', 'demo.client.cq@example.test', '1991-08-22', FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000096', 'Client', 'Demo Client CR', '80000096', '+65', 'demo.client.cr@example.test', '1987-01-01', TRUE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000097', 'Prospect', 'Demo Client CS', '80000097', '+65', 'demo.client.cs@example.test', '1982-06-08', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000098', 'Client', 'Demo Client CT', '80000098', '+65', 'demo.client.ct@example.test', '1981-11-15', FALSE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000099', 'Client', 'Demo Client CU', '80000099', '+65', 'demo.client.cu@example.test', '1977-04-22', FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000100', 'Client', 'Demo Client CV', '80000100', '+65', 'demo.client.cv@example.test', '1972-10-09', TRUE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11')
ON CONFLICT (tenant_id, contact_id) DO NOTHING;

-- Correct only the untouched baseline record; never overwrite an edited DOB,
-- a soft-deleted client, or a record edited through the application.
UPDATE contact SET date_of_birth = DATE '1989-11-12'
WHERE tenant_id = 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'
  AND contact_id = 'd0000000-0000-0000-0000-000000000010'
  AND date_of_birth IS NULL AND NOT is_deleted
  AND updated_at = created_at
  AND full_name = 'Demo Client J' AND mobile = '90000000'
  AND email = 'demo.client.j@example.test'
  AND contact_type = 'Prospect' AND NOT opt_in_email AND NOT e_statement_opt_in;
