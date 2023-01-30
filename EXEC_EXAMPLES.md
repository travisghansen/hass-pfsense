# Introduction

With the support of executing arbitrary `exec_php` and `exec_command` is
intended to serve as a set of community contributed examples of helpful
scripts/examples to achieve specific goals.

# PHP

## update dhcpd dns server

```
require_once '/etc/inc/config.inc';
global $config;
$interface = "lan";
$dns = "192.168.0.1";

if (!is_array($config["dhcpd"])) {
    $config["dhcpd"] = [];
}
if (!is_array($config["dhcpd"][$interface])) {
    $config["dhcpd"][$interface] = [];
}

$config["dhcpd"][$interface]["dnsserver"] = [];
$config["dhcpd"][$interface]["dnsserver"][] = $dns;

write_config("HASS - exec_php: update dhcpd dns server");

// reload services, etc here as necessary
$toreturn = [
    "data" => true,
];
```

## manage alias entries

```
require_once '/etc/inc/config.inc';
global $config;

// name given to the alias
$name = "baz";

// host
//$type = "host";
//$alias = "127.0.0.1";

// network
//$type = "network";
//$alias = "127.0.0.1/32";

// port
$type = "port";
$alias = "33";

$action = "add";
//$action = "remove";

foreach ($config["aliases"]["alias"] as &$value) {
    if ($value["type"] != $type) {
        continue;
    }
    if ($value["name"] != $name) {
        continue;
    }
    $parts = explode(" ", $value["address"]);
    switch($action) {
        case "add":
        if (!in_array($alias, $parts)) {
            $parts[] = $alias;
        }
        break;
        case "remove":
        if (($key = array_search($alias, $parts)) !== false) {
            unset($parts[$key]);
        }
        break;
    }
    $value["address"] = implode(" ", $parts);
    mark_subsystem_dirty("aliases");
    write_config("HASS - exec_php: update alias entry");

    $retval = 0;
    /* reload all components that use aliases */
    $retval |= filter_configure();

    if ($retval == 0) {
        clear_subsystem_dirty('aliases');
    }
}

// reload services, etc here as necessary
$toreturn = [
"data" => true,
];
```

## release / renew dhcp address on an interface

```
require_once '/etc/inc/interfaces.inc';

$if = "igb0";
$interface = "wan";
$ifdescr = "WAN";
$ipv = 4;
$sleep = 1;
    
// Copied from: /usr/local/www/status_interfaces.php
// Relinquish the DHCP lease from the server.
// $if is physical interface: ie: igb0
// $ifdescr is WAN, LAN, etc
// $ipv is '4' or '6'
function dhcp_relinquish_lease($if, $ifdescr, $ipv) {
        $leases_db = '/var/db/dhclient.leases.' . $if;
        $conf_file = '/var/etc/dhclient_'.$ifdescr.'.conf';
        $script_file = '/usr/local/sbin/pfSense-dhclient-script';
        $ipv = ((int) $ipv == 6) ? '-6' : '-4';

        if (file_exists($leases_db) && file_exists($script_file)) {
                mwexec('/usr/local/sbin/dhclient {$ipv} -d -r' .
                        ' -lf ' . escapeshellarg($leases_db) .
                        ' -cf ' . escapeshellarg($conf_file) .
                        ' -sf ' . escapeshellarg($script_file));
        }
}

dhcp_relinquish_lease($if, $ifdescr, $ipv);
interface_bring_down($interface);
sleep($sleep);
interface_configure($interface);

$toreturn = [
    "data" => true,
];
```

# command

## flush state table

```
/sbin/pfctl -F states
```

## kill states

```
/sbin/pfctl -k <source> -k <destination>
```
