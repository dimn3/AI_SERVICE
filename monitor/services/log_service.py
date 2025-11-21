import re
from typing import Dict, List, Optional
from .ssh_service import SSHService


class LogService:
    def __init__(self, ssh_service: SSHService):
        self.ssh = ssh_service

    def get_system_logs(self, lines: int = 50, service: str = None) -> Dict:
        """Получение системных логов"""
        try:
            if service:
                # Логи конкретного сервиса через journalctl
                command = f"journalctl -u {service} -n {lines} --no-pager"
                result = self.ssh.execute_command(command)

                if not result["success"]:
                    # Пробуем через файл логов
                    log_files = {
                        'nginx': '/var/log/nginx/error.log',
                        'apache': '/var/log/apache2/error.log',
                        'mysql': '/var/log/mysql/error.log',
                        'postgresql': '/var/log/postgresql/postgresql-*.log',
                    }

                    if service in log_files:
                        command = f"tail -n {lines} {log_files[service]}"
                        result = self.ssh.execute_command(command)
            else:
                # Общие системные логи
                command = f"journalctl -n {lines} --no-pager"
                result = self.ssh.execute_command(command)

            return {
                "success": result["success"],
                "logs": result["output"] if result["success"] else "",
                "error": result["error"],
                "source": "journalctl" if not service else f"service_{service}"
            }

        except Exception as e:
            return {
                "success": False,
                "logs": "",
                "error": str(e),
                "source": "unknown"
            }

    def get_docker_logs(self, container_name: str = None, lines: int = 50) -> Dict:
        """Получение логов Docker контейнеров"""
        try:
            if container_name:
                # Логи конкретного контейнера
                command = f"docker logs {container_name} --tail {lines} 2>/dev/null || echo 'Контейнер не найден'"
            else:
                # Список контейнеров и их статус
                command = "docker ps --format 'table {{.Names}}\\t{{.Status}}'"

            result = self.ssh.execute_command(command)

            return {
                "success": result["success"],
                "logs": result["output"],
                "error": result["error"],
                "container": container_name or "all"
            }

        except Exception as e:
            return {
                "success": False,
                "logs": "",
                "error": str(e),
                "container": container_name or "all"
            }

    def get_auth_logs(self, lines: int = 30) -> Dict:
        """Получение логов авторизации"""
        try:
            # Пробуем разные файлы логов авторизации
            log_files = [
                "/var/log/auth.log",
                "/var/log/secure",
                "/var/log/system.log"
            ]

            for log_file in log_files:
                command = f"tail -n {lines} {log_file} 2>/dev/null || echo 'Файл не найден'"
                result = self.ssh.execute_command(command)

                if result["success"] and "Файл не найден" not in result["output"]:
                    break

            return {
                "success": True,
                "logs": result["output"],
                "error": result["error"],
                "source": log_file
            }

        except Exception as e:
            return {
                "success": False,
                "logs": "",
                "error": str(e),
                "source": "unknown"
            }

    def get_kernel_logs(self, lines: int = 30) -> Dict:
        """Получение логов ядра"""
        try:
            command = f"dmesg | tail -n {lines}"
            result = self.ssh.execute_command(command)

            return {
                "success": result["success"],
                "logs": result["output"],
                "error": result["error"],
                "source": "dmesg"
            }

        except Exception as e:
            return {
                "success": False,
                "logs": "",
                "error": str(e),
                "source": "dmesg"
            }

    def parse_log_entries(self, logs: str, log_type: str = "system") -> List[Dict]:
        """Парсинг логов на структурированные записи"""
        entries = []

        for line in logs.split('\n'):
            if not line.strip():
                continue

            entry = {
                "raw": line,
                "timestamp": self._extract_timestamp(line),
                "level": self._extract_log_level(line, log_type),
                "service": self._extract_service(line, log_type),
                "message": self._extract_message(line, log_type)
            }
            entries.append(entry)

        return entries

    def _extract_timestamp(self, log_line: str) -> str:
        """Извлечение временной метки из лога"""
        # Паттерны для разных форматов логов
        patterns = [
            r'(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})',  # Jan 1 12:00:00
            r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})',  # 2024-01-01T12:00:00
            r'(\d{2}:\d{2}:\d{2})',  # 12:00:00
        ]

        for pattern in patterns:
            match = re.search(pattern, log_line)
            if match:
                return match.group(1)

        return "Unknown"

    def _extract_log_level(self, log_line: str, log_type: str) -> str:
        """Извлечение уровня лога"""
        levels = ["ERROR", "WARN", "WARNING", "INFO", "DEBUG", "CRITICAL", "FATAL"]

        for level in levels:
            if level in log_line.upper():
                return level.lower()

        return "info"

    def _extract_service(self, log_line: str, log_type: str) -> str:
        """Извлечение имени сервиса"""
        if log_type == "docker":
            # В docker логах обычно первое слово - это сервис
            return log_line.split()[0] if log_line.split() else "unknown"

        # Для системных логов ищем common services
        services = ["nginx", "apache", "mysql", "postgres", "ssh", "systemd"]

        for service in services:
            if service in log_line.lower():
                return service

        return "system"

    def _extract_message(self, log_line: str, log_type: str) -> str:
        """Извлечение основного сообщения"""
        # Убираем временную метку и сервис для чистого сообщения
        if log_type == "docker":
            parts = log_line.split()
            return ' '.join(parts[1:]) if len(parts) > 1 else log_line

        # Для системных логов убираем временную метку
        timestamp_patterns = [
            r'^\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+',
            r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\s+',
        ]

        for pattern in timestamp_patterns:
            log_line = re.sub(pattern, '', log_line)

        return log_line.strip()