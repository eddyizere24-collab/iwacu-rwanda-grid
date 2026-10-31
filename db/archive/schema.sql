-- =============================================================================
-- IWACU RWANDA — PostgreSQL + PostGIS Schema (Nationwide administrative boundaries)
-- =============================================================================
-- Strict compliance: NCSA Law No. 058/2021, Zero PII to LLM, Optimistic Locking
-- SRID 4326, GiST indexes, Row Level Security, Temporal leaders
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS ltree;          -- Materialized path for hierarchy

-- -----------------------------------------------------------------------------
-- ENUMS
-- -----------------------------------------------------------------------------
CREATE TYPE boundary_level AS ENUM (
  'country',   -- ADM0
  'province',  -- ADM1
  'district',  -- ADM2
  'sector',    -- ADM3
  'cell',      -- ADM4
  'village'    -- ADM5
);

CREATE TYPE leader_role AS ENUM (
  'Village Leader',
  'Cell Executive Secretary',
  'Sector Executive Secretary',
  'Mayor',
  'Vice Mayor',
  'District Executive Secretary',
  'Other'
);

CREATE TYPE audit_action AS ENUM (
  'INSERT',
  'UPDATE',
  'DELETE',
  'LOGIN',
  'LOGOUT',
  'CONFLICT'
);

-- -----------------------------------------------------------------------------
-- BOUNDARIES (Administrative polygons with materialized path)
-- -----------------------------------------------------------------------------
CREATE TABLE boundaries (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  scope_code      TEXT NOT NULL UNIQUE,                 -- e.g. "RW-01-01-01-001"
  path            LTREE NOT NULL,                       -- Materialized path: RW.01.01.01.001
  name_kiny       TEXT NOT NULL,
  name_eng        TEXT,
  level           boundary_level NOT NULL,
  parent_id       UUID REFERENCES boundaries(id) ON DELETE RESTRICT,
  geom            geometry(MultiPolygon, 4326) NOT NULL,
  area_m2         DOUBLE PRECISION GENERATED ALWAYS AS (ST_Area(geom::geography)) STORED,
  valid_from      TIMESTAMPTZ NOT NULL DEFAULT now(),
  valid_to        TIMESTAMPTZ,                          -- NULL = currently valid
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  version         INTEGER NOT NULL DEFAULT 1,           -- Optimistic locking

  CONSTRAINT boundaries_valid_period CHECK (valid_to IS NULL OR valid_to > valid_from),
  CONSTRAINT boundaries_scope_format CHECK (scope_code ~ '^RW(-[0-9A-Z]{2,})*$')
);

-- GiST spatial index (critical for intersection queries)
CREATE INDEX idx_boundaries_geom_gist ON boundaries USING GIST (geom);

-- Hierarchy & lookup indexes
CREATE INDEX idx_boundaries_path ON boundaries USING GIST (path);
CREATE INDEX idx_boundaries_scope_code ON boundaries (scope_code);
CREATE INDEX idx_boundaries_level ON boundaries (level);
CREATE INDEX idx_boundaries_parent ON boundaries (parent_id);
CREATE INDEX idx_boundaries_valid ON boundaries (valid_from, valid_to)
  WHERE valid_to IS NULL;

COMMENT ON TABLE boundaries IS 'Administrative boundaries built from NISR 2022 village polygons, with parent cell, sector and district geometries aggregated in PostGIS. SRID 4326.';
COMMENT ON COLUMN boundaries.path IS 'ltree materialized path for fast ancestor/descendant queries';
COMMENT ON COLUMN boundaries.version IS 'Optimistic locking version for concurrent admin edits';

-- -----------------------------------------------------------------------------
-- LEADERS (Temporal table — valid_from / valid_to)
-- -----------------------------------------------------------------------------
CREATE TABLE leaders (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  scope_code      TEXT NOT NULL REFERENCES boundaries(scope_code) ON DELETE RESTRICT,
  first_name      TEXT NOT NULL,
  last_name       TEXT NOT NULL,
  role            leader_role NOT NULL,
  phone_number    TEXT,                                 -- Stored encrypted / masked at app layer
  email           TEXT,
  photo_url       TEXT,
  valid_from      TIMESTAMPTZ NOT NULL DEFAULT now(),
  valid_to        TIMESTAMPTZ,                          -- NULL = currently active
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by      UUID REFERENCES auth.users(id),
  updated_by      UUID REFERENCES auth.users(id),
  version         INTEGER NOT NULL DEFAULT 1,           -- Optimistic locking

  CONSTRAINT leaders_valid_period CHECK (valid_to IS NULL OR valid_to > valid_from),
  CONSTRAINT leaders_phone_format CHECK (
    phone_number IS NULL OR phone_number ~ '^\+250[0-9]{9}$'
  )
);

