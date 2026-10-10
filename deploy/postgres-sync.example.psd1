@{
    PGHOST = 'postgres.internal.example'
    PGPORT = '5432'
    PGDATABASE = 'production'
    PGUSER = 'ecm_readonly'
    # Password in libpq pgpass format; use the task account's file, with restricted ACLs.
    PGPASSFILE = 'C:\engine-wash-secrets\pgpass.conf'
    PGSSLMODE = 'require'
    QUACK_TOKEN_FILE = 'C:\engine-wash-secrets\quack.token'
    DUCKDB_EXTENSION_DIRECTORY = 'C:\engine-wash-secrets\duckdb-extensions'

    # Wrapper opens/closes a tunnel on every invocation. Prepare known_hosts first.
    SSH_HOST = 'b000gdan@actual-ssh-host'
    SSH_LOCAL_PORT = 19494
    SSH_IDENTITY_FILE = 'C:\Users\sync-user\.ssh\id_ed25519'
    # Used only when SSH_HOST is empty and an existing tunnel/endpoint is available.
    FLIGHT_QUACK_URL = 'quack:127.0.0.1:19494'
    WINDOW_DAYS = 7
}
