#!/bin/bash

# Ensure the fps.txt file exists and is initialized to 0.0 and can be written to by vippet
echo "0.0" > /app/.collector-signals/fps.txt
chmod o+w /app/.collector-signals/fps.txt

# Ensure the named pipe for qmassa exists and is writable
if [ ! -p /app/qmassa.fifo ]; then
    mkfifo /app/qmassa.fifo
fi
chmod 666 /app/qmassa.fifo

# Telegraf and qmassa are started and managed by supervisord
/usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
