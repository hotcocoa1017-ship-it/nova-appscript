-- ====================================================================
-- NOVA ROOM MANAGEMENT SYSTEM - Seed Data (v3.0)
-- Initializes staff accounts and 60 realistic rooms for SORA resort
-- ====================================================================

BEGIN;

-- 1. Seed Staff Accounts
INSERT INTO public.nova_users (employee_no, name, role, enabled, default_site, allowed_sites, phone)
VALUES
  ('ADMIN-01', '총괄관리자', 'SUPER_ADMIN', TRUE, 'SORA', ARRAY['SORA']::TEXT[], '010-1111-0001'),
  ('MGR-01', '객실지배인', 'MANAGER', TRUE, 'SORA', ARRAY['SORA']::TEXT[], '010-1111-0002'),
  ('QM-2001', '강QM', 'QM', TRUE, 'SORA', ARRAY['SORA']::TEXT[], '010-2222-2001'),
  ('QM-2002', '이인스펙터', 'INSPECTOR', TRUE, 'SORA', ARRAY['SORA']::TEXT[], '010-2222-2002'),
  ('1001', '김순자', 'ROOM_MAID', TRUE, 'SORA', ARRAY['SORA']::TEXT[], '010-3456-1001'),
  ('1002', '박영희', 'ROOM_MAID', TRUE, 'SORA', ARRAY['SORA']::TEXT[], '010-3456-1002'),
  ('1003', '이정숙', 'ROOM_MAID', TRUE, 'SORA', ARRAY['SORA']::TEXT[], '010-3456-1003'),
  ('1004', '최미경', 'ROOM_MAID', TRUE, 'SORA', ARRAY['SORA']::TEXT[], '010-3456-1004'),
  ('hm-1', '강민우', 'HOUSEMAN', TRUE, 'SORA', ARRAY['SORA']::TEXT[], '010-8890-2001'),
  ('hm-2', '정태양', 'HOUSEMAN', TRUE, 'SORA', ARRAY['SORA']::TEXT[], '010-8890-2002'),
  ('hm-3', '한지훈', 'HOUSEMAN', TRUE, 'SORA', ARRAY['SORA']::TEXT[], '010-8890-2003'),
  ('hm-4', '조진우', 'HOUSEMAN', TRUE, 'SORA', ARRAY['SORA']::TEXT[], '010-8890-2004')
ON CONFLICT (employee_no) DO UPDATE
SET name = EXCLUDED.name,
    role = EXCLUDED.role,
    phone = EXCLUDED.phone;

