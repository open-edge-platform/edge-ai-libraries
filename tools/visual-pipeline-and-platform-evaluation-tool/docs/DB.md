## PostgreSQL Setup

ViPPET uses a PostgreSQL database to persist server/machine records.
The connection is configured via the ``DATABASE_URL`` environment variable.

### Starting the PostgreSQL Docker container

Run the following command on the machine that will host the database.
The ``-p 0.0.0.0:5432:5432`` binding makes the database reachable from
other machines on the network.

```
docker run -d \
  --name vippet-postgres \
  -e POSTGRES_USER=<username> \
  -e POSTGRES_PASSWORD=<password> \
  -e POSTGRES_DB=vippet_db \
  -p 0.0.0.0:5432:5432 \
  --restart unless-stopped \
  postgres:16
```

Verify the container is running:
```
docker ps | grep vippet-postgres
```

### User Roles

ViPPET supports two PostgreSQL roles with different levels of access:

| Role | Permissions | UI behaviour |
|------|-------------|--------------|
| `vippet_server` | Full read/write on the `servers` table | Shows the **Add Server** button — can register and remove machines |
| `vippet_user` | Read-only on the `servers` table | Hides the **Add Server** button — can only view registered machines on the Remote page |

#### Creating the roles

Connect to the running container as the superuser:

```bash
docker exec -it vippet-postgres psql -U <username> -d vippet_db
```

Then run the following SQL:

```sql
-- Create roles
CREATE USER vippet_server WITH PASSWORD '<server_password>';
CREATE USER vippet_user   WITH PASSWORD '<user_password>';

-- Grant connection and schema access
GRANT CONNECT ON DATABASE vippet_db TO vippet_server, vippet_user;
GRANT USAGE   ON SCHEMA public      TO vippet_server, vippet_user;

-- vippet_server: full access to the servers table
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE servers TO vippet_server;

-- vippet_user: read-only access
GRANT SELECT ON TABLE servers TO vippet_user;
```

### Configuration

Set the ``DATABASE_URL`` environment variable before starting ViPPET,
either in your shell or in the ``.env`` file at the project root.

**Admin machine** (can register/remove servers):
```
DATABASE_URL=postgresql://vippet_server:<server_password>@<DB_HOST_IP>:5432/vippet_db
```

**Regular machine** (read-only, Remote page only):
```
DATABASE_URL=postgresql://vippet_user:<user_password>@<DB_HOST_IP>:5432/vippet_db
```

The variable is forwarded into the ``vippet`` container via ``compose.yml``.

### Security recommendations

* Restrict port 5432 to trusted IPs only:
    ```
    sudo ufw allow from <trusted_ip> to any port 5432
    ```
* Use a strong, randomly generated password::
    ```
    openssl rand -base64 32
    ```
* For production deployments consider enabling SSL on the PostgreSQL server
  by mounting a custom ``postgresql.conf`` with ``ssl = on``.