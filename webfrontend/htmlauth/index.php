<?php
// index.php – Weboberfläche des Plugins "Ochsner OTS"
// LoxBerry Design System ohne jQuery Mobile ("nojqm"), Texte aus templates/lang/language_<sprache>.ini,
// eigene Styles/Skripte über $htmlhead (css/o2m.css, js/o2m.js), Hilfe aus templates/help/help.html.
require_once "loxberry_system.php";
require_once "loxberry_web.php";

$L = LBSystem::readlanguage("language.ini");
$lang = LBSystem::lblanguage();
$version = LBSystem::pluginversion();
$plugin = LBSystem::plugindata();
$v = urlencode($version);

$forms = ["app" => "NAV.APP", "overview" => "NAV.OVERVIEW", "values" => "NAV.VALUES", "edit" => "NAV.EDIT",
          "loxone" => "NAV.LOXONE", "settings" => "NAV.SETTINGS", "log" => "NAV.LOG"];
$form = $_GET['form'] ?? 'app';
if (!array_key_exists($form, $forms)) $form = 'app';

$navbar = [];
foreach ($forms as $key => $label) {
    $item = ['Name' => $L[$label] ?? $key, 'URL' => "index.php?form=$key", 'active' => ($form === $key)];
    // Zähler der LoxBerry-Benachrichtigungen des Plugins (Störungen, Dienst)
    if ($key === 'overview') { $item['Notify_Package'] = $lbpplugindir; $item['Notify_Name'] = 'alarm'; }
    if ($key === 'log') { $item['Notify_Package'] = $lbpplugindir; $item['Notify_Name'] = 'daemon'; }
    $navbar[] = $item;
}

$jsonflags = JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT | JSON_UNESCAPED_UNICODE;
$htmlhead = '<link rel="stylesheet" href="css/o2m.css?v=' . $v . '">' . "\n"
          . '<script>window.O2M_L = ' . json_encode($L, $jsonflags) . ';</script>' . "\n";
if ($form === 'app') $htmlhead .= '<link rel="stylesheet" href="css/o2m-app.css?v=' . $v . '">' . "\n";
else $htmlhead .= '<script src="js/o2m.js?v=' . $v . '" defer></script>' . "\n";

// Hilfe-Link: LBWeb übernimmt ihn nur zuverlässig über die globale Variable $helplink
$helplink = $L['COMMON.HELPLINK'] ?? '';

LBWeb::lbheader(($L['COMMON.PAGETITLE'] ?? 'Ochsner OTS') . " V$version", $helplink, "help.html", "nojqm");

if ($form === 'app') {
    $t = new LBTemplate("$lbptemplatedir/app.html");
} else {
    $t = new LBTemplate("$lbptemplatedir/page.html");
    $t->param('O2M_FORM', $form);
    $t->param('O2M_PACKAGE', htmlspecialchars($lbpplugindir));
    $t->param('O2M_PLUGINMD5', htmlspecialchars($plugin['PLUGINDB_MD5_CHECKSUM'] ?? ''));
    $t->param('O2M_LOGLEVEL', intval($plugin['PLUGINDB_LOGLEVEL'] ?? 3));
    // wie LBWeb::loglist_url(['NAME' => 'Daemon'])
    $t->param('O2M_LOGLIST_URL', "/admin/system/logmanager.cgi?package=" . urlencode($lbpplugindir) . "&amp;name=Daemon");
}
$t->paramArray($L);
$t->param('O2M_VERSION', $v);
$t->param('O2M_LANG', htmlspecialchars($lang));
echo $t->outputString();

LBWeb::lbfooter();
