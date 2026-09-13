-- ====================================================================
-- NOVA ROOM MANAGEMENT SYSTEM - PostgreSQL / Supabase Core Schema (v3.0)
-- Phase 2: Database Architecture, Optimistic Concurrency Control, RLS & Realtime Broadcast
-- ====================================================================

BEGIN;

-- 1. Enable Required Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ====================================================================
-- 2. User & RBAC Accounts Table (public.nova_users)
-- ====================================================================
CREATE TABLE IF NOT EXISTS public.nova_users (
  employee_no TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  role TEXT NOT NULL CHECK (
    role IN (
      'SUPER_ADMIN', 'ADMIN', 'MANAGER', 'QM', 'INSPECTOR',
      'HOUSEMAN', 'ROOM_MAID', 'PUBLIC', 'DELIVERY', 'OUTSOURCE', 'PART_TIME',
      -- Legacy compatibility aliases:
      'ORDER'
    )
  ),
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  default_site TEXT NOT NULL DEFAULT 'SORA',
  allowed_sites TEXT[] NOT NULL DEFAULT ARRAY['SORA']::TEXT[],
  department TEXT,
  phone TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ====================================================================
-- 3. Live Room Status Table (public.nova_rooms_current)
-- Supports both legacy NOVA schema and enterprise specification
-- ====================================================================
CREATE TABLE IF NOT EXISTS public.nova_rooms_current (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  business_date DATE NOT NULL DEFAULT CURRENT_DATE,
  site TEXT NOT NULL DEFAULT 'SORA',
  room_no TEXT NOT NULL,
  building TEXT NOT NULL DEFAULT '1동',
  floor INTEGER NOT NULL DEFAULT 1,
  room_type TEXT NOT NULL DEFAULT 'Standard Double',
  
  -- Room Status (Occupancy & Physical Condition)
  room_status TEXT NOT NULL DEFAULT 'STOCK' CHECK (
    room_status IN (
      'STOCK', 'OCCUPIED',
      'CHECKED_OUT', 'VACANT_DIRTY',
      'VACANT_CLEAN', 'READY',
      'OOO', 'OUT_OF_ORDER'
    )
  ),
  
  -- Housekeeping Cleaning Progress
  cleaning_status TEXT NOT NULL DEFAULT 'WAITING' CHECK (
    cleaning_status IN (
      'WAITING', 'NOT_REQUIRED',
      'ASSIGNED', 'CLEANING_ASSIGNED',
      'CLEANING', 'CLEANING_IN_PROGRESS',
      'COMPLETED', 'CLEANING_COMPLETED',
      'QM_WAITING', 'INSPECTION_WAITING',
      'QM_INSPECTING', 'INSPECTION_IN_PROGRESS',
      'QM_COMPLETED', 'INSPECTION_COMPLETED',
      'REWORK'
    )
  ),
  
  cleaning_type TEXT NOT NULL DEFAULT 'NORMAL',
  assignment_type TEXT NOT NULL DEFAULT 'SOLO',
  
  -- Staff Assignments
  roommaid_employee_no TEXT REFERENCES public.nova_users(employee_no) ON DELETE SET NULL,
  secondary_roommaid_employee_no TEXT REFERENCES public.nova_users(employee_no) ON DELETE SET NULL,
  qm_employee_no TEXT REFERENCES public.nova_users(employee_no) ON DELETE SET NULL,
  inspector_employee_no TEXT REFERENCES public.nova_users(employee_no) ON DELETE SET NULL,
  
  -- Operational Details
  operational_status TEXT NOT NULL DEFAULT '',
  dnd BOOLEAN NOT NULL DEFAULT FALSE,
  guest_name TEXT,
  checkout_time TEXT DEFAULT '11:00',
  
  -- Timestamps for Lifecycle Audit
  cleaning_started_at TIMESTAMPTZ,
  cleaning_completed_at TIMESTAMPTZ,
  inspected_at TIMESTAMPTZ,
  
  -- Optimistic Concurrency Control (Version & Audit)
  version BIGINT NOT NULL DEFAULT 1,
  updated_by TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  -- Unique Constraint: One room entry per business date & site
  CONSTRAINT uq_nova_rooms_date_site_room UNIQUE (business_date, site, room_no)
);

-- ====================================================================
-- 4. Audit & Lifecycle Event Stream Table (public.nova_room_events)
-- ====================================================================
CREATE TABLE IF NOT EXISTS public.nova_room_events (
  id BIGSERIAL PRIMARY KEY,
  request_id TEXT NOT NULL UNIQUE,
  business_date DATE NOT NULL,
  site TEXT NOT NULL,
  room_no TEXT NOT NULL,
  action TEXT NOT NULL,
  before_status TEXT,
  after_status TEXT,
  employee_no TEXT NOT NULL,
  room_version BIGINT NOT NULL,
  detail JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ====================================================================
-- 5. Request Idempotency & Dedup Table (public.nova_request_dedup)
-- Prevents double-submits on network lag or fast repetitive clicks
-- ====================================================================
CREATE TABLE IF NOT EXISTS public.nova_request_dedup (
  request_id TEXT PRIMARY KEY,
  employee_no TEXT NOT NULL,
  action TEXT NOT NULL,
  response_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ====================================================================
-- 6. Houseman Orders Table (public.nova_houseman_orders)
-- ====================================================================
CREATE TABLE IF NOT EXISTS public.nova_houseman_orders (
  order_id TEXT PRIMARY KEY,
  business_date DATE NOT NULL DEFAULT CURRENT_DATE,
  site TEXT NOT NULL DEFAULT 'SORA',
  room_no TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT 'TOWEL',
  items JSONB NOT NULL DEFAULT '[]'::JSONB,
  item_summary TEXT NOT NULL DEFAULT '',
  quantity INTEGER NOT NULL DEFAULT 1,
  note TEXT NOT NULL DEFAULT '',
  requester TEXT NOT NULL DEFAULT '프론트',
  
  assigned_employee_no TEXT REFERENCES public.nova_users(employee_no) ON DELETE SET NULL,
  assigned_name TEXT NOT NULL DEFAULT '',
  
  status_code TEXT NOT NULL DEFAULT 'REGISTERED' CHECK (
    status_code IN ('REGISTERED', 'ASSIGNED', 'ACCEPTED', 'PROCESSING', 'COMPLETED', 'UNABLE')
  ),
  important BOOLEAN NOT NULL DEFAULT FALSE,
  version BIGINT NOT NULL DEFAULT 1,
  
  registered_by TEXT NOT NULL,
  registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  accepted_at TIMESTAMPTZ,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  unable_reason TEXT NOT NULL DEFAULT '',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ====================================================================
-- 7. High-Performance Query Indexes
-- Designed specifically for 1,500~3,000 rooms and concurrent filtering
-- ====================================================================
CREATE INDEX IF NOT EXISTS idx_nova_rooms_site_date_room 
  ON public.nova_rooms_current (site, business_date, room_no);

CREATE INDEX IF NOT EXISTS idx_nova_rooms_status_cleaning 
  ON public.nova_rooms_current (site, business_date, room_status, cleaning_status);

CREATE INDEX IF NOT EXISTS idx_nova_rooms_maid 
  ON public.nova_rooms_current (site, business_date, roommaid_employee_no);

CREATE INDEX IF NOT EXISTS idx_nova_rooms_qm 
  ON public.nova_rooms_current (site, business_date, qm_employee_no);

CREATE INDEX IF NOT EXISTS idx_nova_rooms_floor 
  ON public.nova_rooms_current (site, business_date, floor, building);

CREATE INDEX IF NOT EXISTS idx_nova_room_events_room 
  ON public.nova_room_events (site, business_date, room_no, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_nova_houseman_orders_assigned 
  ON public.nova_houseman_orders (site, business_date, assigned_employee_no, status_code);

-- ====================================================================
-- 8. Supabase Realtime Broadcast Trigger Functions
-- ====================================================================
CREATE OR REPLACE FUNCTION public.nova_rooms_current_broadcast()
RETURNS TRIGGER
SECURITY DEFINER
SET search_path = ''
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    PERFORM realtime.broadcast_changes(
      'nova:site:' || OLD.site || ':rooms',
      TG_OP, TG_OP, TG_TABLE_NAME, TG_TABLE_SCHEMA, OLD, OLD
    );
    RETURN OLD;
  END IF;

  PERFORM realtime.broadcast_changes(
    'nova:site:' || NEW.site || ':rooms',
    TG_OP, TG_OP, TG_TABLE_NAME, TG_TABLE_SCHEMA, NEW, OLD
  );
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_nova_rooms_current_broadcast ON public.nova_rooms_current;
CREATE TRIGGER trg_nova_rooms_current_broadcast
AFTER INSERT OR UPDATE OR DELETE
ON public.nova_rooms_current
FOR EACH ROW EXECUTE FUNCTION public.nova_rooms_current_broadcast();

-- Houseman order broadcast
CREATE OR REPLACE FUNCTION public.nova_houseman_order_broadcast()
RETURNS TRIGGER
SECURITY DEFINER
SET search_path = ''
LANGUAGE plpgsql
AS $$
BEGIN
  PERFORM realtime.broadcast_changes(
    'nova:site:' || NEW.site || ':rooms',
    TG_OP, TG_OP, TG_TABLE_NAME, TG_TABLE_SCHEMA, NEW, OLD
  );
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_nova_houseman_orders_broadcast ON public.nova_houseman_orders;
CREATE TRIGGER trg_nova_houseman_orders_broadcast
AFTER INSERT OR UPDATE
ON public.nova_houseman_orders
FOR EACH ROW EXECUTE FUNCTION public.nova_houseman_order_broadcast();

-- ====================================================================
-- 9. Row Level Security (RLS) & Realtime Policies
-- ====================================================================
ALTER TABLE public.nova_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.nova_rooms_current ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.nova_room_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.nova_request_dedup ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.nova_houseman_orders ENABLE ROW LEVEL SECURITY;

-- Allow service role full access
DROP POLICY IF EXISTS "service_role_all_users" ON public.nova_users;
CREATE POLICY "service_role_all_users" ON public.nova_users FOR ALL TO service_role USING (true);

DROP POLICY IF EXISTS "service_role_all_rooms" ON public.nova_rooms_current;
CREATE POLICY "service_role_all_rooms" ON public.nova_rooms_current FOR ALL TO service_role USING (true);

DROP POLICY IF EXISTS "service_role_all_events" ON public.nova_room_events;
CREATE POLICY "service_role_all_events" ON public.nova_room_events FOR ALL TO service_role USING (true);

DROP POLICY IF EXISTS "service_role_all_dedup" ON public.nova_request_dedup;
CREATE POLICY "service_role_all_dedup" ON public.nova_request_dedup FOR ALL TO service_role USING (true);

DROP POLICY IF EXISTS "service_role_all_orders" ON public.nova_houseman_orders;
CREATE POLICY "service_role_all_orders" ON public.nova_houseman_orders FOR ALL TO service_role USING (true);

COMMIT;
