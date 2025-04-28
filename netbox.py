import os
import sys
from pathlib import Path

# Добавляем путь к NetBox в PYTHONPATH
netbox_path = str(Path('/opt/netbox/netbox').resolve())
if netbox_path not in sys.path:
    sys.path.insert(0, netbox_path)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
import django
django.setup()

from dcim.models import Device, DeviceType, Manufacturer, Site
from virtualization.models import VirtualMachine, Cluster, ClusterType, VMInterface
from ipam.models import IPAddress
from tenancy.models import Tenant
from extras.models import CustomField
import requests

class Script:
    def __init__(self):
        self.NUTANIX_URL = "https://172.16.100.30:9440/api/nutanix/v3"
        self.AUTH = ("admin", 'sDV}2[PG;:K*tz7FH3yJ5Y')

    def create_custom_fields(self):
        """Создает кастомные поля в NetBox"""
        CustomField.objects.get_or_create(
            name='nutanix_uuid',
            type='text',
            label='Nutanix UUID'
        )
        CustomField.objects.get_or_create(
            name='nutanix_host',
            type='text',
            label='Nutanix Host'
        )

    def sync_nutanix_vms(self):
        self.create_custom_fields()
        
        cluster_type, _ = ClusterType.objects.get_or_create(name="Nutanix")
        cluster, _ = Cluster.objects.get_or_create(
            name="Nutanix Cluster",
            type=cluster_type,
            site=Site.objects.get_or_create(name="Nutanix DC", slug="nutanix-dc")[0]
        )

        response = requests.post(
            f"{self.NUTANIX_URL}/vms/list",
            auth=self.AUTH,
            verify=False,
            json={"kind": "vm", "length": 250}
        )
        vms = response.json().get('entities', [])

        for vm in vms:
            self.process_vm(vm, cluster)

    def process_vm(self, vm, cluster):
        spec = vm.get('spec', {})
        resources = spec.get('resources', {})
        metadata = vm.get('metadata', {})

        vm_obj, _ = VirtualMachine.objects.update_or_create(
            name=spec.get('name'),
            defaults={
                'status': 'active' if resources.get('power_state') == 'ON' else 'offline',
                'cluster': cluster,
                'vcpus': resources.get('num_vcpus', 1),
                'memory': resources.get('memory_size_mib', 1024),
                'disk': sum(d.get('disk_size_bytes', 0) for d in resources.get('disk_list', [])) // 1024 // 1024,
                'tenant': Tenant.objects.get_or_create(
                    name=metadata.get('project_reference', {}).get('name', 'Nutanix')
                )[0],
                'custom_fields': {
                    'nutanix_uuid': metadata.get('uuid'),
                    'nutanix_host': resources.get('host_reference', {}).get('name')
                }
            }
        )

        self.process_interfaces(vm_obj, resources)
        self.process_host(resources)

    def process_interfaces(self, vm_obj, resources):
        for nic in resources.get('nic_list', []):
            if nic.get('is_connected', False):
                vif, _ = VMInterface.objects.update_or_create(
                    virtual_machine=vm_obj,
                    name=f"vNIC-{nic.get('mac_address', '')[-4:]}",
                    defaults={
                        'mac_address': nic.get('mac_address'),
                        'enabled': nic.get('is_connected')
                    }
                )
                
                for ip_data in nic.get('ip_endpoint_list', []):
                    IPAddress.objects.get_or_create(
                        address=ip_data.get('ip'),
                        defaults={
                            'assigned_object_type': 'virtualization.vminterface',
                            'assigned_object_id': vif.id
                        }
                    )

    def process_host(self, resources):
        host_uuid = resources.get('host_reference', {}).get('uuid')
        if not host_uuid:
            return

        response = requests.get(
            f"{self.NUTANIX_URL}/hosts/{host_uuid}",
            auth=self.AUTH,
            verify=False
        )
        host_data = response.json()

        if host_data:
            Device.objects.update_or_create(
                name=host_data.get('spec', {}).get('name'),
                defaults={
                    'device_type': DeviceType.objects.get_or_create(
                        manufacturer=Manufacturer.objects.get_or_create(name="Nutanix")[0],
                        model=host_data.get('spec', {}).get('resources', {}).get('hypervisor_type')
                    )[0],
                    'custom_fields': {
                        'cpu_model': host_data.get('spec', {}).get('resources', {}).get('cpu_model'),
                        'cpu_cores': host_data.get('spec', {}).get('resources', {}).get('num_cpu_cores'),
                        'cpu_sockets': host_data.get('spec', {}).get('resources', {}).get('num_cpu_sockets')
                    }
                }
            )

def run(*args, **kwargs):
    script = Script()
    script.sync_nutanix_vms()

if __name__ == '__main__':
    run()