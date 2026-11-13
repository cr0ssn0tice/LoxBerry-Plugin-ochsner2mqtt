<?php
// Test-Stub für LoxBerry::System (ohne LoxBerry-Quellcode)
$base = getenv('O2M_T');
$lbpconfigdir = "$base/cfg"; $lbpdatadir = "$base/data"; $lbplogdir = "$base/log";
$lbhomedir = "$base/lbhome"; $lbpbindir = getenv('O2M_BIN'); $lbptemplatedir = getenv('O2M_TPL');
$lbpplugindir = "ochsner2mqtt";
class LBSystem {
    static function pluginversion() { return "0.4.0"; }
    static function lbversion() { return "4.0.1.6"; }
    static function lblanguage() {
        if (!empty($_GET['lang'])) return substr($_GET['lang'], 0, 2);
        $g = json_decode(@file_get_contents($GLOBALS['lbhomedir'] . "/config/system/general.json"), true);
        return $g['Base']['Lang'] ?? 'de';
    }
    static function readlanguage($file = "language.ini") {
        global $lbptemplatedir;
        $L = [];
        $name = preg_replace('/\.[^.]*$/', '', $file);
        $lang = self::lblanguage();
        foreach (array_unique([$lang, "en"]) as $l) {
            $f = "$lbptemplatedir/lang/{$name}_$l.ini";
            if (!is_file($f)) continue;
            $sec = "default";
            foreach (file($f) as $line) {
                $line = trim($line);
                if ($line === "" || strpos("#/;", $line[0]) !== false) continue;
                if ($line[0] === "[") { $sec = substr($line, 1, strpos($line, "]") - 1); continue; }
                [$k, $v] = explode("=", $line, 2);
                if (!isset($L["$sec." . rtrim($k)])) $L["$sec." . rtrim($k)] = ltrim($v);
            }
        }
        return $L;
    }
    static function plugindata() { return ["PLUGINDB_MD5_CHECKSUM" => "", "PLUGINDB_LOGLEVEL" => 6]; }
    static function get_miniservers() { return [1 => ["Name" => "Haus"], 2 => ["Name" => "Garage"]]; }
}
