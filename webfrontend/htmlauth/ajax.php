<?php
// ajax.php – JSON-Endpunkt der Weboberfläche (liegt im authentifizierten LoxBerry-Bereich).
// Eigener Endpunkt statt ajax-generic.php, weil Zugangsdaten nie an den Browser gehen dürfen
// und jede Eingabe serverseitig geprüft wird. Schreibende Aufrufe: POST + Header X-O2M + gleicher Origin.
require_once "loxberry_system.php";

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');

$L = LBSystem::readlanguage("language.ini");
$cfgfile   = "$lbpconfigdir/ochsner2mqtt.json";
$statefile = "$lbpdatadir/state.json";
$cmddir    = "$lbpdatadir/cmd";
$ctl       = "$lbpbindir/ctl.sh";
$sysconf   = "$lbhomedir/config/system";

$DEFAULTS = [
    "host" => "", "port" => 80, "username" => "", "password" => "", "pin" => "",
    "poll_interval" => 30, "mqtt_enabled" => true, "mqtt_topic" => "ochsner",
    "publish_mode" => "changes", "full_refresh_min" => 10, "include_technical" => false,
    "publish_raw_points" => true, "writes_enabled" => false, "write_min_interval_sec" => 120,
    "write_max_per_day" => 100, "api_port" => 18765, "schema_buffer" => "auto",
    "notify_alarms" => true, "notify_connection" => true,
];

/** Text aus der Sprachdatei, {name}-Platzhalter ersetzt. */
function T($key, $params = []) {
    global $L;
    $s = $L[$key] ?? $key;
    foreach ($params as $k => $v) $s = str_replace("{" . $k . "}", $v, $s);
    return $s;
}

function out($data, $code = 200) {
    http_response_code($code);
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}

function read_json_file($path, $default) {
    if (!is_file($path)) return $default;
    $d = json_decode(@file_get_contents($path), true);
    return is_array($d) ? $d : $default;
}

function write_json_atomic($path, $data, $mode = 0640) {
    $tmp = $path . ".tmp" . getmypid();
    if (file_put_contents($tmp, json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES)) === false) return false;
    @chmod($tmp, $mode);
    return rename($tmp, $path);
}

function load_cfg() {
    global $cfgfile, $DEFAULTS;
    $c = array_merge($DEFAULTS, read_json_file($cfgfile, []));
    unset($c["loglevel"]);   // bis 0.3.x eigene Stufe, jetzt LoxBerry-Protokollstufe
    return $c;
}

function require_post() {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') out(["ok" => false, "error" => T("AJAX.POST_REQUIRED")], 405);
    // einfacher CSRF-Schutz: eigener Header + gleicher Origin
    if (($_SERVER['HTTP_X_O2M'] ?? '') !== '1') out(["ok" => false, "error" => T("AJAX.INVALID_REQUEST")], 403);
    $origin = $_SERVER['HTTP_ORIGIN'] ?? '';
    if ($origin !== '') {
        $host = parse_url($origin, PHP_URL_HOST);
        $self = explode(':', $_SERVER['HTTP_HOST'] ?? '')[0];
        if ($host !== $self) out(["ok" => false, "error" => T("AJAX.FOREIGN_ORIGIN")], 403);
    }
    $body = json_decode(file_get_contents('php://input'), true);
    return is_array($body) ? $body : [];
}

function tail_file($path, $lines = 300) {
    if (!is_file($path)) return "";
    $data = @file($path, FILE_IGNORE_NEW_LINES);
    if ($data === false) return "";
    return implode("\n", array_slice($data, -$lines));
}

/** Aktuelle Logdatei des Dienstes (LBLog-Sitzung "Daemon"), nur innerhalb des Plugin-Logordners. */
function daemon_logfile() {
    global $lbpdatadir, $lbplogdir;
    $info = read_json_file("$lbpdatadir/api.json", []);
    $base = realpath($lbplogdir);
    $f = isset($info["logfile"]) ? realpath($info["logfile"]) : false;
    if ($f !== false && $base !== false && strpos($f, $base . DIRECTORY_SEPARATOR) === 0 && is_file($f)) return $f;
    $all = glob("$lbplogdir/*_Daemon.log") ?: [];
    sort($all);
    return $all ? end($all) : "";
}

function miniservers() {
    $list = [];
    $ms = method_exists("LBSystem", "get_miniservers") ? LBSystem::get_miniservers() : [];
    if (is_array($ms)) foreach ($ms as $no => $m) $list[] = ["no" => intval($no), "name" => strval($m["Name"] ?? "")];
    return $list;
}

$action = $_GET['action'] ?? '';

