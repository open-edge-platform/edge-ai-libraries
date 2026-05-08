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
  -e POSTGRES_USER=vippet \
  -e POSTGRES_PASSWORD=<your_secure_password> \
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

Set the ``DATABASE_URL`` environment variable before starting ViPPET,
either in your shell or in the ``.env`` file at the project root:

```
DATABASE_URL=postgresql://vippet:<your_secure_password>@<DB_HOST_IP>:5432/vippet_db
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