CREATE INDEX idx_leaders_scope_code ON leaders (scope_code);
CREATE INDEX idx_leaders_valid ON leaders (scope_code, valid_from, valid_to)
  WHERE valid_to IS NULL;
CREATE INDEX idx_leaders_role ON leaders (role);

COMMENT ON TABLE leaders IS 'Temporal leaders table. Only one active leader per scope_code+role at a time enforced by application logic + unique partial index.';
COMMENT ON COLUMN leaders.phone_number IS 'Never returned raw to frontend. Backend masks; tel: link only on explicit user action.';
COMMENT ON COLUMN leaders.version IS 'Optimistic locking. Concurrent edit → 409 Conflict + diff.';

-- Partial unique index: only one currently active leader per scope+role
CREATE UNIQUE INDEX idx_leaders_active_unique
  ON leaders (scope_code, role)
  WHERE valid_to IS NULL;

-- -----------------------------------------------------------------------------
-- ADMIN PROFILES (extends Supabase auth.users)
-- -----------------------------------------------------------------------------
CREATE TABLE admin_profiles (
  user_id         UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  full_name       TEXT NOT NULL,
  scope_code      TEXT NOT NULL,                        -- Prefix they can manage, e.g. "RW-01"
  is_super_admin  BOOLEAN NOT NULL DEFAULT false,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_login_at   TIMESTAMPTZ,

  CONSTRAINT admin_scope_format CHECK (scope_code ~ '^RW(-[0-9A-Z]{2,})*$')
);

CREATE INDEX idx_admin_profiles_scope ON admin_profiles (scope_code);

COMMENT ON TABLE admin_profiles IS 'RBAC mapping. District admin with scope_code=RW-01 can only UPDATE leaders where leaders.scope_code LIKE RW-01%';

-- -----------------------------------------------------------------------------
-- AUDIT LOGS
-- -----------------------------------------------------------------------------
CREATE TABLE audit_logs (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  actor_id        UUID REFERENCES auth.users(id),
  action          audit_action NOT NULL,
  table_name      TEXT NOT NULL,
  record_id       UUID,
  old_data        JSONB,
  new_data        JSONB,
  ip_address      INET,
  user_agent      TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_logs_actor ON audit_logs (actor_id);
CREATE INDEX idx_audit_logs_table_record ON audit_logs (table_name, record_id);
CREATE INDEX idx_audit_logs_created ON audit_logs (created_at DESC);

-- -----------------------------------------------------------------------------
-- HELPER FUNCTIONS
-- -----------------------------------------------------------------------------

-- Updated_at trigger
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_boundaries_updated
  BEFORE UPDATE ON boundaries
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_leaders_updated
  BEFORE UPDATE ON leaders
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_admin_profiles_updated
  BEFORE UPDATE ON admin_profiles
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Optimistic locking helper (call from API before update)
CREATE OR REPLACE FUNCTION check_version(
  p_table TEXT,
  p_id UUID,
  p_expected_version INTEGER
) RETURNS BOOLEAN AS $$
DECLARE
  current_version INTEGER;
BEGIN
  EXECUTE format('SELECT version FROM %I WHERE id = $1', p_table)
    INTO current_version
    USING p_id;

  IF current_version IS NULL THEN
    RAISE EXCEPTION 'Record not found';
  END IF;

  IF current_version <> p_expected_version THEN
    RETURN false;  -- Caller must return 409 Conflict
  END IF;

  RETURN true;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- -----------------------------------------------------------------------------
-- ROW LEVEL SECURITY (RLS)
-- -----------------------------------------------------------------------------
ALTER TABLE boundaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE leaders ENABLE ROW LEVEL SECURITY;
ALTER TABLE admin_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

-- BOUNDARIES: Public read (anonymous citizens)
CREATE POLICY "boundaries_public_read"
  ON boundaries FOR SELECT
  TO anon, authenticated
  USING (valid_to IS NULL);

-- BOUNDARIES: Only super-admin can write (MVP; future: scoped)
CREATE POLICY "boundaries_super_admin_write"
  ON boundaries FOR ALL
  TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM admin_profiles ap
      WHERE ap.user_id = auth.uid() AND ap.is_super_admin = true
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM admin_profiles ap
      WHERE ap.user_id = auth.uid() AND ap.is_super_admin = true
    )
  );

