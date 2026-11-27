-- Grants for the read-only role inside one demo database (F39). psql variable: role.
-- Nobody but the owner can create objects in the public schema.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE TEMPORARY ON DATABASE :"DBNAME" FROM PUBLIC;
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'role') \gexec
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'role') \gexec
SELECT format('GRANT SELECT ON ALL TABLES IN SCHEMA public TO %I', :'role') \gexec