-- 2. Seed 60 Realistic Rooms across 5 floors (2F~6F)
INSERT INTO public.nova_rooms_current (
  business_date, site, room_no, building, floor, room_type,
  room_status, cleaning_status, cleaning_type, assignment_type,
  roommaid_employee_no, qm_employee_no, operational_status, dnd, guest_name, checkout_time, version
)
VALUES
  -- 2F
  ('2026-09-13', 'SORA', '201', '2동', 2, 'Standard Double', 'STOCK', 'NOT_REQUIRED', 'NORMAL', 'SOLO', '1001', 'QM-2001', '', FALSE, '김민수', '11:00', 1),
  ('2026-09-13', 'SORA', '202', '2동', 2, 'Standard Twin', 'STOCK', 'CLEANING', 'NORMAL', 'SOLO', '1001', 'QM-2001', '', FALSE, '이서연', '11:00', 1),
  ('2026-09-13', 'SORA', '203', '2동', 2, 'Deluxe King', 'STOCK', 'NOT_REQUIRED', 'NORMAL', 'SOLO', '1001', 'QM-2001', '', TRUE, 'Park Smith', '11:00', 1),
  ('2026-09-13', 'SORA', '204', '2동', 2, 'Executive Suite', 'CHECKED_OUT', 'WAITING', 'NORMAL', 'SOLO', NULL, 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '205', '2동', 2, 'Standard Double', 'CHECKED_OUT', 'WAITING', 'NORMAL', 'SOLO', NULL, 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '206', '2동', 2, 'Standard Twin', 'CHECKED_OUT', 'CLEANING', 'NORMAL', 'SOLO', '1001', 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '207', '2동', 2, 'Deluxe King', 'CHECKED_OUT', 'QM_WAITING', 'NORMAL', 'SOLO', '1001', 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '208', '2동', 2, 'Executive Suite', 'VACANT_CLEAN', 'QM_COMPLETED', 'NORMAL', 'SOLO', '1001', 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '209', '2동', 2, 'Standard Double', 'VACANT_CLEAN', 'QM_COMPLETED', 'NORMAL', 'SOLO', '1001', 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '210', '2동', 2, 'Standard Twin', 'STOCK', 'NOT_REQUIRED', 'NORMAL', 'SOLO', '1001', 'QM-2001', '', FALSE, '정다은', '11:00', 1),
  ('2026-09-13', 'SORA', '211', '2동', 2, 'Deluxe King', 'STOCK', 'NOT_REQUIRED', 'NORMAL', 'SOLO', '1001', 'QM-2001', '', FALSE, '최현우', '11:00', 1),
  ('2026-09-13', 'SORA', '212', '2동', 2, 'Executive Suite', 'VACANT_CLEAN', 'QM_COMPLETED', 'NORMAL', 'SOLO', '1001', 'QM-2001', '', FALSE, NULL, '11:00', 1),

  -- 3F
  ('2026-09-13', 'SORA', '301', '3동', 3, 'Standard Double', 'STOCK', 'NOT_REQUIRED', 'NORMAL', 'SOLO', '1002', 'QM-2001', '', FALSE, 'Sarah Jenkins', '11:00', 1),
  ('2026-09-13', 'SORA', '302', '3동', 3, 'Standard Twin', 'STOCK', 'CLEANING', 'NORMAL', 'SOLO', '1002', 'QM-2001', '', FALSE, '김민수', '11:00', 1),
  ('2026-09-13', 'SORA', '303', '3동', 3, 'Deluxe King', 'STOCK', 'NOT_REQUIRED', 'NORMAL', 'SOLO', '1002', 'QM-2001', '', FALSE, '이서연', '11:00', 1),
  ('2026-09-13', 'SORA', '304', '3동', 3, 'Executive Suite', 'CHECKED_OUT', 'WAITING', 'NORMAL', 'SOLO', NULL, 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '305', '3동', 3, 'Standard Double', 'CHECKED_OUT', 'WAITING', 'NORMAL', 'SOLO', NULL, 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '306', '3동', 3, 'Standard Twin', 'CHECKED_OUT', 'CLEANING', 'NORMAL', 'SOLO', '1002', 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '307', '3동', 3, 'Deluxe King', 'CHECKED_OUT', 'QM_WAITING', 'NORMAL', 'SOLO', '1002', 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '308', '3동', 3, 'Executive Suite', 'OOO', 'NOT_REQUIRED', 'NORMAL', 'SOLO', NULL, 'QM-2001', '세면대 수전 누수 점검 중', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '309', '3동', 3, 'Standard Double', 'STOCK', 'NOT_REQUIRED', 'NORMAL', 'SOLO', '1002', 'QM-2001', '', TRUE, 'Tanaka Ken', '11:00', 1),
  ('2026-09-13', 'SORA', '310', '3동', 3, 'Standard Twin', 'VACANT_CLEAN', 'QM_COMPLETED', 'NORMAL', 'SOLO', '1002', 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '311', '3동', 3, 'Deluxe King', 'VACANT_CLEAN', 'QM_COMPLETED', 'NORMAL', 'SOLO', '1002', 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '312', '3동', 3, 'Executive Suite', 'VACANT_CLEAN', 'QM_COMPLETED', 'NORMAL', 'SOLO', '1002', 'QM-2001', '', FALSE, NULL, '11:00', 1),

  -- 4F
  ('2026-09-13', 'SORA', '401', '4동', 4, 'Standard Double', 'STOCK', 'NOT_REQUIRED', 'NORMAL', 'SOLO', '1003', 'QM-2001', '', FALSE, '정다은', '11:00', 1),
  ('2026-09-13', 'SORA', '402', '4동', 4, 'Standard Twin', 'CHECKED_OUT', 'WAITING', 'NORMAL', 'SOLO', NULL, 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '403', '4동', 4, 'Deluxe King', 'CHECKED_OUT', 'CLEANING', 'NORMAL', 'SOLO', '1003', 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '404', '4동', 4, 'Executive Suite', 'CHECKED_OUT', 'QM_WAITING', 'NORMAL', 'SOLO', '1003', 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '405', '4동', 4, 'Standard Double', 'VACANT_CLEAN', 'QM_COMPLETED', 'NORMAL', 'SOLO', '1003', 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '406', '4동', 4, 'Standard Twin', 'VACANT_CLEAN', 'QM_COMPLETED', 'NORMAL', 'SOLO', '1003', 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '407', '4동', 4, 'Deluxe King', 'STOCK', 'NOT_REQUIRED', 'NORMAL', 'SOLO', '1003', 'QM-2001', '', FALSE, '최현우', '11:00', 1),
  ('2026-09-13', 'SORA', '408', '4동', 4, 'Executive Suite', 'STOCK', 'NOT_REQUIRED', 'NORMAL', 'SOLO', '1003', 'QM-2001', '', FALSE, 'Sarah Jenkins', '11:00', 1),
  ('2026-09-13', 'SORA', '409', '4동', 4, 'Standard Double', 'CHECKED_OUT', 'WAITING', 'NORMAL', 'SOLO', NULL, 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '410', '4동', 4, 'Standard Twin', 'CHECKED_OUT', 'CLEANING', 'NORMAL', 'SOLO', '1003', 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '411', '4동', 4, 'Deluxe King', 'VACANT_CLEAN', 'QM_COMPLETED', 'NORMAL', 'SOLO', '1003', 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '412', '4동', 4, 'Executive Suite', 'VACANT_CLEAN', 'QM_COMPLETED', 'NORMAL', 'SOLO', '1003', 'QM-2001', '', FALSE, NULL, '11:00', 1),

  -- 5F
  ('2026-09-13', 'SORA', '501', '5동', 5, 'Standard Double', 'STOCK', 'NOT_REQUIRED', 'NORMAL', 'SOLO', '1004', 'QM-2001', '', FALSE, '김민수', '11:00', 1),
  ('2026-09-13', 'SORA', '502', '5동', 5, 'Standard Twin', 'CHECKED_OUT', 'WAITING', 'NORMAL', 'SOLO', NULL, 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '503', '5동', 5, 'Deluxe King', 'CHECKED_OUT', 'CLEANING', 'NORMAL', 'SOLO', '1004', 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '504', '5동', 5, 'Executive Suite', 'CHECKED_OUT', 'QM_WAITING', 'NORMAL', 'SOLO', '1004', 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '505', '5동', 5, 'Standard Double', 'OOO', 'NOT_REQUIRED', 'NORMAL', 'SOLO', NULL, 'QM-2001', '에어컨 냉매 교체 필요', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '506', '5동', 5, 'Standard Twin', 'VACANT_CLEAN', 'QM_COMPLETED', 'NORMAL', 'SOLO', '1004', 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '507', '5동', 5, 'Deluxe King', 'STOCK', 'NOT_REQUIRED', 'NORMAL', 'SOLO', '1004', 'QM-2001', '', FALSE, 'Park Smith', '11:00', 1),
  ('2026-09-13', 'SORA', '508', '5동', 5, 'Executive Suite', 'STOCK', 'NOT_REQUIRED', 'NORMAL', 'SOLO', '1004', 'QM-2001', '', FALSE, 'Tanaka Ken', '11:00', 1),
  ('2026-09-13', 'SORA', '509', '5동', 5, 'Standard Double', 'CHECKED_OUT', 'WAITING', 'NORMAL', 'SOLO', NULL, 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '510', '5동', 5, 'Standard Twin', 'CHECKED_OUT', 'CLEANING', 'NORMAL', 'SOLO', '1004', 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '511', '5동', 5, 'Deluxe King', 'VACANT_CLEAN', 'QM_COMPLETED', 'NORMAL', 'SOLO', '1004', 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '512', '5동', 5, 'Executive Suite', 'VACANT_CLEAN', 'QM_COMPLETED', 'NORMAL', 'SOLO', '1004', 'QM-2001', '', FALSE, NULL, '11:00', 1),

  -- 6F
  ('2026-09-13', 'SORA', '601', '6동', 6, 'Executive Suite', 'STOCK', 'NOT_REQUIRED', 'NORMAL', 'SOLO', '1004', 'QM-2001', '', FALSE, '정다은', '11:00', 1),
  ('2026-09-13', 'SORA', '602', '6동', 6, 'Deluxe King', 'CHECKED_OUT', 'WAITING', 'NORMAL', 'SOLO', NULL, 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '603', '6동', 6, 'Deluxe King', 'CHECKED_OUT', 'CLEANING', 'NORMAL', 'SOLO', '1004', 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '604', '6동', 6, 'Executive Suite', 'CHECKED_OUT', 'QM_WAITING', 'NORMAL', 'SOLO', '1004', 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '605', '6동', 6, 'Standard Double', 'VACANT_CLEAN', 'QM_COMPLETED', 'NORMAL', 'SOLO', '1004', 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '606', '6동', 6, 'Standard Twin', 'VACANT_CLEAN', 'QM_COMPLETED', 'NORMAL', 'SOLO', '1004', 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '607', '6동', 6, 'Deluxe King', 'STOCK', 'NOT_REQUIRED', 'NORMAL', 'SOLO', '1004', 'QM-2001', '', FALSE, '이서연', '11:00', 1),
  ('2026-09-13', 'SORA', '608', '6동', 6, 'Executive Suite', 'STOCK', 'NOT_REQUIRED', 'NORMAL', 'SOLO', '1004', 'QM-2001', '', FALSE, '최현우', '11:00', 1),
  ('2026-09-13', 'SORA', '609', '6동', 6, 'Standard Double', 'CHECKED_OUT', 'WAITING', 'NORMAL', 'SOLO', NULL, 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '610', '6동', 6, 'Standard Twin', 'CHECKED_OUT', 'CLEANING', 'NORMAL', 'SOLO', '1004', 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '611', '6동', 6, 'Deluxe King', 'VACANT_CLEAN', 'QM_COMPLETED', 'NORMAL', 'SOLO', '1004', 'QM-2001', '', FALSE, NULL, '11:00', 1),
  ('2026-09-13', 'SORA', '612', '6동', 6, 'Executive Suite', 'VACANT_CLEAN', 'QM_COMPLETED', 'NORMAL', 'SOLO', '1004', 'QM-2001', '', FALSE, NULL, '11:00', 1)
ON CONFLICT (business_date, site, room_no) DO UPDATE
SET room_status = EXCLUDED.room_status,
    cleaning_status = EXCLUDED.cleaning_status,
    roommaid_employee_no = EXCLUDED.roommaid_employee_no,
    operational_status = EXCLUDED.operational_status,
    guest_name = EXCLUDED.guest_name,
    version = EXCLUDED.version;

COMMIT;
