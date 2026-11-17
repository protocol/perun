<?php
function load_prefs() {
    $prefs = unserialize($_COOKIE['prefs']);
    echo $prefs['theme'];
}
