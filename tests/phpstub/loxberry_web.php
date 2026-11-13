<?php
// Test-Stub für LoxBerry::Web (ohne LoxBerry-Quellcode). Mit O2M_LBCSS=<Ordner> wird das echte CSS
// des LoxBerry-Design-Systems eingebunden. Realistischer: tests/dev_env.sh mit LBSRC (echtes SDK).
require_once "loxberry_system.php";
class LBWeb {
    static function lbheader($t, $u, $h, $n = false) {
        global $navbar, $htmlhead;
        $dir = getenv('O2M_LBCSS');
        $theme = getenv('O2M_LBTHEME') ?: 'classic-lb';
        echo "<!DOCTYPE html><html lang=\"" . LBSystem::lblanguage() . "\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>" . htmlspecialchars($t) . "</title>";
        if ($dir) foreach (["design-tokens", "main", "components", "theme-$theme"] as $f)
            if (is_file("$dir/$f.css")) echo "<style>" . file_get_contents("$dir/$f.css") . "</style>";
        echo $htmlhead ?? "";
        echo "</head><body class=\"theme-$theme\"><div class=\"lb-main\" style=\"margin-left:0\"><header class=\"lb-header\"><h1 class=\"lb-header-title\">" . htmlspecialchars($t) . "</h1></header>";
        if (is_array($navbar)) {
            echo "<nav style=\"display:flex;gap:4px;flex-wrap:wrap;padding:8px 16px;border-bottom:1px solid var(--lb-border-color,#ddd)\">";
            foreach ($navbar as $nb) echo "<a href=\"" . htmlspecialchars($nb['URL']) . "\" style=\"padding:6px 12px;border-radius:6px;text-decoration:none;" . (!empty($nb['active']) ? "background:var(--lb-primary,#6dac20);color:#fff" : "color:inherit") . "\">" . htmlspecialchars($nb['Name']) . "</a>";
            echo "</nav>";
        }
        echo "<div style=\"padding:16px\">";
    }
    static function lbfooter() { echo "</div></div></body></html>"; }
}
// wie LBTemplate aus loxberry_web.php (nur TMPL_VAR)
class LBTemplate {
    private $v = []; private $t;
    function __construct($path) { $this->t = file_get_contents($path); }
    function param($k, $val) { $this->v[$k] = $val; }
    function paramArray($a) { foreach ($a as $k => $val) $this->param($k, $val); }
    function outputString() { $t = $this->t; foreach ($this->v as $k => $val) $t = str_replace("<TMPL_VAR $k>", $val, $t); return $t; }
}
