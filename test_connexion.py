from pyVim import connect
from pyVmomi import vim
import ssl
import atexit
import getpass

host = input("IP/nom ESXi : ")
user = input("Utilisateur : ")
password = getpass.getpass("Mot de passe : ")

context = ssl._create_unverified_context()

si = connect.SmartConnect(
    host=host,
    user=user,
    pwd=password,
    port=443,
    sslContext=context
)

atexit.register(connect.Disconnect, si)

content = si.RetrieveContent()

view = content.viewManager.CreateContainerView(
    content.rootFolder,
    [vim.VirtualMachine],
    True
)

vms = view.view

print(f"\nVM trouvées : {len(vms)}")

for vm in vms:
    print(f" - {vm.name} : {vm.runtime.powerState}")

view.Destroy()
