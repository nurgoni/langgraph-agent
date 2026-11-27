-- Read-only login role for the demo data sources (F39). psql variables: role, password.
SELECT format('CREATE ROLE %I LOGIN', :'role')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'role') \gexec
SELECT format('ALTER ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE', :'role', :'password') \gexec
SELECT format('ALTER ROLE %I SET default_transaction_read_only = on', :'role') \gexec
