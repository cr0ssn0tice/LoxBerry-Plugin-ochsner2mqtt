<?php
// Router für den PHP-Testserver: simuliert die Web-Struktur eines LoxBerry 4.
//   /index.php, /ajax.php, /css, /js, /app  → Plugin-Ordner (Docroot, wie /admin/plugins/<ordner>/)
//   /system/...                              → webfrontend/html/system des LoxBerry-Quellcodes (CSS, JS, Icons)
//   /admin/system/ajax/ajax-config-handler.cgi        → Protokollstufe in plugindatabase.json setzen
//   /admin/system/ajax/ajax-notification-handler.cgi  → Benachrichtigungen aus der SQLite-DB als HTML
// Nur für Tests; die echten Handler sind Perl-CGIs des LoxBerry.
$uri = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
$lb = getenv('LBHOMEDIR');

if (strpos($uri, '/system/') === 0) {
    // Plugin-Icons legt der Installer nach webfrontend/html/system/images/icons/<ordner>/
    $f = preg_match('#^/system/images/icons/([a-z0-9_]+)/([A-Za-z0-9_.]+)$#', $uri, $m)
        ? realpath("$lb/plugin_icons/$m[1]/$m[2]") : realpath("$lb/webfrontend/html" . $uri);
    if ($f === false || !is_file($f)) { http_response_code(404); return true; }
    $types = ['css' => 'text/css', 'js' => 'application/javascript', 'svg' => 'image/svg+xml', 'png' => 'image/png',
              'woff' => 'font/woff', 'woff2' => 'font/woff2', 'ttf' => 'font/ttf', 'eot' => 'application/vnd.ms-fontobject',
              'ico' => 'image/x-icon'];
    header('Content-Type: ' . ($types[strtolower(pathinfo($f, PATHINFO_EXTENSION))] ?? 'application/octet-stream'));
    readfile($f);
    return true;
}

if ($uri === '/admin/system/ajax/ajax-config-handler.cgi') {
    if (($_POST['action'] ?? '') !== 'plugin-loglevel') { http_response_code(500); return true; }
    $dbf = "$lb/data/system/plugindatabase.json";
    $db = json_decode(file_get_contents($dbf), true);
    foreach ($db['plugins'] as $k => $p) {
        if ($p['md5'] === ($_POST['pluginmd5'] ?? '')) $db['plugins'][$k]['loglevel'] = intval($_POST['value'] ?? 3);
    }
    file_put_contents($dbf, json_encode($db, JSON_PRETTY_PRINT));
    header('Content-Type: application/json');
    echo json_encode(['error' => 0]);
    return true;
}

if ($uri === '/admin/system/ajax/ajax-main-icons-handler.php') {
    header('Content-Type: application/json');
    echo json_encode(['reboot_required' => 0]);
    return true;
}

if ($uri === '/admin/system/ajax/ajax-notification-handler.cgi') {
    $dbf = "$lb/data/system/notifications_sqlite.dat";
    $rows = [];
    if (is_file($dbf)) {
        $db = new PDO("sqlite:$dbf");
        $sql = "SELECT MESSAGE, SEVERITY, timestamp FROM notifications WHERE 1=1";
        $args = [];
        foreach (['package' => 'PACKAGE', 'name' => 'NAME'] as $k => $col) {
            if (($_POST[$k] ?? '') !== '' && ($_POST[$k] ?? '') !== 'undefined') { $sql .= " AND $col = ?"; $args[] = $_POST[$k]; }
        }
        $st = $db->prepare($sql . " ORDER BY notifykey DESC");
        $st->execute($args);
        $rows = $st->fetchAll(PDO::FETCH_ASSOC);
    }
    if (($_POST['action'] ?? '') === 'get_notification_count') {
        $err = count(array_filter($rows, fn($r) => intval($r['SEVERITY']) === 3));
        header('Content-Type: application/json');
        echo json_encode([$err, count($rows) - $err, count($rows)]);
        return true;
    }
    if (($_POST['action'] ?? '') !== 'get_notifications_html') { header('Content-Type: application/json'); echo '[]'; return true; }
    if (!$rows) { http_response_code(204); return true; }
    // gleiche Struktur und Stile wie templates/system/get_notification_html.html des LoxBerry
    $tpl = @file_get_contents("$lb/templates/system/get_notification_html.html");
    $style = ($tpl && preg_match('#<style>.*?</style>#s', $tpl, $m)) ? $m[0] : '';
    echo '<div id="notificationBlock" style="margin-bottom:20px;"><div id="notificationItems">';
    foreach ($rows as $r) {
        $err = intval($r['SEVERITY']) === 3;
        echo '<div class="lb-notify-box ' . ($err ? 'lb-notify-error' : 'lb-notify-info') . '"><div class="lb-notify-icon">'
           . '<img src="/system/images/notification_' . ($err ? 'error' : 'info') . '_small.svg" width="20" height="20"></div>'
           . '<div class="lb-notify-message"><b>' . htmlspecialchars($r['timestamp']) . ':</b> ' . htmlspecialchars($r['MESSAGE']) . '</div>'
           . '<div class="lb-notify-actions"><a href="#" class="lb-btn lb-btn-sm lb-btn-icon"><i class="pi pi-times"></i></a></div></div>';
    }
    echo '</div></div>' . $style;
    return true;
}

if (strpos($uri, '/admin/') === 0) { http_response_code(404); return true; }
return false;   // Plugin-Dateien liefert der eingebaute Server selbst
