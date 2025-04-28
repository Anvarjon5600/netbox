# Nutanix-NetBox Sync Integration

![Nutanix+NetBox](https://i.imgur.com/JZyhW3p.png)

Автоматическая синхронизация виртуальных машин из Nutanix в NetBox с полной детализацией.

## 🔧 Требования
- NetBox 3.5+
- Nutanix Prism Central 5.20+
- Python 3.8+

## 🚀 Установка
1. Склонируйте репозиторий на сервер NetBox:
```bash
git clone https://github.com/ваш-репозиторий /opt/netbox/netbox/scripts/nutanix_integration

## Установите зависимости:
```bash
sudo -u netbox /opt/netbox/venv/bin/pip install -r /opt/netbox/netbox/scripts/nutanix_integration/requirements.txt