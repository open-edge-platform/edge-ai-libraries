#!/bin/bash
sed -e "s|\${BACKEND_HOST}|$BACKEND_HOST|g" \
    -e "s|\${UI_HOST}|$UI_HOST|g" \
    ./nginx_config/nginx.conf.template > ./nginx_config/nginx.conf


