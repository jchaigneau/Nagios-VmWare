# Nagios ESXi Check

Plugin Nagios basé sur `pyVmomi` permettant de superviser directement un ESXi,
sans vCenter.

Checks disponibles :

- CPU ESXi
- RAM ESXi
- VM actives
- espace libre des datastores

## Installation

Debian 13 :

----------------------------------
apt update
apt install python3 python3-venv

python3 -m venv /usr/local/nagios/venv
/usr/local/nagios/venv/bin/pip install --upgrade pyvmomi

----------------------------------

Copier le plugin :

/usr/local/nagios/libexec/check_esxi.py

Le shebang doit pointer vers :

#!/usr/local/nagios/venv/bin/python

Puis :

chmod 755 /usr/local/nagios/libexec/check_esxi.py
Credentials ESXi

----------------------------------

Les mots de passe sont stockés hors de la configuration Nagios :

/etc/nagios/esxi/
├── esxi01.pass
├── esxi02.pass
└── ...

Création :

mkdir -p /etc/nagios/esxi
chown nagios:nagios /etc/nagios/esxi
chmod 750 /etc/nagios/esxi

echo 'MOT_DE_PASSE' > /etc/nagios/esxi/esxi01.pass

chown nagios:nagios /etc/nagios/esxi/esxi01.pass
chmod 600 /etc/nagios/esxi/esxi01.pass

Le fichier .pass contient uniquement le mot de passe.

----------------------------------

Configuration Nagios

Ajouter les commandes de commands.cfg dans /usr/local/nagios/etc/objects/commands.cfg

copier esxi.cfg dans /usr/local/nagios/etc/objects/esxi.cfg
et l'adapter

Ajouter dans nagios.cfg :

cfg_file=/usr/local/nagios/etc/objects/esxi.cfg

Validation :

/usr/local/nagios/bin/nagios -v /usr/local/nagios/etc/nagios.cfg

Puis :

systemctl reload nagios
Utilisation
check_esxi.py --host <ESXI> --user <USER> \
  --password-file <PASSWORD_FILE> --mode cpu -w 80 -c 90

check_esxi.py --host <ESXI> --user <USER> \
  --password-file <PASSWORD_FILE> --mode ram -w 80 -c 90

check_esxi.py --host <ESXI> --user <USER> \
  --password-file <PASSWORD_FILE> --mode vms

check_esxi.py --host <ESXI> --user <USER> \
  --password-file <PASSWORD_FILE> --mode datastore -w 20 -c 10

Pour les datastores, les seuils sont exprimés en % d'espace libre.
