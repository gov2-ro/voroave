# F04 — Give application statistics an unambiguous route

Status: open. Priority: P2.

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
