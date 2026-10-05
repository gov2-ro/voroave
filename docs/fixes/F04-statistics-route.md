# F04 — Give application statistics an unambiguous route

Status: local patch complete 2026-10-05; live check open until the owner deploys. Priority: P2.

## Evidence and target

On the audited host, `/stats` serves a provider-generated traffic report.
`/stats.php` serves the application. Existing files/directories bypass extensionless rewrites.
The target is a stable route that works independently of the provider's reserved `/stats` path.

## Decision and scope

Use `/statistici` as the application route. Keep `stats.php` as its implementation.
Add an explicit internal rewrite before generic rules in `public/.htaccess`.
Mirror the route in `tools/dev-router.php`, including subfolder behavior where applicable.
Update internal links, canonical/OG URLs, and relevant documentation.
Keep `/stats.php` functional for legacy links. Do not add broad extension-removal redirects.
Do not redirect POST APIs or assume the application controls the provider's `/stats` directory.
Document the legacy `/stats` collision and owner-side hosting remediation separately.
The owner should review public access to hosting reports; this task cannot establish their full contents.

## Acceptance

- `/statistici` serves app statistics and a matching canonical URL.
- `/stats.php` still works; app navigation uses `/statistici`.
- Local routing matches Apache routing for the new slug.
- Query filters survive navigation and rewrite.
- Root and subfolder routes resolve correctly.
- Other clean URLs and API POST behavior remain unchanged.
- Record a live check after a separately authorized deployment.

## Boundary

No hosting-panel changes, traffic-report deletion, or production deployment.
Deliver the application patch and owner instructions for the reserved hosting route.

## Result (2026-10-05)

- `public/.htaccess`: `RewriteRule ^statistici/?$ stats.php [L]`, before the generic rules. Internal; no redirect.
- `tools/dev-router.php` mirrors it, including a path prefix (subfolder under the docroot).
- `NAV_ITEMS['stats']['path']` is `/statistici`. `despre.html` links to `statistici`.
  `stats.php` has `rel="canonical"` and `og:url` for `/statistici`. The sitemap never listed it.
- Tests: `tests/test_statistics_route.py` (static rule order, dev router, subfolder, shadow directory,
  real `httpd` with mod_rewrite at root, `/sub` and `/prov`) and `tests/test_statistics_route.js`.
- Local only. The live `/stats` collision is a hosting fact and was not reproduced here.
  Apache was tested with Homebrew `httpd` and static probe files, not with PHP.
  The Apache test is opt-in: `.venv/bin/python -m pytest tests -q -m apache`. The required run deselects it.

## Owner instructions (not done by this task)

1. Deploy `public/` with the usual rsync, excluding `api/config.local.php`.
2. Check `https://voroave.ro/statistici` returns the application page. Check `/stats.php` still works.
3. Check `/despre` links to `/statistici`. Record the result in `docs/activity-history.md`.
4. Open `https://voroave.ro/stats` and decide who may see the provider traffic report.
   This task cannot see its contents. It may list visitor addresses, paths and referrers.
5. In the hosting panel, either password-protect the report or turn it off. Do not delete the
   directory without a decision. The application does not need `/stats` any more.
6. Ask the host whether the report path can be renamed. Do not add an `.htaccess` rule that
   hides `/stats`: the provider directory may be outside the application folder.
