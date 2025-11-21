import re
import time
from typing import Dict, List, Optional
from .ssh_service import SSHService


class DiagnosticService:
    def __init__(self, ssh_service: SSHService):
        self.ssh = ssh_service

    def get_system_resources(self):
        """Получение информации о системных ресурсах с правильным расчетом CPU"""
        try:
            resources = {}

            # Загрузка CPU - правильный расчет
            cpu_result = self.ssh.execute_command("top -bn1 | grep 'Cpu(s)'")
            if cpu_result["success"]:
                cpu_line = cpu_result["output"]
                # Ищем процент использования CPU (user + system)
                if '%Cpu(s):' in cpu_line:
                    # Формат: %Cpu(s):  0.1 us,  0.1 sy,  0.0 ni, 99.8 id,  0.0 wa,  0.0 hi,  0.0 si,  0.0 st
                    parts = cpu_line.split(',')
                    us = float(parts[0].split('%Cpu(s):')[1].split('us')[0].strip())
                    sy = float(parts[1].split('sy')[0].strip())
                    cpu_usage = us + sy
                else:
                    # Альтернативный метод
                    cpu_result = self.ssh.execute_command(
                        "grep 'cpu ' /proc/stat | awk '{print (($2+$3+$4+$6+$7+$8)*100)/($2+$3+$4+$5+$6+$7+$8)}'")
                    if cpu_result["success"] and cpu_result["output"].strip():
                        cpu_usage = float(cpu_result["output"].strip())
                    else:
                        cpu_usage = 0
            else:
                cpu_usage = 0

            # Ограничиваем максимальное значение
            if cpu_usage > 100:
                print(f"⚠️ Исправляю некорректное значение CPU: {cpu_usage}% -> 100%")
                cpu_usage = 100

            resources['cpu_usage'] = round(cpu_usage, 1)

            # Память
            mem_result = self.ssh.execute_command("free | grep Mem")
            if mem_result["success"]:
                mem_parts = mem_result["output"].split()
                total_mem = int(mem_parts[1])
                used_mem = int(mem_parts[2])
                free_mem = int(mem_parts[3])
                usage_percent = (used_mem / total_mem) * 100 if total_mem > 0 else 0

                resources['memory'] = {
                    'total': self._format_bytes(total_mem * 1024),  # KB to bytes
                    'used': self._format_bytes(used_mem * 1024),
                    'free': self._format_bytes(free_mem * 1024),
                    'usage_percent': round(usage_percent, 1)
                }
            else:
                resources['memory'] = {
                    'total': 'N/A', 'used': 'N/A', 'free': 'N/A', 'usage_percent': 0
                }

            # Диск
            disk_result = self.ssh.execute_command("df / | tail -1")
            if disk_result["success"]:
                disk_parts = disk_result["output"].split()
                if len(disk_parts) >= 5:
                    total_disk = int(disk_parts[1]) * 1024  # 1K blocks to bytes
                    used_disk = int(disk_parts[2]) * 1024
                    usage_percent = int(disk_parts[4].replace('%', ''))

                    resources['disk'] = {
                        'total': self._format_bytes(total_disk),
                        'used': self._format_bytes(used_disk),
                        'usage_percent': usage_percent
                    }
                else:
                    resources['disk'] = {'usage_percent': 0}
            else:
                resources['disk'] = {'usage_percent': 0}

            return resources

        except Exception as e:
            print(f"❌ Ошибка получения ресурсов: {e}")
            return {
                'cpu_usage': 0,
                'memory': {'total': 'N/A', 'used': 'N/A', 'free': 'N/A', 'usage_percent': 0},
                'disk': {'total': 'N/A', 'used': 'N/A', 'usage_percent': 0}
            }

    def _format_bytes(self, bytes_size):
        """Форматирует байты в читаемый вид"""
        if bytes_size == 0:
            return "0 B"

        sizes = ['B', 'KB', 'MB', 'GB', 'TB']
        i = 0
        while bytes_size >= 1024 and i < len(sizes) - 1:
            bytes_size /= 1024.0
            i += 1

        return f"{bytes_size:.1f} {sizes[i]}"

    def _parse_system_resources(self, results: Dict) -> Dict:
        """Парсинг сырых данных о ресурсах"""
        parsed = {}

        # Парсим uptime
        if results["uptime"]["success"]:
            uptime_output = results["uptime"]["data"]
            # Извлекаем load average: 12:00:00 up 10 days,  load average: 0.5, 0.3, 0.1
            load_match = re.search(r'load average:\s+([\d.]+),\s+([\d.]+),\s+([\d.]+)', uptime_output)
            if load_match:
                parsed["load_average"] = {
                    "1min": float(load_match.group(1)),
                    "5min": float(load_match.group(2)),
                    "15min": float(load_match.group(3))
                }

        # Парсим память
        if results["memory"]["success"]:
            memory_output = results["memory"]["data"]
            # Пример: total used free shared buff/cache available
            lines = memory_output.split('\n')
            if len(lines) > 1:
                headers = lines[0].split()
                values = lines[1].split()
                if 'total' in headers and 'used' in headers:
                    total_idx = headers.index('total')
                    used_idx = headers.index('used')
                    parsed["memory"] = {
                        "total": values[total_idx],
                        "used": values[used_idx],
                        "usage_percent": self._calculate_usage_percent(values[used_idx], values[total_idx])
                    }

        # Парсим диск
        if results["disk"]["success"]:
            disk_output = results["disk"]["data"]
            lines = disk_output.split('\n')
            if len(lines) > 1:
                # Находим строку с корневым разделом
                for line in lines:
                    if '/ ' in line:
                        parts = line.split()
                        if len(parts) >= 5:
                            parsed["disk"] = {
                                "total": parts[1],
                                "used": parts[2],
                                "available": parts[3],
                                "usage_percent": parts[4].replace('%', '')
                            }
                        break

        # Парсим CPU
        if results["cpu"]["success"]:
            cpu_output = results["cpu"]["data"]
            # Ищем строку с %Cpu(s)
            for line in cpu_output.split('\n'):
                if '%Cpu(s)' in line:
                    cpu_match = re.search(r'(\d+\.\d+) us', line)
                    if cpu_match:
                        parsed["cpu_usage"] = float(cpu_match.group(1))
                    break

        return parsed

    def _calculate_usage_percent(self, used: str, total: str) -> float:
        """Вычисление процента использования"""
        try:
            # Конвертируем человеко-читаемые размеры в байты
            def to_bytes(size_str):
                multipliers = {'G': 1024 ** 3, 'M': 1024 ** 2, 'K': 1024}
                for unit, multiplier in multipliers.items():
                    if unit in size_str:
                        return float(size_str.replace(unit, '')) * multiplier
                return float(size_str)

            used_bytes = to_bytes(used)
            total_bytes = to_bytes(total)
            return round((used_bytes / total_bytes) * 100, 2)
        except:
            return 0.0

    def get_running_processes(self, limit: int = 10, sort_by: str = "cpu") -> List[Dict]:
        """Получение списка запущенных процессов"""
        if sort_by == "cpu":
            command = f"ps aux --sort=-%cpu | head -{limit + 1}"
        else:
            command = f"ps aux --sort=-%mem | head -{limit + 1}"

        result = self.ssh.execute_command(command)

        processes = []
        if result["success"]:
            lines = result["output"].split('\n')[1:]  # Пропускаем заголовок
            for line in lines[:limit]:
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 11:
                        process = {
                            "user": parts[0],
                            "pid": int(parts[1]),
                            "cpu_percent": float(parts[2]),
                            "memory_percent": float(parts[3]),
                            "command": ' '.join(parts[10:]),
                            "start_time": parts[8]
                        }
                        processes.append(process)

        return processes

    def get_network_info(self) -> Dict:
        """Получение сетевой информации"""
        commands = {
            "connections": "netstat -tulpn",
            "interfaces": "ip addr show",
            "bandwidth": "cat /proc/net/dev | head -5"
        }

        results = {}
        for key, command in commands.items():
            result = self.ssh.execute_command(command)
            results[key] = result["output"] if result["success"] else result["error"]

        return results

    def get_services_status(self) -> List[Dict]:
        """Получение статуса системных сервисов"""
        command = "systemctl list-units --type=service --state=running --no-pager"
        result = self.ssh.execute_command(command)

        services = []
        if result["success"]:
            lines = result["output"].split('\n')
            for line in lines[1:]:  # Пропускаем заголовок
                if line.strip() and '●' not in line:  # Пропускаем строки с ошибками
                    parts = line.split()
                    if len(parts) >= 4:
                        service = {
                            "name": parts[0],
                            "load": parts[1],
                            "active": parts[2],
                            "sub": parts[3],
                            "description": ' '.join(parts[4:])
                        }
                        services.append(service)

        return services

    def quick_diagnostic(self) -> Dict:
        """Быстрая диагностика системы"""
        start_time = time.time()

        resources = self.get_system_resources()
        processes = self.get_running_processes(limit=5)
        services = self.get_services_status()[:10]  # Первые 10 сервисов
        network = self.get_network_info()

        execution_time = round(time.time() - start_time, 2)

        return {
            "success": True,
            "resources": resources,
            "top_processes": processes,
            "services": services,
            "network_summary": network,
            "execution_time": execution_time,
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S')
        }