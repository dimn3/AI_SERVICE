import paramiko
import logging
from typing import Dict, Optional
from django.conf import settings

logger = logging.getLogger(__name__)


class SSHService:
    def __init__(self):
        self.ssh_client = None
        self.connected = False

    def connect(self, host: str = None, username: str = None,
                password: str = None, key_file: str = None, port: int = 22) -> bool:
        """Подключение к серверу по SSH"""
        try:
            host = host or settings.SSH_CONFIG['HOST']
            username = username or settings.SSH_CONFIG['USERNAME']
            password = password or settings.SSH_CONFIG['PASSWORD']
            key_file = key_file or settings.SSH_CONFIG['KEY_FILE']
            port = port or settings.SSH_CONFIG['PORT']

            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            if key_file:
                self.ssh_client.connect(host, port=port, username=username, key_filename=key_file)
            else:
                self.ssh_client.connect(host, port=port, username=username, password=password)

            self.connected = True
            logger.info(f"Успешное подключение к {host}")
            return True

        except Exception as e:
            logger.error(f"Ошибка подключения SSH: {e}")
            self.connected = False
            return False

    def execute_command(self, command: str, timeout: int = 30) -> Dict:
        """Выполнение команды на сервере"""
        if not self.connected or not self.ssh_client:
            return {
                "success": False,
                "output": "",
                "error": "SSH подключение не установлено",
                "command": command
            }

        try:
            stdin, stdout, stderr = self.ssh_client.exec_command(command, timeout=timeout)
            exit_code = stdout.channel.recv_exit_status()
            output = stdout.read().decode('utf-8', errors='ignore').strip()
            error = stderr.read().decode('utf-8', errors='ignore').strip()

            return {
                "success": exit_code == 0,
                "output": output,
                "error": error,
                "exit_code": exit_code,
                "command": command
            }

        except Exception as e:
            logger.error(f"Ошибка выполнения команды: {e}")
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "command": command
            }

    def disconnect(self):
        """Отключение от сервера"""
        if self.ssh_client:
            self.ssh_client.close()
            self.connected = False
            logger.info("SSH соединение закрыто")