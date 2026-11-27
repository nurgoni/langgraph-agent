-- Demo dataset 2 (F39): IoT sensors at several sites. Fixture for evals only; no code depends on
-- its names. Deterministic (setseed). Planted patterns are listed in planted_patterns.yaml.
-- Runs inside the target database; idempotent (drops and recreates its tables).
SET TIME ZONE 'UTC';
SELECT setseed(0.48);

DROP TABLE IF EXISTS readings, devices, sites CASCADE;

CREATE TABLE sites (
    site_id integer PRIMARY KEY,
    site_name text NOT NULL,
    region text NOT NULL,
    climate_zone text NOT NULL
);
COMMENT ON TABLE sites IS 'Buildings where sensors are installed.';
COMMENT ON COLUMN sites.climate_zone IS 'temperate, tropical, or dry.';

CREATE TABLE devices (
    device_id integer PRIMARY KEY,
    site_id integer NOT NULL REFERENCES sites (site_id),
    kind text NOT NULL,
    unit text NOT NULL,
    installed_at date NOT NULL
);
COMMENT ON TABLE devices IS 'One sensor. Each site has two devices of each kind.';
COMMENT ON COLUMN devices.kind IS 'temperature (celsius), humidity (percent), or power (kW).';

CREATE TABLE readings (
    device_id integer NOT NULL REFERENCES devices (device_id),
    recorded_at timestamptz NOT NULL,
    value double precision
);
COMMENT ON TABLE readings IS 'Hourly sensor readings. A reading can be missing or repeated.';
COMMENT ON COLUMN readings.recorded_at IS 'Start of the hour the reading covers (UTC).';
COMMENT ON COLUMN readings.value IS 'Measured value in the unit of the device. Null when the sensor reported no value.';
CREATE INDEX readings_device_time ON readings (device_id, recorded_at);

INSERT INTO sites
SELECT g,
       'Site ' || chr(64 + g),
       (ARRAY['north', 'south', 'east', 'west'])[1 + (g - 1) % 4],
       (ARRAY['temperate', 'tropical', 'dry'])[1 + (g - 1) % 3]
FROM generate_series(1, 8) AS g;

INSERT INTO devices
SELECT row_number() OVER (ORDER BY s.site_id, k.ordinality, copy),
       s.site_id,
       k.kind,
       CASE k.kind WHEN 'temperature' THEN 'celsius' WHEN 'humidity' THEN 'percent' ELSE 'kW' END,
       DATE '2026-01-01' + (s.site_id * 7)
FROM sites AS s
CROSS JOIN unnest(ARRAY['temperature', 'humidity', 'power']) WITH ORDINALITY AS k (kind, ordinality)
CROSS JOIN generate_series(1, 2) AS copy;

-- Daily cycle for every kind, a slow warming trend for temperature, and working hours for power.
-- Site 3 (Site C) uses about 35% less power from 2026-08-15.
INSERT INTO readings
SELECT d.device_id,
       h.hour,
       CASE d.kind
           WHEN 'temperature' THEN
               20 + 5 * sin(2 * pi() * (extract(hour FROM h.hour) - 9) / 24)
               + 0.02 * extract(day FROM h.hour - TIMESTAMPTZ '2026-05-01')
               + (random() - 0.5) * 1.5
           WHEN 'humidity' THEN
               CASE WHEN random() < 0.005 THEN NULL
                    ELSE 60 - 12 * sin(2 * pi() * (extract(hour FROM h.hour) - 9) / 24)
                         + (random() - 0.5) * 6 END
           ELSE
               (30 + CASE WHEN extract(isodow FROM h.hour) < 6
                               AND extract(hour FROM h.hour) BETWEEN 8 AND 18 THEN 25 ELSE 0 END
                + (random() - 0.5) * 6)
               * CASE WHEN d.site_id = 3 AND h.hour >= TIMESTAMPTZ '2026-08-15' THEN 0.65 ELSE 1 END
       END
FROM devices AS d
CROSS JOIN generate_series(
    TIMESTAMPTZ '2026-05-01', TIMESTAMPTZ '2026-10-31 23:00', INTERVAL '1 hour'
) AS h (hour)
-- Gaps: device 7 is offline for four days, and site 5 sends nothing for half a day.
WHERE NOT (d.device_id = 7 AND h.hour >= TIMESTAMPTZ '2026-07-10'
                           AND h.hour < TIMESTAMPTZ '2026-07-14')
  AND NOT (d.site_id = 5 AND h.hour >= TIMESTAMPTZ '2026-09-01'
                         AND h.hour < TIMESTAMPTZ '2026-09-01 12:00')
ORDER BY d.device_id, h.hour;

-- Outliers: temperature sensors sometimes report 999 (a glitch value).
UPDATE readings SET value = 999
WHERE device_id IN (1, 14)
  AND extract(epoch FROM recorded_at)::bigint % 1000003 < 1800;

-- Duplicates: device 12 repeats about 1% of its readings.
INSERT INTO readings
SELECT device_id, recorded_at, value
FROM readings
WHERE device_id = 12 AND extract(epoch FROM recorded_at)::bigint % (3600 * 97) = 0
ORDER BY recorded_at;

ANALYZE;
