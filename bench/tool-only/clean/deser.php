<?php
function load_prefs() {
    $prefs = json_decode($_COOKIE['prefs'], true);
    echo htmlspecialchars($prefs['theme'] ?? 'light');
}
