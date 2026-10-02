"""Static proxy policy and local CORS checks; installed nginx is tested separately."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NGINX = ROOT / "infra" / "nginx"


def test_proxy_headers_cover_redirects_errors_api_and_cache_classes():
    config = (NGINX / "bukergo.ru.conf").read_text()
    common = (NGINX / "booker-common-headers.conf").read_text()
    https = (NGINX / "booker-https-headers.conf").read_text()
    assert config.count("server_tokens off;") == 3
    assert config.count("include /opt/booker/current/infra/nginx/booker-https-headers.conf;") >= 6
    assert "location = /api/internal/readiness" in config
    assert "return 404;" in config
    assert "proxy_hide_header Cache-Control;" in config
    assert 'Cache-Control "private, no-cache, no-store, max-age=0, must-revalidate" always;' in config
    assert 'Cache-Control "public, max-age=31536000, immutable";' in config
    assert "location /_next/static/" in config
    assert "Strict-Transport-Security" in https
    assert "max-age=604800" in https
    assert "includeSubDomains" not in https and "preload" not in https
    for name in ("Content-Security-Policy", "X-Content-Type-Options", "Referrer-Policy", "X-Frame-Options"):
        assert f"add_header {name}" in common
    assert "script-src 'self' 'unsafe-inline'" in common
    assert "style-src 'self' 'unsafe-inline'" in common
    assert "unsafe-eval" not in common
    assert "object-src 'none'" in common
    assert "frame-ancestors 'self'" in common
    assert "https://" not in common  # no credentials or external endpoint embedded in policy


def test_next_disables_powered_by_and_deploy_checks_database_readiness():
    next_config = (ROOT / "apps" / "web" / "next.config.ts").read_text()
    deploy = (ROOT / "infra" / "deploy-vps.sh").read_text()
    transaction = (ROOT / "infra" / "release_deploy.py").read_text()
    assert "poweredByHeader: false" in next_config
    assert "release_deploy.py" in deploy
    assert '"-fS"' in transaction and '"/internal/readiness"' in transaction


def test_cors_never_reflects_untrusted_origin_with_credentials(client):
    trusted = client.get("/health", headers={"Origin": "https://bukergo.ru"})
    assert trusted.headers.get("access-control-allow-origin") == "https://bukergo.ru"
    untrusted = client.get("/health", headers={"Origin": "https://untrusted.example"})
    assert "access-control-allow-origin" not in untrusted.headers
    assert untrusted.headers.get("access-control-allow-origin") != "*"
