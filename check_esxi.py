#!/usr/local/nagios/venv/bin/python

import argparse
import atexit
import getpass
import os
import ssl
import sys

from pyVim import connect
from pyVmomi import vim


OK = 0
WARNING = 1
CRITICAL = 2
UNKNOWN = 3


def nagios_exit(code, message):
    print(message)
    sys.exit(code)


def read_password(args):
    if args.password_file:
        try:
            with open(args.password_file, "r") as f:
                return f.read().strip()
        except Exception as e:
            nagios_exit(UNKNOWN, f"UNKNOWN - impossible de lire le fichier mot de passe: {e}")

    if args.password:
        return args.password

    return getpass.getpass("Mot de passe ESXi : ")


def connect_esxi(args):
    password = read_password(args)

    try:
        context = ssl._create_unverified_context()

        si = connect.SmartConnect(
            host=args.host,
            user=args.user,
            pwd=password,
            port=args.port,
            sslContext=context
        )

        atexit.register(connect.Disconnect, si)

        return si

    except Exception as e:
        nagios_exit(
            UNKNOWN,
            f"UNKNOWN - connexion ESXi impossible: {e}"
        )


def get_host(content):
    view = content.viewManager.CreateContainerView(
        content.rootFolder,
        [vim.HostSystem],
        True
    )

    hosts = view.view
    view.Destroy()

    if not hosts:
        nagios_exit(UNKNOWN, "UNKNOWN - aucun HostSystem trouvé")

    return hosts[0]


def check_cpu(host, warning, critical):
    try:
        summary = host.summary
        quick = summary.quickStats
        hardware = summary.hardware

        usage_mhz = quick.overallCpuUsage or 0
        total_mhz = hardware.cpuMhz * hardware.numCpuCores

        if total_mhz <= 0:
            nagios_exit(UNKNOWN, "UNKNOWN - capacité CPU ESXi invalide")

        percent = (usage_mhz / total_mhz) * 100

        if percent >= critical:
            status = CRITICAL
            state = "CRITICAL"
        elif percent >= warning:
            status = WARNING
            state = "WARNING"
        else:
            status = OK
            state = "OK"

        print(
            f"{state} - CPU ESXi: {percent:.1f}% "
            f"(usage={usage_mhz}MHz / total={total_mhz}MHz) "
            f"| 'cpu_usage'={percent:.1f}%;{warning};{critical};0;100"
        )

        sys.exit(status)

    except Exception as e:
        nagios_exit(UNKNOWN, f"UNKNOWN - erreur CPU: {e}")


def check_ram(host, warning, critical):
    try:
        summary = host.summary
        quick = summary.quickStats
        hardware = summary.hardware

        total_mb = hardware.memorySize / (1024 * 1024)
        used_mb = quick.overallMemoryUsage or 0

        if total_mb <= 0:
            nagios_exit(UNKNOWN, "UNKNOWN - mémoire ESXi invalide")

        percent = (used_mb / total_mb) * 100
        free_mb = total_mb - used_mb

        if percent >= critical:
            status = CRITICAL
            state = "CRITICAL"
        elif percent >= warning:
            status = WARNING
            state = "WARNING"
        else:
            status = OK
            state = "OK"

        print(
            f"{state} - RAM ESXi: {percent:.1f}% utilisée "
            f"({used_mb:.0f}MB / {total_mb:.0f}MB, "
            f"libre={free_mb:.0f}MB) "
            f"| 'ram_usage'={percent:.1f}%;{warning};{critical};0;100"
        )

        sys.exit(status)

    except Exception as e:
        nagios_exit(UNKNOWN, f"UNKNOWN - erreur RAM: {e}")


def check_vms(host, warning, critical):
    try:
        vms = host.vm

        total = len(vms)
        active = 0

        for vm in vms:
            if vm.runtime.powerState == vim.VirtualMachinePowerState.poweredOn:
                active += 1

        if active >= critical:
            status = CRITICAL
            state = "CRITICAL"
        elif active >= warning:
            status = WARNING
            state = "WARNING"
        else:
            status = OK
            state = "OK"

        print(
            f"{state} - VM actives: {active}/{total} "
            f"| 'vms_active'={active};{warning};{critical};0;"
        )

        sys.exit(status)

    except Exception as e:
        nagios_exit(UNKNOWN, f"UNKNOWN - erreur VM: {e}")


