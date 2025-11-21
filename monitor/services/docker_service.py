import re
import json
from typing import Dict, List, Optional
from .ssh_service import SSHService


class DockerService:
    def __init__(self, ssh_service: SSHService):
        self.ssh = ssh_service

    def list_containers(self, all_containers: bool = False) -> List[Dict]:
        """Получение списка Docker контейнеров"""
        if all_containers:
            command = "docker ps -a --format '{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}'"
        else:
            command = "docker ps --format '{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}'"

        result = self.ssh.execute_command(command)
        containers = []

        if result["success"] and result["output"]:
            for line in result["output"].split('\n'):
                if line.strip():
                    parts = line.split('|')
                    if len(parts) >= 5:
                        container = {
                            "id": parts[0][:12],  # Берем короткий ID
                            "name": parts[1],
                            "image": parts[2],
                            "status": parts[3],
                            "ports": parts[4],
                            "is_running": "Up" in parts[3]
                        }
                        containers.append(container)

        return containers

    def get_container_info(self, container_id: str) -> Dict:
        """Получение детальной информации о контейнере"""
        # Базовая информация
        command = f"docker inspect {container_id}"
        result = self.ssh.execute_command(command)

        if not result["success"]:
            return {"error": f"Контейнер {container_id} не найден"}

        try:
            inspect_data = json.loads(result["output"])[0]

            # Статистика в реальном времени
            stats_command = f"docker stats {container_id} --no-stream --format '{{{{.Container}}}}|{{{{.Name}}}}|{{{{.CPUPerc}}}}|{{{{.MemUsage}}}}|{{{{.NetIO}}}}|{{{{.BlockIO}}}}|{{{{.PIDs}}}}'"
            stats_result = self.ssh.execute_command(stats_command)

            stats = {}
            if stats_result["success"] and stats_result["output"]:
                stats_parts = stats_result["output"].split('|')
                if len(stats_parts) >= 6:
                    stats = {
                        "cpu_percent": stats_parts[2].strip(),
                        "memory_usage": stats_parts[3].strip(),
                        "network_io": stats_parts[4].strip(),
                        "block_io": stats_parts[5].strip(),
                        "pids": stats_parts[6].strip() if len(stats_parts) > 6 else "0"
                    }

            return {
                "id": container_id,
                "name": inspect_data.get("Name", "").lstrip('/'),
                "image": inspect_data.get("Config", {}).get("Image", ""),
                "status": inspect_data.get("State", {}).get("Status", ""),
                "running": inspect_data.get("State", {}).get("Running", False),
                "created": inspect_data.get("Created", ""),
                "ports": inspect_data.get("NetworkSettings", {}).get("Ports", {}),
                "ip_address": inspect_data.get("NetworkSettings", {}).get("IPAddress", ""),
                "mounts": inspect_data.get("Mounts", []),
                "env_variables": inspect_data.get("Config", {}).get("Env", []),
                "stats": stats
            }
        except json.JSONDecodeError:
            return {"error": "Ошибка парсинга информации о контейнере"}

    def get_container_logs(self, container_id: str, lines: int = 50, follow: bool = False) -> Dict:
        """Получение логов контейнера"""
        if follow:
            # Для реального времени - здесь будет WebSocket логика
            command = f"docker logs {container_id} --tail {lines} -f 2>&1"
        else:
            command = f"docker logs {container_id} --tail {lines} 2>&1"

        result = self.ssh.execute_command(command)

        return {
            "success": result["success"],
            "logs": result["output"] if result["success"] else "",
            "error": result["error"],
            "container_id": container_id,
            "lines": lines
        }

    def get_container_stats(self, container_id: str) -> Dict:
        """Получение статистики контейнера"""
        command = f"docker stats {container_id} --no-stream --format json"
        result = self.ssh.execute_command(command)

        if result["success"] and result["output"]:
            try:
                stats_data = json.loads(result["output"])
                return {
                    "success": True,
                    "stats": stats_data
                }
            except json.JSONDecodeError:
                pass

        # Fallback: используем текстовый формат
        command = f"docker stats {container_id} --no-stream"
        result = self.ssh.execute_command(command)

        return {
            "success": result["success"],
            "stats_text": result["output"] if result["success"] else "",
            "error": result["error"]
        }

    def container_action(self, container_id: str, action: str) -> Dict:
        """Выполнение действия с контейнером"""
        valid_actions = ["start", "stop", "restart", "pause", "unpause"]

        if action not in valid_actions:
            return {
                "success": False,
                "error": f"Недопустимое действие: {action}. Допустимые: {', '.join(valid_actions)}"
            }

        command = f"docker {action} {container_id}"
        result = self.ssh.execute_command(command)

        return {
            "success": result["success"],
            "message": f"Команда {action} выполнена" if result["success"] else f"Ошибка выполнения {action}",
            "output": result["output"],
            "error": result["error"]
        }

    def get_system_info(self) -> Dict:
        """Получение информации о Docker системе"""
        commands = {
            "version": "docker version --format json",
            "info": "docker system info --format json",
            "df": "docker system df --format json"
        }

        results = {}
        for key, command in commands.items():
            result = self.ssh.execute_command(command)
            if result["success"] and result["output"]:
                try:
                    results[key] = json.loads(result["output"])
                except json.JSONDecodeError:
                    results[key] = result["output"]
            else:
                results[key] = {"error": result["error"]}

        # Получаем общее количество контейнеров
        containers_all = self.list_containers(all_containers=True)
        containers_running = [c for c in containers_all if c["is_running"]]

        return {
            "containers_total": len(containers_all),
            "containers_running": len(containers_running),
            "containers_stopped": len(containers_all) - len(containers_running),
            "version": results.get("version", {}),
            "system_info": results.get("info", {}),
            "disk_usage": results.get("df", {})
        }

    def get_container_processes(self, container_id: str) -> Dict:
        """Получение процессов внутри контейнера"""
        command = f"docker top {container_id}"
        result = self.ssh.execute_command(command)

        processes = []
        if result["success"] and result["output"]:
            lines = result["output"].split('\n')[1:]  # Пропускаем заголовок
            for line in lines:
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 8:
                        process = {
                            "uid": parts[0],
                            "pid": parts[1],
                            "ppid": parts[2],
                            "c": parts[3],
                            "stime": parts[4],
                            "tty": parts[5],
                            "time": parts[6],
                            "cmd": ' '.join(parts[7:])
                        }
                        processes.append(process)

        return {
            "success": True,
            "processes": processes,
            "count": len(processes)
        }