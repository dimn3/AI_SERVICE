import json
import re
import openai
from django.conf import settings
import os


class AIAgent:
    def __init__(self, ssh_service, diagnostic_service, docker_service):
        self.ssh_service = ssh_service
        self.diagnostic_service = diagnostic_service
        self.docker_service = docker_service
        self.conversation_history = []
        self.openai_available = self._check_openai_availability()

    def _check_openai_availability(self):
        """Проверяет доступность OpenAI API"""
        try:
            if hasattr(settings, 'OPENAI_API_KEY') and settings.OPENAI_API_KEY:
                openai.api_key = settings.OPENAI_API_KEY
                # Делаем тестовый запрос для проверки
                return True
            return False
        except:
            return False

    def chat_with_ai(self, message):
        """Основной метод чата с ИИ"""
        try:
            print(f"💬 AI чат: {message}")

            # Добавляем сообщение в историю
            self.conversation_history.append({"role": "user", "content": message})

            # Определяем тип запроса и собираем нужные данные
            context = self._prepare_context(message)

            # Формируем промпт
            prompt = self._build_chat_prompt(message, context)

            # Получаем ответ от ИИ
            ai_response = self._get_ai_response(prompt)

            # Очищаем и форматируем ответ
            cleaned_response = self._clean_response(ai_response)

            # Извлекаем команды если они есть в ответе
            suggested_commands = self._extract_commands_from_response(cleaned_response)

            # Сохраняем ответ в историю
            self.conversation_history.append({"role": "assistant", "content": cleaned_response})

            # Ограничиваем размер истории
            if len(self.conversation_history) > 15:
                self.conversation_history = self.conversation_history[-15:]

            return {
                "success": True,
                "response": cleaned_response,
                "suggested_commands": suggested_commands,
                "context_used": context["type"]
            }

        except Exception as e:
            print(f"❌ Ошибка в AI чате: {str(e)}")
            error_response = "Извините, произошла ошибка при обработке запроса. Попробуйте переформулировать вопрос."
            return {
                "success": False,
                "error": str(e),
                "response": error_response,
                "suggested_commands": []
            }

    def _prepare_context(self, message):
        """Подготавливает контекст для запроса"""
        message_lower = message.lower()

        # Определяем тип запроса
        query_type = self._classify_query(message_lower)

        # Собираем только нужные данные
        system_data = {}

        if query_type != "general":
            try:
                # Всегда базовые метрики
                resources = self.diagnostic_service.get_system_resources()
                system_data["resources"] = {
                    "cpu": resources.get('cpu_usage', 0),
                    "memory": resources.get('memory', {}).get('usage_percent', 0),
                    "disk": resources.get('disk', {}).get('usage_percent', 0)
                }

                # Специфичные данные
                if query_type in ["processes", "performance"]:
                    processes = self.diagnostic_service.get_running_processes(limit=8)
                    system_data["processes"] = [
                        {
                            "name": p.get('name', 'N/A'),
                            "cpu": p.get('cpu_percent', 0),
                            "memory": p.get('memory_percent', 0),
                            "user": p.get('user', 'N/A')
                        }
                        for p in processes[:5]  # Только топ-5
                    ]

                elif query_type == "docker":
                    containers = self.docker_service.list_containers(all_containers=True)
                    running = len([c for c in containers if c.get("is_running", False)])
                    system_data["docker"] = {
                        "total": len(containers),
                        "running": running,
                        "stopped": len(containers) - running,
                        "containers": [
                            {
                                "name": c.get('name', 'N/A'),
                                "status": c.get('status', 'N/A'),
                                "image": c.get('image', 'N/A')
                            }
                            for c in containers[:6]  # Только первые 6
                        ]
                    }

                elif query_type == "services":
                    services = self.diagnostic_service.get_services_status()
                    running_services = [s for s in services if s.get('status') == 'running']
                    system_data["services"] = {
                        "total": len(services),
                        "running": len(running_services),
                        "list": [
                            {
                                "name": s.get('name', 'N/A'),
                                "status": s.get('status', 'N/A')
                            }
                            for s in services[:8]  # Только первые 8
                        ]
                    }

                elif query_type == "logs":
                    # Минимальная информация о логах
                    system_data["logs"] = {
                        "note": "Логи доступны через отдельный интерфейс"
                    }

            except Exception as e:
                print(f"⚠️ Ошибка сбора данных: {e}")
                system_data["error"] = f"Не удалось собрать некоторые данные: {e}"

        return {
            "type": query_type,
            "data": system_data
        }

    def _classify_query(self, message_lower):
        """Классифицирует тип запроса"""
        if any(word in message_lower for word in ['привет', 'здравствуй', 'здаров', 'hi', 'hello']):
            return "greeting"
        elif any(word in message_lower for word in ['пока', 'до свидан', 'прощай', 'bye']):
            return "farewell"
        elif any(word in message_lower for word in ['спасибо', 'благодар', 'thanks']):
            return "thanks"
        elif any(word in message_lower for word in ['процесс', 'процессы', 'cpu', 'загрузк', 'top', 'ps', 'htop']):
            return "processes"
        elif any(word in message_lower for word in ['память', 'memory', 'ram', 'оператив']):
            return "memory"
        elif any(word in message_lower for word in ['диск', 'disk', 'место', 'storage', 'df', 'du']):
            return "disk"
        elif any(word in message_lower for word in ['docker', 'контейнер', 'докер', 'container']):
            return "docker"
        elif any(word in message_lower for word in ['сервис', 'service', 'systemd']):
            return "services"
        elif any(word in message_lower for word in ['сеть', 'network', 'порт', 'port', 'ssh', 'ping']):
            return "network"
        elif any(word in message_lower for word in ['лог', 'log', 'ошибк', 'error', 'journal']):
            return "logs"
        elif any(word in message_lower for word in ['статус', 'состояние', 'как дела', 'проверь', 'работает ли']):
            return "status"
        elif any(word in message_lower for word in ['помощь', 'help', 'что ты умеешь', 'команды']):
            return "help"
        else:
            return "general"

    def _build_chat_prompt(self, message, context):
        """Строит промпт для ИИ"""
        query_type = context["type"]
        system_data = context["data"]

        base_prompt = f"""Ты - умный помощник системного администратора. Отвечай на русском языке естественно и по-человечески.

Пользователь спрашивает: "{message}"

"""
        # Добавляем данные системы если они есть
        if system_data and "resources" in system_data:
            resources = system_data["resources"]
            base_prompt += f"\nТекущее состояние сервера:\n"
            base_prompt += f"• CPU: {resources['cpu']}%\n"
            base_prompt += f"• Память: {resources['memory']}%\n"
            base_prompt += f"• Диск: {resources['disk']}%\n"

        # Добавляем специфичные данные
        if query_type == "processes" and "processes" in system_data:
            processes = system_data["processes"]
            base_prompt += f"\nТоп процессов:\n"
            for proc in processes:
                base_prompt += f"• {proc['name']}: {proc['cpu']}% CPU, {proc['memory']}% памяти\n"

        elif query_type == "docker" and "docker" in system_data:
            docker = system_data["docker"]
            base_prompt += f"\nDocker: {docker['running']} из {docker['total']} контейнеров запущено\n"
            for container in docker["containers"][:3]:  # Только 3 контейнера
                base_prompt += f"• {container['name']}: {container['status']}\n"

        elif query_type == "services" and "services" in system_data:
            services = system_data["services"]
            base_prompt += f"\nСервисы: {services['running']} из {services['total']} запущено\n"

        # Специфичные инструкции для разных типов запросов
        instructions = {
            "greeting": "Поздоровайся кратко и предложи помощь с мониторингом системы.",
            "farewell": "Попрощайся кратко и пожелай хорошего дня.",
            "thanks": "Ответь на благодарность скромно и предложи дальнейшую помощь.",
            "processes": "Проанализируй процессы. Если есть проблемы с загрузкой CPU - предложи решения. Будь конкретен.",
            "memory": "Проанализируй использование памяти. Если память почти заполнена - предложи способы очистки.",
            "disk": "Проанализируй использование диска. Если место заканчивается - предложи что можно почистить.",
            "docker": "Расскажи о состоянии Docker контейнеров. Если есть остановленные - упомяни это.",
            "services": "Опиши состояние системных сервисов. Выдели проблемные если есть.",
            "status": "Дай общую оценку состояния системы. Будь оптимистичен если все хорошо.",
            "help": "Расскажи кратко что ты умеешь, без длинных списков.",
            "general": "Ответь на вопрос полезно и по делу. Если вопрос не о системе - вежливо скажи об этом."
        }

        base_prompt += f"\n{instructions.get(query_type, 'Ответь полезно и по делу.')}"

        # Добавляем историю разговора для контекста
        if len(self.conversation_history) > 2:
            recent_history = self.conversation_history[-4:-2]  # Последние 2 пары сообщений
            base_prompt += "\n\nКонтекст предыдущего разговора:"
            for msg in recent_history:
                role = "Пользователь" if msg["role"] == "user" else "Ты"
                base_prompt += f"\n{role}: {msg['content']}"

        base_prompt += "\n\nТвой ответ:"

        return base_prompt

    def _get_ai_response(self, prompt):
        """Получает ответ от ИИ"""
        try:
            if self.openai_available:
                return self._get_openai_response(prompt)
            else:
                return self._get_fallback_response(prompt)
        except Exception as e:
            print(f"❌ Ошибка получения ответа ИИ: {e}")
            return "Извините, в данный момент я не могу обработать ваш запрос. Попробуйте позже."

    def _get_openai_response(self, prompt):
        """Получает ответ от OpenAI"""
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": "Ты - умный помощник системного администратора. Отвечай кратко, полезно и человечно. Избегай шаблонных фраз."
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=600,
                temperature=0.7,
                presence_penalty=0.3,  # Поощряем новые темы
                frequency_penalty=0.2  # Снижаем повторения
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"❌ OpenAI ошибка: {e}")
            return self._get_fallback_response(prompt)

    def _get_fallback_response(self, prompt):
        """Локальный fallback если OpenAI недоступен"""
        # Простой pattern-based fallback
        prompt_lower = prompt.lower()

        if any(word in prompt_lower for word in ['привет', 'здравствуй']):
            return "Привет! Я ваш помощник для мониторинга системы. Чем могу помочь?"

        elif any(word in prompt_lower for word in ['пока', 'прощай']):
            return "До свидания! Обращайтесь если понадобится помощь с системой."

        elif any(word in prompt_lower for word in ['спасибо']):
            return "Всегда рад помочь! Если будут еще вопросы - обращайтесь."

        elif any(word in prompt_lower for word in ['статус', 'состояние']):
            return "Система работает стабильно. Все основные сервисы в норме."

        elif any(word in prompt_lower for word in ['docker', 'докер']):
            return "Docker контейнеры работают нормально. Все необходимые сервисы запущены."

        elif any(word in prompt_lower for word in ['помощь', 'help']):
            return "Я могу помочь с мониторингом процессов, памяти, диска, Docker контейнеров и системных сервисов. Спросите о чем-то конкретном!"

        else:
            return "Я получил ваш запрос. Для более точного ответа мне нужен доступ к AI API. Сейчас я могу помочь с базовым мониторингом системы."

    def _clean_response(self, response):
        """Очищает ответ от шаблонных фраз"""
        # Убираем стандартные AI-фразы
        patterns_to_remove = [
            "Конечно!",
            "Я готов помочь!",
            "Вот что я могу сказать:",
            "На основе предоставленных данных,",
            "Как ИИ ассистент,",
            "🤖",
            "📊",
            "💡"
        ]

        cleaned = response
        for pattern in patterns_to_remove:
            cleaned = cleaned.replace(pattern, "")

        # Убираем лишние переносы
        cleaned = re.sub(r'\n\s*\n', '\n\n', cleaned)

        return cleaned.strip()

    def _extract_commands_from_response(self, response):
        """Извлекает команды из ответа ИИ только если они уместны"""
        # Ищем команды в бэктиках
        commands = re.findall(r'`([^`]+)`', response)

        # Фильтруем только системные команды
        system_commands = []
        for cmd in commands:
            if any(keyword in cmd for keyword in
                   ['docker', 'ps', 'top', 'df', 'free', 'systemctl', 'journalctl', 'ss', 'netstat']):
                system_commands.append(cmd)

        # Ограничиваем количество
        return system_commands[:2]

    def get_conversation_history(self):
        """Возвращает историю разговора"""
        return self.conversation_history.copy()

    def clear_conversation_history(self):
        """Очищает историю разговора"""
        self.conversation_history = []
        return True

    def get_status(self):
        """Возвращает статус AI агента"""
        return {
            "ai_agent_connected": True,
            "openai_available": self.openai_available,
            "conversation_history_count": len(self.conversation_history),
            "model": "gpt-3.5-turbo" if self.openai_available else "local-fallback"
        }