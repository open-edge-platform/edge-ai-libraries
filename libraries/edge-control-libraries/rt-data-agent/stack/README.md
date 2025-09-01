## Stack Security

### MQTT broker authentication

In default, there is no security setting for the mqtt broker.
Everyone could sub/pub to the broker hence there is a data leak risk. 

To enable the security/authentication for the broker, the simplest way is to enable username/password.
Here are the steps for the ECI image which has a default running mosquitto service.

####  Create example username/password for the broker, use **test/test** for example.
```
# mosquitto_passwd -c /etc/mosquitto/passwd test
Password:
Reenter password:
```
####  Enable broker authentication in `/etc/mosquitto/mosquitto.conf`.
*  Set `allow_anonymous false`
*  Set `password_file /etc/mosquitto/passwd`

#### Restart the mosquitto service to make changes take effect
```
# systemctl daemon-reload
# systemctl restart mosquitto.service
```
Now if you run the stack/agent the mqtt connection will fail.

Next let's enable the authentication for the stack/agent.

####  Set username/password for broker connection authentication in the [`mqtt_service.py`](../app/mqtt_service.py)
*  Uncomment the line `username_pw_set(username="test", password="test")` before the connect.

####  Set username/password for the telegraf mqtt input plugin authentication in the [`telegraf.conf`](./telegraf/telegraf.conf)
*  Uncomment the lines below.
```
#   ## Username and password to connect MQTT server.
#     username = "test"
#     password = "test"
```

Till now, the username/password authentication for the mqtt broker in this demo is done.

You could run the demo with mqtt broker securely protected.

### User permission for the database

The database in this example demo is saved in local docker volumes.

The docker volumes are in the path `/var/lib/docker/volumes/` with the access permission who runs the stack.

For example, the ECI image has the default root user, after starting the stack, the volumes permission is like below.
```
# ls -l /var/lib/docker/volumes/
total 32
-rw------- 1 root root 32768 Jan  4 06:14 metadata.db
drwxr-xr-x 3 root root  4096 Jan  4 06:14 stack_grafana_data
drwxr-xr-x 3 root root  4096 Jan  4 06:14 stack_influxdb_data
```

For other users other than root, there is no way to access/modify the database.
