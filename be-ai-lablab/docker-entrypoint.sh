#!/bin/sh
set -eu

mkdir -p storage/app/private storage/app/public storage/framework/cache/data \
    storage/framework/sessions storage/framework/views storage/logs bootstrap/cache

if [ -z "${APP_KEY:-}" ]; then
    if [ ! -s storage/app/app-key ]; then
        (umask 077; php -r 'echo "base64:".base64_encode(random_bytes(32));' > storage/app/app-key)
    fi
    chmod 600 storage/app/app-key
    APP_KEY="$(cat storage/app/app-key)"
    export APP_KEY
fi

chown -R www-data:www-data storage bootstrap/cache
php artisan migrate --force

exec "$@"
