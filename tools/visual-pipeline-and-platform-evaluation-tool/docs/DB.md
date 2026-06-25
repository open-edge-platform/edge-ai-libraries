## PostgreSQL Setup

ViPPET uses a PostgreSQL database on a **central machine** to persist server/machine
records. The database connection is only required on that central machine — client
machines connect to its REST API via ``VITE_SERVERS_HOST`` and do not need
``DATABASE_URL`` at all.

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

### Configuration

Set the following environment variables on the **central machine** before starting
the servers registry service:

```
DATABASE_URL=postgresql://<username>:<password>@<DB_HOST_IP>:5432/vippet_db
ADMIN_API_KEY=<your-secret-key>
```

See [Server Registry Service](../compose.servers.yml) or `make run-servers` /
`make servers` for how to start the service.

### Access Control

ViPPET uses a single database user. Write access to the servers registry is
controlled by the ``ADMIN_API_KEY`` environment variable on the central machine:

| Central machine config | Access level | UI behaviour |
|---|---|---|
| `ADMIN_API_KEY` is **set** | Write — register/remove machines | Shows the **Register Server** button |
| `ADMIN_API_KEY` is **not set** | Read-only — list servers only | Hides the **Register Server** button |

Client machines whose UI is built with ``VITE_ADMIN_API_KEY=<key>`` will include
the key in write requests. Machines without it are implicitly read-only.

### Security recommendations

* Restrict port 5432 to trusted IPs only:
    ```
    sudo ufw allow from <trusted_ip> to any port 5432
    ```
* Generate a strong, random password:
    ```
    openssl rand -base64 32
    ```
* Generate a strong, random API key:
    ```
    openssl rand -base64 32
    ```
* For production deployments consider enabling SSL on the PostgreSQL server
  by mounting a custom ``postgresql.conf`` with ``ssl = on``.
