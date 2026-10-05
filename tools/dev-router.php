<?php
/**
 * Router for PHP's built-in server, so local dev matches the deployed Apache.
 *
 *     php -S 127.0.0.1:8011 -t public tools/dev-router.php
 *
 * The built-in server ignores .htaccess entirely, which means the extensionless URLs
 * (/despre → /despre.php) work in production and 404 locally — exactly the kind of gap
 * where a broken link ships because nobody could see it. This mirrors the rewrite
 * rules in public/.htaccess and nothing else; it is a dev convenience, not a framework.
 *
 * It lives in tools/ on purpose: only the contents of public/ are deployed, so a router
 * placed there would ship to the server and be reachable over HTTP.
 */
declare(strict_types=1);

$root = dirname(__DIR__) . '/public';
$path = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?: '/';
$file = $root . urldecode($path);

// /joc → /ghici, mirroring the one 301 in .htaccess. Without it the rename reads as
// working locally right up until an old link is followed in production.
if (preg_match('#^/joc(\.php)?/?$#', $path)) {
    header('Location: /ghici', true, 301);
    return true;
}

// /statistici → stats.php (F04), mirroring the explicit rewrite in .htaccess. It is an
// internal rewrite: no redirect, and the query string stays in $_SERVER. A prefix before
// the slug (a subfolder deploy inside the docroot) is honoured when stats.php exists there.
if (preg_match('#^(.*?)/statistici/?$#', $path, $m)) {
    $candidate = $root . urldecode($m[1]) . '/stats.php';
    if (is_file($candidate)) {
        $_SERVER['SCRIPT_NAME']     = $m[1] . '/stats.php';
        $_SERVER['SCRIPT_FILENAME'] = $candidate;
        require $candidate;
        return true;
    }
}

// A real file or directory serves itself, exactly as the .htaccess conditions require.
if ($path !== '/' && (is_file($file) || is_dir($file))) {
    return false;
}

foreach (['.php', '.html'] as $ext) {
    $candidate = $root . rtrim(urldecode($path), '/') . $ext;
    if (is_file($candidate)) {
        $_SERVER['SCRIPT_NAME']     = rtrim($path, '/') . $ext;
        $_SERVER['SCRIPT_FILENAME'] = $candidate;
        if ($ext === '.html') { readfile($candidate); return true; }
        require $candidate;
        return true;
    }
}

return false;