-- LEADERS: Public read of currently active leaders only
CREATE POLICY "leaders_public_read"
  ON leaders FOR SELECT
  TO anon, authenticated
  USING (valid_to IS NULL);

-- LEADERS: Scoped admin write (prefix match on scope_code)
CREATE POLICY "leaders_scoped_admin_write"
  ON leaders FOR ALL
  TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM admin_profiles ap
      WHERE ap.user_id = auth.uid()
        AND (
          ap.is_super_admin = true
          OR leaders.scope_code LIKE ap.scope_code || '%'
        )
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM admin_profiles ap
      WHERE ap.user_id = auth.uid()
        AND (
          ap.is_super_admin = true
          OR leaders.scope_code LIKE ap.scope_code || '%'
        )
    )
  );

-- ADMIN_PROFILES: Users can read their own profile; super-admin can manage all
CREATE POLICY "admin_profiles_self_read"
  ON admin_profiles FOR SELECT
  TO authenticated
  USING (user_id = auth.uid() OR EXISTS (
    SELECT 1 FROM admin_profiles ap
    WHERE ap.user_id = auth.uid() AND ap.is_super_admin = true
  ));

CREATE POLICY "admin_profiles_super_admin_write"
  ON admin_profiles FOR ALL
  TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM admin_profiles ap
      WHERE ap.user_id = auth.uid() AND ap.is_super_admin = true
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM admin_profiles ap
      WHERE ap.user_id = auth.uid() AND ap.is_super_admin = true
    )
  );

-- AUDIT_LOGS: Only super-admin can read
CREATE POLICY "audit_logs_super_admin_read"
  ON audit_logs FOR SELECT
  TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM admin_profiles ap
      WHERE ap.user_id = auth.uid() AND ap.is_super_admin = true
    )
  );

-- Insert into audit_logs is done via SECURITY DEFINER functions only
CREATE POLICY "audit_logs_no_direct_write"
  ON audit_logs FOR INSERT
  TO authenticated
  WITH CHECK (false);

-- -----------------------------------------------------------------------------
-- USEFUL VIEWS
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_active_leaders AS
SELECT
  l.id,
  l.scope_code,
  b.name_kiny AS boundary_name_kiny,
  b.name_eng  AS boundary_name_eng,
  b.level,
  l.first_name,
  l.last_name,
  l.role,
  l.email,
  l.photo_url,
  l.valid_from,
  l.version
FROM leaders l
JOIN boundaries b ON b.scope_code = l.scope_code
WHERE l.valid_to IS NULL
  AND b.valid_to IS NULL;

COMMENT ON VIEW v_active_leaders IS 'Active leaders joined with boundary names. Phone numbers intentionally excluded.';