switch ($action) {
case 'state':
    out(read_json_file($statefile, ["status" => ["connected" => false, "error" => T("AJAX.NO_DATA_YET")], "points" => []]));

case 'alarm_history':
    out(array_reverse(read_json_file("$lbpdatadir/alarm_history.json", [])));

case 'write_log':
    out(array_reverse(read_json_file("$lbpdatadir/write_log.json", [])));

case 'cmd_results':
    out(read_json_file("$lbpdatadir/cmd_results.json", []));

case 'log':
    $f = daemon_logfile();
    out(["log" => $f !== "" ? tail_file($f, 400) : "", "file" => $f !== "" ? basename($f) : "",
         "viewer" => $f !== "" ? "/admin/system/tools/logfile.cgi?logfile=" . rawurlencode($f) . "&header=html&format=template" : ""]);

case 'loxinfo':
    $gen = read_json_file("$sysconf/general.json", []);
    $host = explode(':', $_SERVER['HTTP_HOST'] ?? '')[0];
    out(["udp_port" => intval($gen["Mqtt"]["Udpinport"] ?? 11884), "loxberry" => $host,
         "gateway" => !empty($gen["Mqtt"])]);

case 'gateway':
    // MQTT Gateway des LoxBerry: Version und (bei V2) welche unserer Topics eingetragen sind
    $gen = read_json_file("$sysconf/general.json", []);
    $ver = intval($gen["Mqtt"]["Gatewayversion"] ?? 1) === 2 ? 2 : 1;
    $base = load_cfg()["mqtt_topic"];
    $subs = read_json_file("$sysconf/subscriptions.json", ["Subscriptions" => []]);
    $ours = []; $toms = null;
    foreach (($subs["Subscriptions"] ?? []) as $e) {
        if (isset($e["Id"]) && strpos($e["Id"], "$base/") === 0) {
            $ours[] = $e["Id"];
            if ($toms === null) $toms = array_map('intval', $e["Toms"] ?? []);
        }
    }
    out(["version" => $ver, "base" => $base, "subscribed" => $ours, "toms" => $toms ?? [],
         "miniservers" => miniservers(), "total" => count($subs["Subscriptions"] ?? []),
         "udp_port" => intval($gen["Mqtt"]["Udpinport"] ?? 11884)]);

case 'gateway_subscribe':
    // Trägt genau die übergebenen Topics (alle unter dem Basis-Topic) in die Abo-Liste des Gateway V2 ein.
    // Fremde Abos bleiben unverändert; vorher wird eine Sicherung angelegt. Die Liste der eigenen
    // Einträge (gateway_topics.json) nutzt die Deinstallation zum Aufräumen.
    $in = require_post();
    $base = load_cfg()["mqtt_topic"];
    $want = [];
    foreach (($in["topics"] ?? []) as $t) {
        $t = strval($t);
        if (strpos($t, "$base/") !== 0 || !preg_match('#^[A-Za-z0-9_\-/]{1,200}$#', $t)) out(["ok" => false, "error" => T("AJAX.BAD_TOPIC", ["topic" => $t])]);
        $want[$t] = true;
    }
    if (count($want) > 600) out(["ok" => false, "error" => T("AJAX.TOO_MANY")]);
    $validms = array_column(miniservers(), "no");
    $toms = [];
    foreach (($in["toms"] ?? []) as $n) {
        if (!in_array(intval($n), $validms, true)) out(["ok" => false, "error" => T("AJAX.BAD_MS")]);
        $toms[] = intval($n);
    }
    $file = "$sysconf/subscriptions.json";
    $fp = @fopen($file, "c+");
    if (!$fp) out(["ok" => false, "error" => T("AJAX.GW_NOT_WRITABLE")]);
    flock($fp, LOCK_EX);
    $raw = stream_get_contents($fp);
    $subs = json_decode($raw ?: '{"Subscriptions":[]}', true);
    if (!is_array($subs) || !isset($subs["Subscriptions"]) || !is_array($subs["Subscriptions"])) {
        flock($fp, LOCK_UN); fclose($fp);
        out(["ok" => false, "error" => T("AJAX.GW_UNREADABLE")]);
    }
    if ($raw !== "") @file_put_contents("$lbpdatadir/subscriptions.json.backup", $raw);
    $keep = []; $removed = 0; $have = [];
    foreach ($subs["Subscriptions"] as $e) {
        $id = $e["Id"] ?? "";
        if (strpos($id, "$base/") === 0) {
            if (!isset($want[$id])) { $removed++; continue; }
            $have[$id] = true;
            $e["Toms"] = $toms;
        }
        $keep[] = $e;
    }
    $added = 0;
    foreach (array_keys($want) as $t) {
        if (isset($have[$t])) continue;
        $keep[] = ["Id" => $t, "Toms" => $toms, "Noncached" => false, "resetaftersend" => false, "Jsonexpand" => false, "Json" => []];
        $added++;
    }
    $subs["Subscriptions"] = $keep;
    ftruncate($fp, 0);
    rewind($fp);
    fwrite($fp, json_encode($subs, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE));
    fflush($fp);
    flock($fp, LOCK_UN);
    fclose($fp);
    write_json_atomic("$lbpdatadir/gateway_topics.json", ["base" => $base, "topics" => array_keys($want)], 0644);
    out(["ok" => true, "count" => count($want), "added" => $added, "removed" => $removed]);

case 'diag':
    $token = trim(@file_get_contents("$lbpdatadir/api_token"));
    $info = read_json_file("$lbpdatadir/api.json", ["port" => 18765]);
    $ctx = stream_context_create(["http" => ["method" => "GET", "timeout" => 20, "ignore_errors" => true,
                                             "header" => "X-O2M-Token: $token\r\n"]]);
    $resp = $token !== "" ? @file_get_contents("http://127.0.0.1:" . intval($info["port"]) . "/api/diag", false, $ctx) : false;
    $d = $resp !== false ? json_decode($resp, true) : null;
    if (!is_array($d)) $d = ["error" => T("AJAX.DIAG_NO_DAEMON")];
    $d["loxberry"] = ["version" => (method_exists("LBSystem", "lbversion") ? LBSystem::lbversion() : null),
                      "php" => PHP_VERSION, "debian" => trim(@file_get_contents("/etc/debian_version")),
                      "language" => LBSystem::lblanguage()];
    $gen = read_json_file("$sysconf/general.json", []);
    $d["loxberry"]["mqtt_gateway"] = intval($gen["Mqtt"]["Gatewayversion"] ?? 1);
    $d["loxberry"]["miniservers"] = count(miniservers());
    $f = daemon_logfile();
    $d["log_file"] = $f !== "" ? basename($f) : null;
    $d["log_tail"] = preg_replace('/\b\d{1,3}(\.\d{1,3}){3}\b/', '<ip>', $f !== "" ? tail_file($f, 150) : "");
    header('Content-Disposition: attachment; filename="ochsner2mqtt-diagnose-' . date('Ymd-His') . '.json"');
    echo json_encode($d, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;

case 'config':
    $c = load_cfg();
    $c["has_password"] = $c["password"] !== "";
    $c["has_pin"] = $c["pin"] !== "";
    $c["password"] = "";
    $c["pin"] = "";
    out($c);

case 'save_config':
    $in = require_post();
    $c = load_cfg();
    $host = trim($in["host"] ?? "");
    if ($host !== "" && !filter_var($host, FILTER_VALIDATE_IP) && !preg_match('/^[A-Za-z0-9.-]{1,253}$/', $host))
        out(["ok" => false, "error" => T("AJAX.BAD_HOST")]);
    $c["host"] = $host;
    $c["port"] = max(1, min(65535, intval($in["port"] ?? 80)));
    $c["username"] = substr(trim($in["username"] ?? ""), 0, 64);
    if (!empty($in["password"])) $c["password"] = substr($in["password"], 0, 128);
    if (!empty($in["clear_password"])) $c["password"] = "";
    if (isset($in["pin"]) && $in["pin"] !== "") {
        if (!preg_match('/^[0-9]{1,12}$/', $in["pin"])) out(["ok" => false, "error" => T("AJAX.BAD_PIN")]);
        $c["pin"] = $in["pin"];
    }
    if (!empty($in["clear_pin"])) $c["pin"] = "";
    $c["poll_interval"] = max(10, min(3600, intval($in["poll_interval"] ?? 30)));
    $c["mqtt_enabled"] = !empty($in["mqtt_enabled"]);
    $topic = trim(preg_replace('/[^A-Za-z0-9_\-\/]/', '', $in["mqtt_topic"] ?? "ochsner"), "/");
    $c["mqtt_topic"] = $topic !== "" ? $topic : "ochsner";
    $c["publish_mode"] = (($in["publish_mode"] ?? "changes") === "all") ? "all" : "changes";
    $c["full_refresh_min"] = max(1, min(1440, intval($in["full_refresh_min"] ?? 10)));
    $c["include_technical"] = !empty($in["include_technical"]);
    $c["publish_raw_points"] = !empty($in["publish_raw_points"]);
    $c["writes_enabled"] = !empty($in["writes_enabled"]);
    $c["write_min_interval_sec"] = max(10, min(86400, intval($in["write_min_interval_sec"] ?? 120)));
    $c["write_max_per_day"] = max(0, min(1000, intval($in["write_max_per_day"] ?? 100)));
    $c["schema_buffer"] = in_array($in["schema_buffer"] ?? "auto", ["auto", "show", "hide"], true) ? $in["schema_buffer"] : "auto";
    $c["notify_alarms"] = !empty($in["notify_alarms"]);
    $c["notify_connection"] = !empty($in["notify_connection"]);
    if (!write_json_atomic($cfgfile, $c)) out(["ok" => false, "error" => T("AJAX.SAVE_FAILED")]);
    out(["ok" => true]);

case 'cmd':
    $in = require_post();
    $allowed = ["write", "rescan", "poll", "clear_alarm_history"];
    $a = $in["action"] ?? "";
    if (!in_array($a, $allowed, true)) out(["ok" => false, "error" => T("AJAX.UNKNOWN_ACTION")]);
    $cmd = ["id" => bin2hex(random_bytes(6)), "action" => $a];
    if ($a === "write") {
        $slug = $in["slug"] ?? "";
        if (!preg_match('/^[a-z0-9_]{1,120}$/', $slug)) out(["ok" => false, "error" => T("AJAX.BAD_POINT")]);
        $cmd["slug"] = $slug;
        $cmd["value"] = substr(strval($in["value"] ?? ""), 0, 64);
    }
    if (!is_dir($cmddir)) @mkdir($cmddir, 0755, true);
    $name = sprintf("%s/%d_%s.json", $cmddir, (int)(microtime(true) * 1000), $cmd["id"]);
    if (!write_json_atomic($name, $cmd, 0644)) out(["ok" => false, "error" => T("AJAX.CMD_FAILED")]);
    out(["ok" => true, "id" => $cmd["id"]]);

case 'api':
    // Weiterleitung an die lokale API des Daemons (nur 127.0.0.1, Token aus dem Datenordner)
    $ep = $_GET['ep'] ?? '';
    $routes = ["plants" => ["GET", "/api/plants"], "live" => ["GET", "/api/live"],
               "schedules" => ["GET", "/api/schedules"], "history" => ["GET", "/api/history"],
               "topics" => ["GET", "/api/topics"],
               "service" => ["POST", "/api/service"], "schedule_set" => ["POST", "/api/schedule/set"]];
    if (!isset($routes[$ep])) out(["error" => ["code" => "not_found", "message" => T("AJAX.UNKNOWN_ENDPOINT")]], 404);
    [$method, $path] = $routes[$ep];
    $body = "";
    if ($method === "POST") {
        require_post();  // CSRF-Prüfung; Rohdaten unverändert weitergeben (PHP würde {"0":…} zu einer Liste machen)
        $body = file_get_contents('php://input');
        if (strlen($body) > 200000) out(["error" => ["code" => "invalid", "message" => T("AJAX.TOO_LARGE")]], 413);
    } else {
        $qs = [];
        foreach (["force", "start", "end", "entity_ids"] as $k) if (isset($_GET[$k])) $qs[$k] = substr($_GET[$k], 0, 2000);
        if ($qs) $path .= "?" . http_build_query($qs);
    }
    $token = trim(@file_get_contents("$lbpdatadir/api_token"));
    $info = read_json_file("$lbpdatadir/api.json", ["port" => 18765]);
    if ($token === "") out(["error" => ["code" => "daemon", "message" => T("AJAX.DAEMON_NO_TOKEN")]], 503);
    $ctx = stream_context_create(["http" => [
        "method" => $method, "timeout" => 60, "ignore_errors" => true,
        "header" => "X-O2M-Token: $token\r\nContent-Type: application/json\r\n",
        "content" => $body,
    ]]);
    $resp = @file_get_contents("http://127.0.0.1:" . intval($info["port"]) . $path, false, $ctx);
    if ($resp === false) out(["error" => ["code" => "daemon", "message" => T("AJAX.DAEMON_DOWN")]], 503);
    $code = 200;
    if (isset($http_response_header[0]) && preg_match('/\s(\d{3})\s/', $http_response_header[0], $m)) $code = intval($m[1]);
    http_response_code($code);
    echo $resp;
    exit;

case 'daemon':
    $in = require_post();
    $op = $in["op"] ?? "status";
    if (!in_array($op, ["status", "restart"], true)) out(["ok" => false, "error" => T("AJAX.UNKNOWN_OP")]);
    $outp = [];
    $rc = 0;
    exec(escapeshellarg($ctl) . " " . $op . " 2>&1", $outp, $rc);
    out(["ok" => $rc === 0, "output" => implode("\n", $outp)]);

default:
    out(["ok" => false, "error" => T("AJAX.UNKNOWN_ACTION")], 400);
}
