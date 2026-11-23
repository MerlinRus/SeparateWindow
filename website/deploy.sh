#!/usr/bin/env bash
set -euo pipefail

domain=separate.maark.ru
site=/opt/separate-window
config=/etc/nginx/sites-available/$domain
enabled=/etc/nginx/sites-enabled/$domain
certificate=/etc/letsencrypt/live/$domain/fullchain.pem

install -d -m 0755 "$site/releases" "$site/acme"
exec 9>"$site/.deploy.lock"
flock -x 9

test_and_reload() {
    if nginx -t >"$site/nginx-test.log" 2>&1; then
        systemctl reload nginx
    else
        cat "$site/nginx-test.log" >&2
        return 1
    fi
}

activate() {
    local candidate=$1 backup
    backup=$(mktemp "$site/config-backup.XXXXXXXX")
    if [[ -f "$config" ]]; then
        cp -- "$config" "$backup"
    fi
    install -m 0644 "$candidate" "$config"
    if [[ ! -L "$enabled" ]]; then
        ln -s -- "$config" "$enabled"
    fi
    if test_and_reload; then
        rm -- "$backup"
        return 0
    fi
    if [[ -s "$backup" ]]; then
        install -m 0644 "$backup" "$config"
    else
        rm -- "$enabled" "$config"
    fi
    rm -- "$backup"
    return 1
}

case ${1:-} in
    deploy)
        release=$(mktemp -d "$site/releases/$(date -u +%Y%m%dT%H%M%SZ).XXXXXXXX")
        chmod 0755 "$release"
        tar -xf "$2" --no-same-owner -C "$release"
        test -s "$release/public/index.html"
        test -s "$release/public/en/index.html"
        test -s "$release/public/onboarding/index.html"
        test -s "$release/public/en/onboarding/index.html"
        test -s "$release/public/assets/onboarding-loop.mp4"
        previous=$(readlink "$site/current" || true)
        ln -s -- "$release" "$site/.next"
        mv -Tf -- "$site/.next" "$site/current"
        candidate="$release/nginx-http.conf"
        if [[ -s "$certificate" ]]; then
            candidate="$release/nginx-https.conf"
        fi
        if ! activate "$candidate"; then
            if [[ -n "$previous" ]]; then
                ln -s -- "$previous" "$site/.next"
                mv -Tf -- "$site/.next" "$site/current"
            else
                rm -- "$site/current"
            fi
            exit 1
        fi
        printf 'Activated %s\n' "$release"
        ;;
    https)
        test -s "$site/current/public/index.html"
        certbot certonly --webroot -w "$site/acme" -d "$domain" --cert-name "$domain" \
            --non-interactive --keep-until-expiring --deploy-hook '/usr/bin/systemctl reload nginx'
        test -s "$certificate"
        activate "$site/current/nginx-https.conf"
        ;;
    *)
        printf 'Usage: %s deploy ARCHIVE | https\n' "$0" >&2
        exit 2
        ;;
esac
