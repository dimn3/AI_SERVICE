import json
import os
from typing import Dict, List, Optional
from django.conf import settings
from openai import OpenAI


class AIAgent:
    def __init__(self, ssh_service, diagnostic_service, docker_service):
        self.main_ssh = ssh_service
        self.main_diagnostic = diagnostic_service
        self.main_docker = docker_service

        # Инициализируем OpenAI клиент
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = getattr(settings, 'OPENAI_MODEL', 'gpt-3.5-turbo')

        self.conversation_history = []
        self.system_prompt = self._get_system_prompt()

        print(f"🔧 AI Agent инициализирован с моделью {self.model}")

    def _get_system_prompt(self) -> str:
        """Возвращает системный промпт для AI агента"""
        return """Ты - опытный системный администратор и DevOps инженер. Твоя задача - анализировать состояние серверов, диагностировать проблемы и давать экспертные рекомендации.

Твои обязанности:
1. Анализировать системные метрики, логи и состояние сервисов
2. Выявлять проблемы и потенциальные риски
3. Предлагать конкретные команды для диагностики и решения проблем
4. Объяснять технические концепции понятным языком
5. Предлагать оптимизации для улучшения производительности

Будь точным, профессиональным и полезным. Всегда предлагай конкретные действия и команды."""

    def get_status(self) -> Dict:
        """Получение статуса ИИ агента"""
        return {
            "ai_agent_connected": True,
            "model": self.model,
            "conversation_history_count": len(self.conversation_history),
            "openai_configured": bool(settings.OPENAI_API_KEY)
        }

    def _fallback_analysis(self, message: str) -> Dict:
        """Fallback анализ если LLM недоступна"""
        print("🔄 Использую fallback анализ (LLM недоступна)")

        try:
            # Собираем базовые данные
            system_data = self._collect_relevant_data("diagnostic", message)
            resources = system_data.get("resources", {})

            # Простой анализ на основе данных
            cpu_usage = resources.get('cpu_usage', 0)
            memory_usage = resources.get('memory', {}).get('usage_percent', 0)
            disk_usage = resources.get('disk', {}).get('usage_percent', 0)

            # Анализируем тип запроса для базового ответа
            query_type = self._analyze_query_type(message)

            if query_type == "network":
                response = f"""
    🤖 Базовый анализ сети (LLM недоступна)

    СОСТОЯНИЕ СИСТЕМЫ:
    • CPU: {cpu_usage}%
    • Память: {memory_usage}%
    • Диск: {disk_usage}%

    Для анализа сети используйте:
    - ss -tuln - открытые порты
    - ping google.com - проверка подключения
    - ip addr show - сетевые интерфейсы

    ⚠️ Для детального анализа сети требуется доступ к AI модели.
    """
                commands = ["ss -tuln", "ping -c 3 google.com", "ip addr show"]

            elif query_type == "logs":
                response = f"""
    🤖 Базовый анализ логов (LLM недоступна)

    СОСТОЯНИЕ СИСТЕМЫ:
    • CPU: {cpu_usage}%
    • Память: {memory_usage}%
    • Диск: {disk_usage}%

    Для анализа логов рекомендую выполнить:
    - journalctl -n 50 - для просмотра системных логов
    - tail -100 /var/log/syslog - для просмотра syslog

    ⚠️ Для более детального анализа требуется доступ к AI модели.
    """
                commands = ["journalctl -n 20", "tail -50 /var/log/syslog"]

            # ... остальные типы запросов ...

            else:
                response = f"""
    🤖 Базовый анализ системы (LLM недоступна)

    ТЕКУЩЕЕ СОСТОЯНИЕ:
    • Загрузка CPU: {cpu_usage}%
    • Использование памяти: {memory_usage}%
    • Использование диска: {disk_usage}%

    ОБЩИЕ КОМАНДЫ ДЛЯ ДИАГНОСТИКИ:
    - top -bn1 | head -20
    - free -h
    - df -h  
    - docker ps -a

    ⚠️ AI модель временно недоступна.
    """
                commands = ["top -bn1 | head -20", "free -h", "df -h", "docker ps -a"]

            # ВАЖНО: Всегда возвращаем словарь
            return {
                "success": True,
                "response": response,
                "suggested_commands": commands,
                "query_type": query_type,
                "fallback": True
            }

        except Exception as e:
            # Даже при ошибке возвращаем словарь
            return {
                "success": False,
                "error": f"Ошибка fallback анализа: {str(e)}",
                "response": "❌ Не удалось выполнить анализ. Проверьте подключение к серверу и настройки AI.",
                "suggested_commands": [],
                "query_type": "error"
            }

    def _build_prompt(self, user_message: str, query_type: str, system_data: Dict) -> str:
        """Генерим промпт для AI"""

        # Базовые данные системы
        resources = system_data.get("resources", {})
        cpu = resources.get('cpu_usage', 0)
        memory = resources.get('memory', {}).get('usage_percent', 0)
        disk = resources.get('disk', {}).get('usage_percent', 0)

        prompt = f"""
    Данные сервера:
    - CPU: {cpu}%
    - Память: {memory}%
    - Диск: {disk}%

    Вопрос: {user_message}

    Дай четкий ответ по делу. Если есть проблемы - скажи что делать. В конце предложи 2-3 команды для проверки.
    """
        return prompt

    def _generate_simple_response(self, message: str, query_type: str, system_data: Dict) -> str:
        """Генерим простой ответ без внешних зависимостей"""

        resources = system_data.get("resources", {})
        cpu = resources.get('cpu_usage', 0)
        memory = resources.get('memory', {}).get('usage_percent', 0)
        disk = resources.get('disk', {}).get('usage_percent', 0)

        responses = {
            "network": f"""📡 Анализ сети

    Состояние системы:
    • CPU: {cpu}%
    • Память: {memory}% 
    • Диск: {disk}%

    Команды для проверки сети:
    \`\`\`bash
    ss -tuln
    ping -c 3 google.com
    ip addr show
    \`\`\`

    Что именно не так с сетью?""",

            "logs": f"""📝 Анализ логов

    Состояние системы:
    • CPU: {cpu}%
    • Память: {memory}%
    • Диск: {disk}%

    Команды для проверки логов:
    \`\`\`bash
    journalctl -n 30
    tail -50 /var/log/syslog
    dmesg | tail -20
    \`\`\`

    Какие логи интересуют?""",

            "docker": f"""🐳 Анализ Docker

    Состояние системы:
    • CPU: {cpu}%
    • Память: {memory}%
    • Диск: {disk}%

    Команды для Docker:
    \`\`\`bash
    docker ps -a
    docker stats --no-stream
    docker system df
    \`\`\`

    Какой контейнер проверяем?"""
        }

        return responses.get(query_type, f"""🤖 Анализ системы

    Текущее состояние:
    • CPU: {cpu}%
    • Память: {memory}%
    • Диск: {disk}%

    Команды для диагностики:
    \`\`\`bash
    top -bn1 | head -20
    free -h
    df -h
    docker ps -a
    ss -tuln
    \`\`\`

    Задай конкретный вопрос о системе!""")


    def chat_with_ai(self, message: str) -> Dict:
        """Чат с ИИ агентом через локальную LLM"""
        try:
            # Анализируем тип запроса
            query_type = self._analyze_query_type(message)
            print(f"🔍 Тип запроса: {query_type}")

            # Собираем релевантные данные
            system_data = self._collect_relevant_data(query_type, message)

            # Формируем промпт
            prompt = self._build_prompt(message, query_type, system_data)

            ai_response = self._generate_simple_response(message, query_type, system_data)

            # Извлекаем предложенные команды
            suggested_commands = self._extract_commands_from_response(ai_response)

            # Сохраняем в историю
            self.conversation_history.append({
                "role": "user",
                "content": message
            })
            self.conversation_history.append({
                "role": "assistant",
                "content": ai_response
            })

            # ВАЖНО: Всегда возвращаем словарь
            return {
                "success": True,
                "response": ai_response,
                "suggested_commands": suggested_commands,
                "query_type": query_type
            }

        except Exception as e:
            print(f"❌ Ошибка в chat_with_ai: {e}")
            # Fallback на базовый анализ если LLM недоступна
            return self._fallback_analysis(message)

    def _analyze_query_type(self, message: str) -> str:
        """Анализирует тип запроса пользователя"""
        message_lower = message.lower()

        if any(word in message_lower for word in ['лог', 'ошибк', 'error', 'journal', 'log', 'журнал']):
            return "logs"
        elif any(word in message_lower for word in ['процесс', 'process', 'top', 'памят', 'memory', 'cpu', 'нагруз']):
            return "processes"
        elif any(word in message_lower for word in ['docker', 'контейнер', 'container']):
            return "docker"
        elif any(word in message_lower for word in ['сеть', 'network', 'порт', 'port', 'подключ']):
            return "network"
        elif any(word in message_lower for word in ['диск', 'disk', 'папк', 'folder', 'место', 'пространств']):
            return "disk"
        elif any(word in message_lower for word in ['сервис', 'service', 'systemctl']):
            return "services"
        elif any(word in message_lower for word in ['диагност', 'анализ', 'статус', 'состоян', 'здоров']):
            return "diagnostic"
        else:
            return "general"

    def _collect_relevant_data(self, query_type: str, user_message: str) -> Dict:
        """Собирает релевантные данные в зависимости от типа запроса"""
        data = {}

        try:
            # Всегда собираем базовые ресурсы
            data["resources"] = self.main_diagnostic.get_system_resources()

            if query_type == "logs":
                # Логи ошибок
                logs_result = self.main_ssh.execute_command(
                    "journalctl -p err..alert -n 10 --no-pager 2>/dev/null || echo 'Логи недоступны'")
                data["error_logs"] = logs_result["output"] if logs_result["success"] else "Не удалось получить логи"

            elif query_type == "processes":
                # Процессы по памяти и CPU
                memory_processes = self.main_diagnostic.get_running_processes(limit=10, sort_by='memory')
                cpu_processes = self.main_diagnostic.get_running_processes(limit=10, sort_by='cpu')
                data["memory_processes"] = memory_processes
                data["cpu_processes"] = cpu_processes

            elif query_type == "docker":
                # Docker контейнеры
                containers = self.main_docker.list_containers(all_containers=True)
                data["docker_containers"] = containers

            elif query_type == "network":
                # Сетевая информация
                network_info = self.main_diagnostic.get_network_info()
                data["network"] = network_info

            elif query_type == "disk":
                # Информация о дисках
                disk_result = self.main_ssh.execute_command("df -h 2>/dev/null || echo 'Команда df недоступна'")
                data["disk_info"] = disk_result["output"] if disk_result[
                    "success"] else "Не удалось получить информацию о дисках"

            elif query_type == "services":
                # Статус сервисов
                services = self.main_diagnostic.get_services_status()
                data["services"] = services

        except Exception as e:
            print(f"⚠️ Ошибка сбора данных для {query_type}: {e}")
            data["collection_error"] = str(e)

        return data

    def _build_messages(self, user_message: str, query_type: str, system_data: Dict) -> List[Dict]:
        """Строит сообщения для OpenAI API"""
        # Системный промпт
        messages = [
            {"role": "system", "content": self.system_prompt}
        ]

        # Добавляем контекстные данные
        context_prompt = self._build_context_prompt(query_type, system_data, user_message)
        messages.append({"role": "user", "content": context_prompt})

        return messages

    def _build_context_prompt(self, query_type: str, system_data: Dict, user_message: str) -> str:
        """Строит контекстный промпт с системными данными"""

        prompt = f"""
Пользователь запрашивает: "{user_message}"

Тип запроса: {query_type}

ТЕКУЩЕЕ СОСТОЯНИЕ СИСТЕМЫ:

{self._format_system_data(system_data)}

ПРОАНИЛИЗИРУЙ эти данные и ответь на вопрос пользователя. Будь конкретным и полезным.

В своем ответе:
1. Ответь напрямую на вопрос пользователя
2. Проанализируй предоставленные данные
3. Выяви проблемы если они есть
4. Предложи конкретные действия и команды для решения
5. Объясни сложные моменты простым языком

Ответ должен быть структурированным и полезным для системного администратора.
"""
        return prompt

    def _format_system_data(self, system_data: Dict) -> str:
        """Форматирует системные данные для промпта"""
        formatted = []

        # Базовые ресурсы
        resources = system_data.get("resources", {})
        if resources:
            cpu_usage = resources.get('cpu_usage', 0)
            memory = resources.get('memory', {})
            disk = resources.get('disk', {})

            formatted.append("📊 БАЗОВЫЕ РЕСУРСЫ:")
            formatted.append(f"• CPU: {cpu_usage}%")
            formatted.append(
                f"• Память: {memory.get('usage_percent', 0)}% ({memory.get('used', 'N/A')} / {memory.get('total', 'N/A')})")
            formatted.append(
                f"• Диск: {disk.get('usage_percent', 0)}% ({disk.get('used', 'N/A')} / {disk.get('total', 'N/A')})")
            formatted.append("")

        # Процессы
        if "memory_processes" in system_data or "cpu_processes" in system_data:
            formatted.append("🖥️ ПРОЦЕССЫ:")
            memory_processes = system_data.get("memory_processes", [])
            cpu_processes = system_data.get("cpu_processes", [])

            if memory_processes:
                formatted.append("Топ по памяти:")
                for i, proc in enumerate(memory_processes[:3], 1):
                    name = proc.get('name', 'N/A')
                    memory = proc.get('memory_percent', 0)
                    formatted.append(f"  {i}. {name}: {memory}% памяти")

            if cpu_processes:
                formatted.append("Топ по CPU:")
                for i, proc in enumerate(cpu_processes[:3], 1):
                    name = proc.get('name', 'N/A')
                    cpu = proc.get('cpu_percent', 0)
                    formatted.append(f"  {i}. {name}: {cpu}% CPU")
            formatted.append("")

        # Docker
        if "docker_containers" in system_data:
            containers = system_data.get("docker_containers", [])
            running = len([c for c in containers if c.get("is_running", False)])
            total = len(containers)

            formatted.append("🐳 DOCKER:")
            formatted.append(f"• Контейнеров: {running}/{total} запущено")
            if containers:
                formatted.append("Состояние контейнеров:")
                for container in containers[:5]:
                    name = container.get('name', 'N/A')
                    status = container.get('status', 'N/A')
                    formatted.append(f"  - {name}: {status}")
            formatted.append("")

        # Логи
        if "error_logs" in system_data:
            error_logs = system_data.get("error_logs", "")
            if error_logs and len(error_logs) > 10:
                formatted.append("📝 ПОСЛЕДНИЕ ОШИБКИ В ЛОГАХ:")
                # Берем только первые несколько строк чтобы не перегружать промпт
                lines = error_logs.split('\n')[:5]
                for line in lines:
                    if line.strip():
                        formatted.append(f"  {line}")
                formatted.append("")

        # Сеть
        if "network" in system_data:
            network = system_data.get("network", {})
            formatted.append("🌐 СЕТЬ:")
            formatted.append(f"• Хостнейм: {network.get('hostname', 'N/A')}")
            interfaces = network.get('interfaces', [])
            for iface in interfaces[:2]:
                formatted.append(f"• {iface.get('name', 'N/A')}: {iface.get('ip', 'N/A')}")
            formatted.append("")

        # Сервисы
        if "services" in system_data:
            services = system_data.get("services", [])
            running = len([s for s in services if s.get('status') == 'running'])
            failed = len([s for s in services if s.get('status') == 'failed'])

            formatted.append("⚙️ СЕРВИСЫ:")
            formatted.append(f"• Запущено: {running}, С ошибками: {failed}")
            formatted.append("")

        return "\n".join(formatted)

    def _extract_commands_from_response(self, response: str) -> List[str]:
        """Извлекает команды из ответа AI"""
        commands = []

        # Ищем команды в ответе (обычно они выделены бэктиками или в отдельных строках)
        lines = response.split('\n')
        for line in lines:
            line = line.strip()
            # Ищем команды в бэктиках
            if '`' in line:
                parts = line.split('`')
                for i, part in enumerate(parts):
                    if i % 2 == 1:  # Нечетные части - это код между бэктиками
                        if any(keyword in part.lower() for keyword in
                               ['docker', 'systemctl', 'journalctl', 'ps', 'top', 'df', 'free', 'ss', 'netstat']):
                            commands.append(part)

            # Ищем команды которые начинаются с common prefixes
            if any(line.startswith(prefix) for prefix in
                   ['docker ', 'systemctl ', 'journalctl ', 'ps ', 'top ', 'df ', 'free ', 'ss ', 'netstat ', 'tail ',
                    'grep ']):
                commands.append(line)

        # Убираем дубликаты и ограничиваем количество
        unique_commands = list(dict.fromkeys(commands))[:5]

        # Если не нашли команд в ответе, возвращаем дефолтные
        if not unique_commands:
            unique_commands = [
                "docker ps -a",
                "top -bn1 | head -20",
                "journalctl -n 20",
                "df -h",
                "ss -tuln"
            ]

        return unique_commands

    def analyze_system_state(self, user_query: str = "") -> Dict:
        """Анализ текущего состояния системы с помощью ИИ агента (для обратной совместимости)"""
        try:
            # Просто вызываем chat_with_ai и возвращаем результат
            result = self.chat_with_ai(user_query or "Проанализируй текущее состояние системы")

            # Убедимся что возвращаем правильный формат
            if isinstance(result, dict):
                return result
            else:
                # Если вернулась строка, оборачиваем в словарь
                return {
                    "success": True,
                    "response": str(result),
                    "suggested_commands": [],
                    "query_type": "general"
                }

        except Exception as e:
            print(f"❌ Ошибка в analyze_system_state: {e}")
            return {
                "success": False,
                "error": str(e),
                "response": "Не удалось проанализировать систему",
                "suggested_commands": []
            }

    def get_conversation_history(self) -> List[Dict]:
        """Получение истории разговора"""
        return self.conversation_history

    def clear_conversation_history(self):
        """Очистка истории разговора"""
        self.conversation_history = []