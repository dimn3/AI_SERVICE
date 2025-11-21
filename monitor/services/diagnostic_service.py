import re
import time
from typing import Dict, List, Optional
from .ssh_service import SSHService


class DiagnosticService:
    def __init__(self, ssh_service: SSHService):
        self.ssh = ssh_service

    def get_system_resources(self) -> Dict:
        """Получение информации о системных ресурсах"""
        commands = {
            "uptime": "uptime",
            "memory": "free -h",
            "disk": "df -h /",
            "cpu": "top -bn1 | head -5"
        }

        results = {}
        for key, command in commands.items():
            result = self.ssh.execute_command(command)
            results[key] = {
                "success": result["success"],
                "data": result["output"] if result["success"] else result["error"]
            }

        # Парсим результаты
        parsed_data = self._parse_system_resources(results)
        return parsed_data

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