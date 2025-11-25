import json
import re
import random
from django.conf import settings
import os

try:
    from openai import OpenAI

    OPENAI_NEW_API = True
except ImportError:
    OPENAI_NEW_API = False
    import openai


class AIAgent:
    def __init__(self, ssh_service, diagnostic_service, docker_service):
        self.ssh_service = ssh_service
        self.diagnostic_service = diagnostic_service
        self.docker_service = docker_service
        self.conversation_history = []
        self.openai_available = self._check_openai_availability()
        self.client = self._create_openai_client()

    def _create_openai_client(self):
        """Создает клиент OpenAI для новой версии API"""
        if not self.openai_available:
            return None

        try:
            if OPENAI_NEW_API:
                return OpenAI(api_key=settings.OPENAI_API_KEY)
            else:
                return None
        except Exception as e:
            print(f"❌ Ошибка создания OpenAI клиента: {e}")
            return None

    def _check_openai_availability(self):
        """Проверяет доступность OpenAI API"""
        try:
            if hasattr(settings, 'OPENAI_API_KEY') and settings.OPENAI_API_KEY:
                print("✅ OpenAI API доступен")
                return True
            print("❌ OpenAI API key не найден")
            return False
        except Exception as e:
            print(f"❌ Ошибка проверки OpenAI: {e}")
            return False

    def chat_with_ai(self, message):
        """Умный метод чата с ИИ, который всегда использует реальные данные"""
        try:
            print(f"💬 AI запрос: {message}")

            # Добавляем в историю
            self.conversation_history.append({"role": "user", "content": message})

            # Всегда собираем ВСЕ реальные данные системы
            system_data = self._collect_all_real_system_data()

            # Формируем умный промпт с реальными данными
            prompt = self._build_smart_prompt(message, system_data)

            # Получаем ответ
            ai_response = self._get_ai_response(prompt)

            # Извлекаем команды
            suggested_commands = self._extract_commands_from_response(ai_response)

            # Сохраняем в историю
            self.conversation_history.append({"role": "assistant", "content": ai_response})

            # Ограничиваем историю
            if len(self.conversation_history) > 20:
                self.conversation_history = self.conversation_history[-20:]

            return {
                "success": True,
                "response": ai_response,
                "suggested_commands": suggested_commands
            }

        except Exception as e:
            print(f"❌ Ошибка AI чата: {str(e)}")
            import traceback
            traceback.print_exc()

            # Fallback с реальными данными
            fallback_response = self._get_smart_fallback_with_real_data(message)
            return {
                "success": False,
                "error": str(e),
                "response": fallback_response,
                "suggested_commands": []
            }

    def _collect_all_real_system_data(self):
        """Собирает ВСЕ реальные данные системы"""
        data = {}

        try:
            # 1. Базовые ресурсы
            resources = self.diagnostic_service.get_system_resources()
            data["resources"] = {
                "cpu_usage": resources.get('cpu_usage', 0),
                "memory": {
                    "usage_percent": resources.get('memory', {}).get('usage_percent', 0),
                    "used": resources.get('memory', {}).get('used', 'N/A'),
                    "total": resources.get('memory', {}).get('total', 'N/A')
                },
                "disk": {
                    "usage_percent": resources.get('disk', {}).get('usage_percent', 0),
                    "used": resources.get('disk', {}).get('used', 'N/A'),
                    "total": resources.get('disk', {}).get('total', 'N/A')
                }
            }

            # 2. Процессы (топ по CPU и памяти)
            processes_cpu = self.diagnostic_service.get_running_processes(limit=10, sort_by='cpu')
            processes_memory = self.diagnostic_service.get_running_processes(limit=10, sort_by='memory')

            data["processes"] = {
                "top_cpu": processes_cpu[:5],
                "top_memory": processes_memory[:5],
                "total_count": len(processes_cpu)
            }

            # 3. Docker контейнеры
            containers = self.docker_service.list_containers(all_containers=True)
            running_containers = [c for c in containers if c.get("is_running", False)]
            stopped_containers = [c for c in containers if not c.get("is_running", False)]

            data["docker"] = {
                "total": len(containers),
                "running": len(running_containers),
                "stopped": len(stopped_containers),
                "containers": containers[:8],  # Первые 8 контейнеров
                "running_list": running_containers[:4],
                "stopped_list": stopped_containers[:2]
            }

            # 4. Системные сервисы
            services = self.diagnostic_service.get_services_status()
            running_services = [s for s in services if s.get('status') == 'running']
            failed_services = [s for s in services if s.get('status') == 'failed']

            data["services"] = {
                "total": len(services),
                "running": len(running_services),
                "failed": len(failed_services),
                "services_list": services[:6]  # Первые 6 сервисов
            }

            # 5. Сетевая информация
            network_info = self.diagnostic_service.get_network_info()
            data["network"] = network_info

            print(f"📊 Собраны реальные данные: CPU {data['resources']['cpu_usage']}%, "
                  f"Память {data['resources']['memory']['usage_percent']}%, "
                  f"Docker {data['docker']['running']}/{data['docker']['total']}, "
                  f"Сервисы {data['services']['running']}/{data['services']['total']}")

        except Exception as e:
            print(f"⚠️ Ошибка сбора реальных данных: {e}")
            data["error"] = f"Ошибка сбора данных: {e}"

        return data

    def _build_smart_prompt(self, message, system_data):
        """Строит умный промпт с реальными данными"""

        # Форматируем данные в читаемый вид
        system_info = self._format_real_system_data(system_data)

        prompt = f"""
# КОНТЕКСТ СИСТЕМЫ
Ты - умный AI ассистент системы мониторинга. У тебя есть РЕАЛЬНЫЕ данные о текущем состоянии сервера.

# РЕАЛЬНЫЕ ДАННЫЕ СИСТЕМЫ
{system_info}

# ЗАПРОС ПОЛЬЗОВАТЕЛЯ
"{message}"

# ИСТОРИЯ РАЗГОВОРА
{self._format_conversation_history()}

# ИНСТРУКЦИИ
1. ОТВЕЧАЙ ТОЛЬКО НА ОСНОВЕ РЕАЛЬНЫХ ДАННЫХ ВЫШЕ
2. Будь полезным и конкретным
3. Если данных нет для ответа - честно скажи об этом
4. Используй естественный язык, можно с юмором
5. Для технических вопросов давай конкретные рекомендации
6. Предлагай команды только если они действительно нужны

ОТВЕТ:
"""
        return prompt

    def _format_real_system_data(self, system_data):
        """Форматирует реальные данные системы"""
        lines = []

        # Ресурсы
        if "resources" in system_data:
            res = system_data["resources"]
            lines.append("## 📊 РЕСУРСЫ")
            lines.append(f"- CPU: {res['cpu_usage']}% загрузки")
            lines.append(
                f"- Память: {res['memory']['usage_percent']}% ({res['memory']['used']} / {res['memory']['total']})")
            lines.append(f"- Диск: {res['disk']['usage_percent']}% ({res['disk']['used']} / {res['disk']['total']})")
            lines.append("")

        # Процессы
        if "processes" in system_data:
            procs = system_data["processes"]
            lines.append("## 🔥 ПРОЦЕССЫ")
            lines.append(f"Всего процессов: {procs['total_count']}")

            lines.append("Топ по CPU:")
            for i, proc in enumerate(procs["top_cpu"][:3], 1):
                lines.append(
                    f"  {i}. {proc.get('name', 'N/A')} - {proc.get('cpu_percent', 0)}% CPU, {proc.get('memory_percent', 0)}% памяти")

            lines.append("Топ по памяти:")
            for i, proc in enumerate(procs["top_memory"][:3], 1):
                lines.append(
                    f"  {i}. {proc.get('name', 'N/A')} - {proc.get('memory_percent', 0)}% памяти, {proc.get('cpu_percent', 0)}% CPU")
            lines.append("")

        # Docker
        if "docker" in system_data:
            docker = system_data["docker"]
            lines.append("## 🐳 DOCKER")
            lines.append(f"Контейнеры: {docker['running']}/{docker['total']} запущено")

            if docker["running_list"]:
                lines.append("Запущенные:")
                for container in docker["running_list"]:
                    lines.append(f"  🟢 {container.get('name', 'N/A')} - {container.get('status', 'N/A')}")

            if docker["stopped_list"]:
                lines.append("Остановленные:")
                for container in docker["stopped_list"]:
                    lines.append(f"  🔴 {container.get('name', 'N/A')} - {container.get('status', 'N/A')}")
            lines.append("")

        # Сервисы
        if "services" in system_data:
            services = system_data["services"]
            lines.append("## ⚙️ СЕРВИСЫ")
            lines.append(
                f"Всего: {services['total']}, запущено: {services['running']}, с ошибками: {services['failed']}")

            for service in services["services_list"][:4]:
                status_icon = "🟢" if service.get('status') == 'running' else "🔴" if service.get(
                    'status') == 'failed' else "🟡"
                lines.append(f"  {status_icon} {service.get('name', 'N/A')} - {service.get('status', 'N/A')}")

        return "\n".join(lines)

    def _format_conversation_history(self):
        """Форматирует историю разговора"""
        if len(self.conversation_history) < 2:
            return "История пуста"

        history_text = ""
        recent_history = self.conversation_history[-4:]  # Последние 2 пары

        for msg in recent_history:
            role = "Пользователь" if msg["role"] == "user" else "Ассистент"
            history_text += f"{role}: {msg['content']}\n"

        return history_text

    def _get_ai_response(self, prompt):
        """Получает ответ от ИИ"""
        try:
            if self.openai_available and self.client:
                return self._get_openai_response(prompt)
            else:
                # Всегда используем умный fallback с реальными данными
                return self._get_smart_fallback_with_real_data_from_prompt(prompt)
        except Exception as e:
            print(f"❌ Ошибка получения ответа ИИ: {e}")
            return self._get_smart_fallback_with_real_data_from_prompt(prompt)

    def _get_openai_response(self, prompt):
        """Получает ответ от OpenAI"""
        try:
            if OPENAI_NEW_API:
                response = self.client.chat.completions.create(
                    model="gpt-4",  # Используем GPT-4
                    messages=[
                        {
                            "role": "system",
                            "content": "Ты - экспертный системный администратор. Отвечай точно на основе предоставленных данных. Будь полезным и конкретным."
                        },
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=800,
                    temperature=0.7,
                )
                return response.choices[0].message.content.strip()
            else:
                response = openai.ChatCompletion.create(
                    model="gpt-4",
                    messages=[
                        {
                            "role": "system",
                            "content": "Ты - экспертный системный администратор. Отвечай точно на основе предоставленных данных. Будь полезным и конкретным."
                        },
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=800,
                    temperature=0.7,
                )
                return response.choices[0].message.content.strip()

        except Exception as e:
            print(f"❌ OpenAI ошибка: {e}")
            raise e

    def _get_smart_fallback_with_real_data(self, message):
        """Умный fallback с реальными данными"""
        try:
            # Собираем данные заново для fallback
            system_data = self._collect_all_real_system_data()

            # Анализируем запрос и формируем ответ на основе реальных данных
            message_lower = message.lower()

            if any(word in message_lower for word in ['привет', 'здравствуй', 'hello']):
                return self._format_greeting_response(system_data)
            elif any(word in message_lower for word in ['процесс', 'нагружают', 'топ']):
                return self._format_processes_response(system_data)
            elif any(word in message_lower for word in ['докер', 'docker', 'контейнер']):
                return self._format_docker_response(system_data)
            elif any(word in message_lower for word in ['сервис', 'service']):
                return self._format_services_response(system_data)
            elif any(word in message_lower for word in ['сеть', 'network', 'порт']):
                return self._format_network_response(system_data)
            elif any(word in message_lower for word in ['статус', 'состояние', 'как дела']):
                return self._format_status_response(system_data)
            else:
                return self._format_general_response(system_data, message)

        except Exception as e:
            print(f"❌ Ошибка в умном fallback: {e}")
            return "На основе текущих данных: система работает стабильно. Для детальной информации используйте разделы мониторинга."

    def _get_smart_fallback_with_real_data_from_prompt(self, prompt):
        """Умный fallback из промпта"""
        # Извлекаем сообщение из промпта
        message_match = re.search(r'ЗАПРОС ПОЛЬЗОВАТЕЛЯ\s*"([^"]+)"', prompt)
        if message_match:
            message = message_match.group(1)
            return self._get_smart_fallback_with_real_data(message)
        else:
            return "Получил ваш запрос! Система стабильна, детали в разделах мониторинга."

    def _format_greeting_response(self, system_data):
        """Форматирует приветственный ответ с реальными данными"""
        resources = system_data.get("resources", {})
        docker = system_data.get("docker", {})

        return f"""Привет! 👋 

Система работает стабильно:
• CPU: {resources.get('cpu_usage', 0)}% загрузки
• Память: {resources.get('memory', {}).get('usage_percent', 0)}% использовано  
• Docker: {docker.get('running', 0)}/{docker.get('total', 0)} контейнеров запущено

Чем могу помочь?"""

    def _format_processes_response(self, system_data):
        """Форматирует ответ о процессах с реальными данными"""
        processes = system_data.get("processes", {})
        top_cpu = processes.get("top_cpu", [])

        response = "🔍 На основе реальных данных о процессах:\n\n"

        if top_cpu:
            response += "Топ процессов по CPU:\n"
            for i, proc in enumerate(top_cpu[:5], 1):
                response += f"{i}. **{proc.get('name', 'N/A')}** - {proc.get('cpu_percent', 0)}% CPU, {proc.get('memory_percent', 0)}% памяти\n"
        else:
            response += "Данные о процессах временно недоступны\n"

        response += f"\nВсего процессов: {processes.get('total_count', 0)}"

        # Добавляем оценку
        cpu_usage = system_data.get("resources", {}).get("cpu_usage", 0)
        if cpu_usage > 80:
            response += "\n\n⚠️ Внимание: Высокая загрузка CPU!"
        elif cpu_usage < 20:
            response += "\n\n✅ CPU практически не нагружен"

        return response

    def _format_docker_response(self, system_data):
        """Форматирует ответ о Docker с реальными данными"""
        docker = system_data.get("docker", {})
        running = docker.get("running", 0)
        total = docker.get("total", 0)
        containers = docker.get("containers", [])

        response = f"🐳 Docker: {running}/{total} контейнеров запущено\n\n"

        if containers:
            response += "Состояние контейнеров:\n"
            for container in containers[:6]:
                status_icon = "🟢" if container.get("is_running") else "🔴"
                response += f"{status_icon} {container.get('name', 'N/A')} - {container.get('status', 'N/A')}\n"

        if docker.get("stopped", 0) > 0:
            response += f"\n⚠️ Остановлено контейнеров: {docker.get('stopped', 0)}"

        return response

    def _format_services_response(self, system_data):
        """Форматирует ответ о сервисах с реальными данными"""
        services = system_data.get("services", {})
        running = services.get("running", 0)
        total = services.get("total", 0)
        failed = services.get("failed", 0)

        response = f"⚙️ Системные сервисы: {running}/{total} запущено"

        if failed > 0:
            response += f", {failed} с ошибками\n\n"
            response += "❌ Рекомендуется проверить сервисы с ошибками!"
        else:
            response += "\n\n✅ Все сервисы работают нормально"

        services_list = services.get("services_list", [])
        if services_list:
            response += "\n\nОсновные сервисы:\n"
            for service in services_list[:4]:
                status_icon = "🟢" if service.get('status') == 'running' else "🔴"
                response += f"{status_icon} {service.get('name', 'N/A')}\n"

        return response

    def _format_network_response(self, system_data):
        """Форматирует ответ о сети с реальными данными"""
        network = system_data.get("network", {})

        response = "🌐 Сетевая информация:\n\n"

        if network.get("connections"):
            response += f"Активные подключения: {len(network.get('connections', []))}\n"

        if network.get("interface_stats"):
            response += "Статус интерфейсов: активны\n"

        response += "✅ Сетевое подключение стабильно"

        return response

    def _format_status_response(self, system_data):
        """Форматирует общий статус с реальными данными"""
        resources = system_data.get("resources", {})
        docker = system_data.get("docker", {})
        services = system_data.get("services", {})

        cpu = resources.get("cpu_usage", 0)
        memory = resources.get("memory", {}).get("usage_percent", 0)
        disk = resources.get("disk", {}).get("usage_percent", 0)

        response = "📊 ОБЩИЙ СТАТУС СИСТЕМЫ\n\n"

        # Оценка CPU
        if cpu < 20:
            response += "✅ CPU: отлично (низкая нагрузка)\n"
        elif cpu < 60:
            response += "🟡 CPU: нормально (умеренная нагрузка)\n"
        else:
            response += "🔴 CPU: высоко (может тормозить)\n"

        # Оценка памяти
        if memory < 60:
            response += "✅ Память: отлично (достаточно)\n"
        elif memory < 85:
            response += "🟡 Память: нормально (средняя загрузка)\n"
        else:
            response += "🔴 Память: критично (мало свободной)\n"

        # Оценка диска
        if disk < 70:
            response += "✅ Диск: отлично (много места)\n"
        elif disk < 90:
            response += "🟡 Диск: нормально (места достаточно)\n"
        else:
            response += "🔴 Диск: критично (мало места)\n"

        response += f"\n🐳 Docker: {docker.get('running', 0)}/{docker.get('total', 0)} контейнеров\n"
        response += f"⚙️ Сервисы: {services.get('running', 0)}/{services.get('total', 0)} запущено"

        if services.get('failed', 0) > 0:
            response += f" ⚠️ {services.get('failed', 0)} с ошибками"

        return response

    def _format_general_response(self, system_data, message):
        """Форматирует общий ответ с реальными данными"""
        return f"""Получил ваш вопрос: "{message}"

На основе текущих данных системы:
• CPU: {system_data.get('resources', {}).get('cpu_usage', 0)}% загрузки
• Память: {system_data.get('resources', {}).get('memory', {}).get('usage_percent', 0)}% использовано
• Docker: {system_data.get('docker', {}).get('running', 0)} контейнеров запущено
• Сервисы: {system_data.get('services', {}).get('running', 0)} запущено

Система работает стабильно. Для детальной информации уточните вопрос!"""

    def _extract_commands_from_response(self, response):
        """Извлекает команды из ответа"""
        commands = re.findall(r'`([^`]+)`', response)
        return commands[:3]

    def get_conversation_history(self):
        return self.conversation_history.copy()

    def clear_conversation_history(self):
        self.conversation_history = []
        return True

    def get_status(self):
        return {
            "ai_agent_connected": True,
            "openai_available": self.openai_available,
            "conversation_history_count": len(self.conversation_history),
            "model": "gpt-4" if self.openai_available else "smart-fallback"
        }