-- Least-privilege roles. Passwords are set by the deployment (see infra/ and scripts/).
-- svc_reader: S1 to S5 and S7 (read only market data)
-- svc_s6:     S6 Portfolio (read market data, write holdings and watchlist)
-- svc_s8:     S8 Alerts (read market data, write alert rules and alerts)
-- ingestor:   Market Data Ingestor (write market data and the ingestion log)

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'svc_reader') THEN CREATE ROLE svc_reader LOGIN; END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'svc_s6') THEN CREATE ROLE svc_s6 LOGIN; END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'svc_s8') THEN CREATE ROLE svc_s8 LOGIN; END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ingestor') THEN CREATE ROLE ingestor LOGIN; END IF;
END
$$;

GRANT SELECT ON companies, prices TO svc_reader, svc_s6, svc_s8;
GRANT SELECT, INSERT, UPDATE, DELETE ON holdings, watchlist TO svc_s6;
GRANT SELECT, INSERT, UPDATE, DELETE ON alert_rules, alerts TO svc_s8;
GRANT SELECT, INSERT, UPDATE ON companies, prices TO ingestor;
GRANT SELECT, INSERT, UPDATE ON ingestion_log TO ingestor;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO svc_s6, svc_s8, ingestor;