-- -----------------------------------------------------------------------------
-- GEOSPATIAL CONFIDENCE FUNCTION (used by /api/locate)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION calculate_location_confidence(
  p_lng DOUBLE PRECISION,
  p_lat DOUBLE PRECISION,
  p_accuracy_m DOUBLE PRECISION
)
RETURNS TABLE (
  scope_code TEXT,
  name_kiny TEXT,
  name_eng TEXT,
  level boundary_level,
  confidence NUMERIC,
  intersection_area_m2 DOUBLE PRECISION,
  path LTREE
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  WITH circle AS (
    SELECT ST_Buffer(
      ST_SetSRID(ST_MakePoint(p_lng, p_lat), 4326)::geography,
      p_accuracy_m
    )::geometry AS geom,
    ST_Area(
      ST_Buffer(
        ST_SetSRID(ST_MakePoint(p_lng, p_lat), 4326)::geography,
        p_accuracy_m
      )
    ) AS area_m2
  ),
  intersections AS (
    SELECT
      b.scope_code,
      b.name_kiny,
      b.name_eng,
      b.level,
      b.path,
      ST_Area(
        ST_Intersection(b.geom::geography, c.geom::geography)
      ) AS inter_area_m2,
      c.area_m2 AS circle_area_m2
    FROM boundaries b
    CROSS JOIN circle c
    WHERE b.valid_to IS NULL
      AND b.level = 'village'
      AND ST_Intersects(b.geom, c.geom)
  )
  SELECT
    i.scope_code,
    i.name_kiny,
    i.name_eng,
    i.level,
    ROUND(
      (LEAST(i.inter_area_m2 / NULLIF(i.circle_area_m2, 0), 1.0) * 100)::numeric,
      2
    ) AS confidence,
    i.inter_area_m2 AS intersection_area_m2,
    i.path
  FROM intersections i
  WHERE i.inter_area_m2 > 0
  ORDER BY confidence DESC;
$$;

GRANT EXECUTE ON FUNCTION calculate_location_confidence(DOUBLE PRECISION, DOUBLE PRECISION, DOUBLE PRECISION)
  TO anon, authenticated, service_role;

-- -----------------------------------------------------------------------------
-- BOUNDARY INGEST HELPER (used by scripts/ingest-boundaries.ts)
-- Applies ST_MakeValid + forces SRID 4326
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION ingest_boundary_feature(
  p_scope_code TEXT,
  p_path       TEXT,
  p_name_kiny  TEXT,
  p_name_eng   TEXT,
  p_level      TEXT,
  p_wkt        TEXT
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_geom geometry;
  v_id   UUID;
BEGIN
  -- Parse WKT, force 4326, make valid, and cast to MultiPolygon
  v_geom := ST_Multi(
    ST_CollectionExtract(
      ST_MakeValid(
        ST_SetSRID(ST_GeomFromText(p_wkt), 4326)
      ),
      3  -- extract polygonal geometries
    )
  );

  IF v_geom IS NULL OR ST_IsEmpty(v_geom) THEN
    RAISE EXCEPTION 'Invalid or empty geometry for scope_code %', p_scope_code;
  END IF;

  INSERT INTO boundaries (
    scope_code, path, name_kiny, name_eng, level, geom
  ) VALUES (
    p_scope_code,
    p_path::ltree,
    p_name_kiny,
    p_name_eng,
    p_level::boundary_level,
    v_geom
  )
  ON CONFLICT (scope_code) DO UPDATE SET
    path       = EXCLUDED.path,
    name_kiny  = EXCLUDED.name_kiny,
    name_eng   = EXCLUDED.name_eng,
    level      = EXCLUDED.level,
    geom       = EXCLUDED.geom,
    updated_at = now(),
    version    = boundaries.version + 1
  RETURNING id INTO v_id;

  RETURN v_id;
END;
$$;

GRANT EXECUTE ON FUNCTION ingest_boundary_feature(TEXT, TEXT, TEXT, TEXT, TEXT, TEXT)
  TO service_role;


-- -----------------------------------------------------------------------------
-- NATIONWIDE BATCH INGEST (used by scripts/ingest-boundaries.ts)
-- Inserts village polygons and incrementally dissolves them into parent
-- cell/sector/district boundaries. Re-running is safe (idempotent upsert).
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION ingest_boundary_batch(p_features JSONB)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_village_count INTEGER := 0;
BEGIN
  IF jsonb_typeof(p_features) <> 'array' THEN
    RAISE EXCEPTION 'p_features must be a JSON array';
  END IF;

  -- Upsert the village polygons after validating/fixing geometry.
  WITH parsed AS (
    SELECT *
    FROM jsonb_to_recordset(p_features) AS x(
      scope_code TEXT,
      path TEXT,
      name_kiny TEXT,
      name_eng TEXT,
      level TEXT,
      geom JSONB,
      province_scope_code TEXT,
      province_name TEXT,
      province_name_eng TEXT,
      district_scope_code TEXT,
      district_name TEXT,
      sector_scope_code TEXT,
      sector_name TEXT,
      cell_scope_code TEXT,
      cell_name TEXT
    )
  ),
  normalized AS (
    SELECT p.*,
      ST_Multi(ST_CollectionExtract(
        ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(p.geom::text), 4326)), 3
      )) AS polygon_geom
    FROM parsed p
    WHERE p.geom IS NOT NULL
  )
  INSERT INTO boundaries (scope_code, path, name_kiny, name_eng, level, geom)
  SELECT scope_code, path::ltree, name_kiny, name_eng, level::boundary_level, polygon_geom
  FROM normalized
  WHERE scope_code IS NOT NULL
    AND path IS NOT NULL
    AND name_kiny IS NOT NULL
    AND polygon_geom IS NOT NULL
    AND NOT ST_IsEmpty(polygon_geom)
  ON CONFLICT (scope_code) DO UPDATE SET
    path = EXCLUDED.path,
    name_kiny = EXCLUDED.name_kiny,
    name_eng = EXCLUDED.name_eng,
    level = EXCLUDED.level,
    geom = EXCLUDED.geom,
    updated_at = now(),
    version = boundaries.version + 1;

  GET DIAGNOSTICS v_village_count = ROW_COUNT;

  -- Build dissolved parent polygons from the same village features. When a
  -- parent appears in a later batch, union the new batch with its stored shape.
  WITH parsed AS (
    SELECT *
    FROM jsonb_to_recordset(p_features) AS x(
      scope_code TEXT, path TEXT, name_kiny TEXT, name_eng TEXT, level TEXT,
      geom JSONB,
      province_scope_code TEXT, province_name TEXT, province_name_eng TEXT,
      district_scope_code TEXT, district_name TEXT,
      sector_scope_code TEXT, sector_name TEXT,
      cell_scope_code TEXT, cell_name TEXT
    )
  ),
  normalized AS (
    SELECT p.*,
      ST_Multi(ST_CollectionExtract(
        ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(p.geom::text), 4326)), 3
      )) AS polygon_geom
    FROM parsed p
    WHERE p.geom IS NOT NULL
  ),
  parent_rows AS (
    SELECT
      province_scope_code AS scope_code,
      replace(province_scope_code, '-', '.') AS path,
      province_name AS name_kiny,
      province_name_eng AS name_eng,
      'province'::boundary_level AS level,
      ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_UnaryUnion(ST_Collect(polygon_geom))), 3)) AS geom
    FROM normalized
    WHERE province_scope_code IS NOT NULL AND province_name IS NOT NULL
      AND polygon_geom IS NOT NULL AND NOT ST_IsEmpty(polygon_geom)
    GROUP BY province_scope_code, province_name, province_name_eng

    UNION ALL

    SELECT
      district_scope_code,
      replace(district_scope_code, '-', '.'),
      district_name,
      district_name,
      'district'::boundary_level,
      ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_UnaryUnion(ST_Collect(polygon_geom))), 3))
    FROM normalized
    WHERE district_scope_code IS NOT NULL AND district_name IS NOT NULL
      AND polygon_geom IS NOT NULL AND NOT ST_IsEmpty(polygon_geom)
    GROUP BY district_scope_code, district_name

    UNION ALL

    SELECT
      sector_scope_code,
      replace(sector_scope_code, '-', '.'),
      sector_name,
      sector_name,
      'sector'::boundary_level,
      ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_UnaryUnion(ST_Collect(polygon_geom))), 3))
    FROM normalized
    WHERE sector_scope_code IS NOT NULL AND sector_name IS NOT NULL
      AND polygon_geom IS NOT NULL AND NOT ST_IsEmpty(polygon_geom)
    GROUP BY sector_scope_code, sector_name

    UNION ALL

    SELECT
      cell_scope_code,
      replace(cell_scope_code, '-', '.'),
      cell_name,
      cell_name,
      'cell'::boundary_level,
      ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_UnaryUnion(ST_Collect(polygon_geom))), 3))
    FROM normalized
    WHERE cell_scope_code IS NOT NULL AND cell_name IS NOT NULL
      AND polygon_geom IS NOT NULL AND NOT ST_IsEmpty(polygon_geom)
    GROUP BY cell_scope_code, cell_name
  )
  INSERT INTO boundaries (scope_code, path, name_kiny, name_eng, level, geom)
  SELECT scope_code, path::ltree, name_kiny, name_eng, level, geom
  FROM parent_rows
  WHERE geom IS NOT NULL AND NOT ST_IsEmpty(geom)
  ON CONFLICT (scope_code) DO UPDATE SET
    path = EXCLUDED.path,
    name_kiny = EXCLUDED.name_kiny,
    name_eng = EXCLUDED.name_eng,
    level = EXCLUDED.level,
    geom = ST_Multi(ST_CollectionExtract(
      ST_MakeValid(ST_UnaryUnion(ST_Collect(boundaries.geom, EXCLUDED.geom))), 3
    )),
    updated_at = now(),
    version = boundaries.version + 1;

  RETURN v_village_count;
END;
$$;

GRANT EXECUTE ON FUNCTION ingest_boundary_batch(JSONB) TO service_role;



-- -----------------------------------------------------------------------------
-- GRANTS (Supabase roles)
-- -----------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO anon, authenticated;
GRANT SELECT ON boundaries TO anon, authenticated;
GRANT SELECT ON leaders TO anon, authenticated;
GRANT SELECT ON v_active_leaders TO anon, authenticated;
GRANT SELECT ON admin_profiles TO authenticated;
GRANT SELECT ON audit_logs TO authenticated;

-- End of schema
