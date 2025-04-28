import requests
from dcim.models import Device, Site
from virtualization.models import (
    VirtualMachine, Cluster, ClusterType,
    VMInterface, IPAddress
)
from tenancy.models import Tenant
from extras.models import CustomField

# Конфиг Nutanix
NUTANIX_URL = "https://172.16.100.30:9440/api/nutanix/v3"
AUTH = ("admin", "sDV}2[PG;:K*tz7FH3yJ5Y")

def create_custom_fields():
    """Создает кастомные поля в NetBox при первом запуске"""
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

def sync_nutanix_full():
    create_custom_fields()
    
    # Создаем структуру в NetBox
    cluster_type, _ = ClusterType.objects.get_or_create(name="Nutanix")
    cluster, _ = Cluster.objects.get_or_create(
        name="Nutanix Cluster",
        type=cluster_type,
        site=Site.objects.get_or_create(name="Nutanix DC", slug="nutanix-dc")[0]
    )

    # Получаем ВМ из Nutanix
    vms = requests.post(
        f"{NUTANIX_URL}/vms/list",
        auth=AUTH,
        verify=False,
        json={"kind": "vm", "length": 250}  # 250 - лимит запроса
    ).json().get('entities', [])

    for vm in vms:
        spec = vm.get('spec', {})
        resources = spec.get('resources', {})
        metadata = vm.get('metadata', {})

        # Основные параметры ВМ
        vm_obj, created = VirtualMachine.objects.update_or_create(
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

        # Сетевые интерфейсы и IP-адреса
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
                
                # IP-адреса
                for ip_data in nic.get('ip_endpoint_list', []):
                    ip, _ = IPAddress.objects.get_or_create(
                        address=ip_data.get('ip'),
                        defaults={
                            'assigned_object_type': 'virtualization.vminterface',
                            'assigned_object_id': vif.id
                        }
                    )

        # CPU и хосты (дополнительные данные)
        host_data = requests.get(
            f"{NUTANIX_URL}/hosts/{resources.get('host_reference', {}).get('uuid')}",
            auth=AUTH,
            verify=False
        ).json()
        
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

if __name__ == '__main__':
    sync_nutanix_full()