def check_datastore(content, datastore_name, warning, critical):
    try:
        view = content.viewManager.CreateContainerView(
            content.rootFolder,
            [vim.Datastore],
            True
        )

        datastores = list(view.view)
        view.Destroy()

        if datastore_name:
            datastores = [
                ds for ds in datastores
                if ds.name == datastore_name
            ]

            if not datastores:
                nagios_exit(
                    UNKNOWN,
                    f"UNKNOWN - datastore '{datastore_name}' introuvable"
                )

        worst_status = OK
        results = []

        for ds in datastores:
            summary = ds.summary

            capacity = summary.capacity
            free = summary.freeSpace

            if capacity <= 0:
                continue

            free_percent = (free / capacity) * 100
            used_percent = 100 - free_percent

            free_gb = free / (1024 ** 3)
            capacity_gb = capacity / (1024 ** 3)

            if free_percent <= critical:
                status = CRITICAL
                state = "CRITICAL"
                worst_status = max(worst_status, CRITICAL)

            elif free_percent <= warning:
                status = WARNING
                state = "WARNING"
                worst_status = max(worst_status, WARNING)

            else:
                status = OK
                state = "OK"

            safe_name = ds.name.replace("'", "_").replace(" ", "_")

            results.append(
                f"{state} {ds.name}: "
                f"{free_percent:.1f}% libre "
                f"({free_gb:.1f}GB / {capacity_gb:.1f}GB)"
                f" | '{safe_name}_free'={free_gb:.1f}GB;"
                f"{capacity_gb * warning / 100:.1f};"
                f"{capacity_gb * critical / 100:.1f};0;"
                f"{capacity_gb:.1f}"
            )

        if not results:
            nagios_exit(UNKNOWN, "UNKNOWN - aucun datastore exploitable")

        # Pour plusieurs datastores, on affiche une ligne globale.
        print(
            f"{'CRITICAL' if worst_status == CRITICAL else 'WARNING' if worst_status == WARNING else 'OK'} "
            f"- Datastores: " +
            " | ".join(results)
        )

        sys.exit(worst_status)

    except Exception as e:
        nagios_exit(
            UNKNOWN,
            f"UNKNOWN - erreur datastore: {e}"
        )


def main():
    parser = argparse.ArgumentParser(
        description="Plugin Nagios - supervision directe VMware ESXi via pyVmomi"
    )

    parser.add_argument(
        "--host",
        required=True,
        help="Adresse IP ou nom DNS de l'ESXi"
    )

    parser.add_argument(
        "--port",
        type=int,
        default=443,
        help="Port HTTPS ESXi (défaut: 443)"
    )

    parser.add_argument(
        "--user",
        default="root",
        help="Utilisateur ESXi"
    )

    parser.add_argument(
        "--password",
        help="Mot de passe ESXi (déconseillé en production)"
    )

    parser.add_argument(
        "--password-file",
        help="Fichier contenant le mot de passe ESXi"
    )

    parser.add_argument(
        "--mode",
        required=True,
        choices=[
            "cpu",
            "ram",
            "vms",
            "datastore"
        ],
        help="Type de contrôle"
    )

    parser.add_argument(
        "-w",
        "--warning",
        type=float,
        default=80,
        help="Seuil WARNING"
    )

    parser.add_argument(
        "-c",
        "--critical",
        type=float,
        default=90,
        help="Seuil CRITICAL"
    )

    parser.add_argument(
        "-d",
        "--datastore",
        help="Nom du datastore à contrôler"
    )

    args = parser.parse_args()
    if args.mode == "datastore":
        if args.warning <= args.critical:
            nagios_exit(
                UNKNOWN,
                "UNKNOWN - pour un datastore, WARNING doit être supérieur à CRITICAL"
            )
    else:
        if args.warning >= args.critical:
            nagios_exit(
                UNKNOWN,
                "UNKNOWN - WARNING doit être inférieur à CRITICAL"
            )

    si = connect_esxi(args)
    content = si.RetrieveContent()

    host = get_host(content)

    if args.mode == "cpu":
        check_cpu(host, args.warning, args.critical)

    elif args.mode == "ram":
        check_ram(host, args.warning, args.critical)

    elif args.mode == "vms":
        check_vms(host, args.warning, args.critical)

    elif args.mode == "datastore":
        check_datastore(
            content,
            args.datastore,
            args.warning,
            args.critical
        )


if __name__ == "__main__":
    main()
