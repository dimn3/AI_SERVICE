from django.shortcuts import render, redirect
from django.utils.html import escape
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import json
from django.http import JsonResponse

from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings

from .services.ssh_service import SSHService
from .services.log_service import LogService
from .services.diagnostic_service import DiagnosticService
from .services.docker_service import DockerService
from .services.ai_agent import AIAgent

ssh_service = SSHService()
log_service = LogService(ssh_service)
diagnostic_service = DiagnosticService(ssh_service)
docker_service = DockerService(ssh_service)
ai_agent = AIAgent(ssh_service, diagnostic_service, docker_service)


def initialize_services():
    """Автоматическая инициализация сервисов при запуске"""
    try:
        from django.conf import settings

        # Пробуем автоматически подключиться к SSH
        ssh_config = settings.SSH_CONFIG
        print(f"🔄 Автоподключение к {ssh_config['HOST']}...")

        success = ssh_service.connect(
            host=ssh_config['HOST'],
            username=ssh_config['USERNAME'],
            password=ssh_config['PASSWORD'],
            key_file=ssh_config.get('KEY_FILE'),
            port=ssh_config['PORT']
        )

        if success:
            print("✅ Автоподключение успешно")
        else:
            print("❌ Автоподключение не удалось")

    except Exception as e:
        print(f"⚠️ Ошибка автоподключения: {e}")


# Вызываем при импорте
initialize_services()



@api_view(['POST'])
def connect_server(request):
    """Подключение к серверу с настройками из settings.py"""
    try:
        # Используем настройки из settings.py, но позволяем переопределить через API
        ssh_config = settings.SSH_CONFIG.copy()

        # Если в запросе есть данные - переопределяем настройки
        if 'host' in request.data:
            ssh_config['HOST'] = request.data.get('host', ssh_config['HOST'])
        if 'username' in request.data:
            ssh_config['USERNAME'] = request.data.get('username', ssh_config['USERNAME'])
        if 'password' in request.data:
            ssh_config['PASSWORD'] = request.data.get('password', ssh_config['PASSWORD'])
        if 'key_file' in request.data:
            ssh_config['KEY_FILE'] = request.data.get('key_file', ssh_config['KEY_FILE'])
        if 'port' in request.data:
            ssh_config['PORT'] = request.data.get('port', ssh_config['PORT'])

        # Подключаемся с финальными настройками
        success = ssh_service.connect(
            host=ssh_config['HOST'],
            username=ssh_config['USERNAME'],
            password=ssh_config['PASSWORD'],
            key_file=ssh_config['KEY_FILE'],
            port=ssh_config['PORT']
        )

        if success:
            return Response({
                "status": "connected",
                "message": f"Успешное подключение к серверу {ssh_config['HOST']}",
                "server": ssh_config['HOST']
            })
        else:
            return Response({
                "status": "error",
                "message": f"Не удалось подключиться к серверу {ssh_config['HOST']}"
            }, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        return Response({
            "status": "error",
            "message": f"Ошибка подключения: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def connect_server_simple(request):
    """Простое подключение с настройками из settings.py (без параметров)"""
    try:
        # Используем ТОЛЬКО настройки из settings.py
        ssh_config = settings.SSH_CONFIG

        success = ssh_service.connect(
            host=ssh_config['HOST'],
            username=ssh_config['USERNAME'],
            password=ssh_config['PASSWORD'],
            key_file=ssh_config['KEY_FILE'],
            port=ssh_config['PORT']
        )

        if success:
            return Response({
                "status": "connected",
                "message": f"Успешное подключение к {ssh_config['HOST']}",
                "server": ssh_config['HOST'],
                "user": ssh_config['USERNAME']
            })
        else:
            return Response({
                "status": "error",
                "message": f"Не удалось подключиться к {ssh_config['HOST']}. Проверь настройки в .env файле."
            }, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        return Response({
            "status": "error",
            "message": f"Ошибка подключения: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
def disconnect_server(request):
    """Отключение от сервера"""
    try:
        ssh_service.disconnect()
        return Response({
            "status": "disconnected",
            "message": "Отключение от сервера выполнено"
        })
    except Exception as e:
        return Response({
            "status": "error",
            "message": f"Ошибка отключения: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@csrf_exempt
def get_system_logs(request):
    """Получение системных логов с авто-подключением"""
    try:
        print("📨 Запрос на получение логов")

        # Если SSH не подключен - пробуем подключиться автоматически
        if not hasattr(ssh_service, 'connected') or not ssh_service.connected:
            print("🔄 SSH не подключен, пробуем авто-подключение...")

            from django.conf import settings
            ssh_config = settings.SSH_CONFIG

            success = ssh_service.connect(
                host=ssh_config['HOST'],
                username=ssh_config['USERNAME'],
                password=ssh_config['PASSWORD'],
                key_file=ssh_config.get('KEY_FILE'),
                port=ssh_config['PORT']
            )

            if not success:
                return Response({
                    "success": False,
                    "error": "Не удалось автоматически подключиться к серверу. Подключитесь вручную."
                }, status=400)

        # Остальной код без изменений...
        lines_str = request.GET.get('lines', '50')
        try:
            lines = int(lines_str)
        except:
            lines = 50

        lines = min(lines, 100)

        service = request.GET.get('service', '')
        print(f"🔧 Получаем логи: lines={lines}, service={service}")

        if service:
            cmd = f"journalctl -u {service} -n {lines} --no-pager 2>/dev/null || echo 'Сервис {service} не найден'"
        else:
            cmd = f"tail -{lines} /var/log/syslog 2>/dev/null || echo 'Файл логов недоступен'"

        print(f"🔧 Выполняем команду: {cmd}")

        result = ssh_service.execute_command(cmd)
        print(f"🔧 Результат: success={result['success']}")

        if result["success"]:
            return Response({
                "success": True,
                "logs": result["output"],
                "lines": lines,
                "source": service if service else "system"
            })
        else:
            return Response({
                "success": False,
                "error": result.get("error", "Неизвестная ошибка SSH")
            }, status=500)

    except Exception as e:
        print(f"❌ Ошибка в get_system_logs: {str(e)}")
        import traceback
        traceback.print_exc()

        return Response({
            "success": False,
            "error": f"Внутренняя ошибка: {str(e)}"
        }, status=500)


@api_view(['GET'])
def get_docker_logs(request):
    """Получение Docker логов - исправленная версия"""
    try:
        lines = int(request.GET.get('lines', 50))
        container_name = request.GET.get('container', '')

        print(f"🔧 Получение Docker логов: lines={lines}, container='{container_name}'")

        if container_name:
            # Логи конкретного контейнера
            cmd = f"docker logs {container_name} --tail {lines} 2>&1"
        else:
            # Общие Docker логи - пробуем несколько источников
            commands = [
                f"journalctl -u docker -n {lines} --no-pager 2>&1",
                f"sudo journalctl -u docker.service -n {lines} --no-pager 2>&1",
                f"tail -n {lines} /var/log/docker.log 2>&1",
                "docker system info 2>&1"  # Fallback команда
            ]

            # Используем первую успешную команду
            cmd = commands[0]
            for test_cmd in commands:
                test_result = ssh_service.execute_command(test_cmd)
                if test_result["success"] and test_result["output"].strip():
                    if "No entries" not in test_result["output"] and "не видите сообщения" not in test_result["output"]:
                        cmd = test_cmd
                        break

        result = ssh_service.execute_command(cmd)

        if result["success"]:
            logs_output = result["output"].strip()

            # Если команда требует аргумент (ошибка docker logs без контейнера)
            if "requires 1 argument" in logs_output:
                # Получаем список контейнеров как fallback
                containers_cmd = "docker ps -a --format '🚀 {{.Names}} | 📊 {{.Status}} | 🏷️ {{.Image}}' | head -10"
                containers_result = ssh_service.execute_command(containers_cmd)
                if containers_result["success"]:
                    logs_output = "ℹ️  Выберите конкретный контейнер для просмотра логов\n\n" \
                                  "🐳 Доступные контейнеры:\n\n" + containers_result["output"]
                else:
                    logs_output = "📝 Для просмотра логов Docker выберите конкретный контейнер из списка выше"

            # Если логи пустые или содержат сообщение о правах
            elif not logs_output or "No entries" in logs_output or "не видите сообщения" in logs_output:
                containers_cmd = "docker ps -a --format 'table {{.Names}}\\t{{.Status}}' | head -10"
                containers_result = ssh_service.execute_command(containers_cmd)
                if containers_result["success"]:
                    logs_output = "📝 Docker логи демона недоступны или пусты\n\n" \
                                  "🐳 Текущие контейнеры:\n\n" + containers_result["output"]

            return Response({
                "success": True,
                "logs": logs_output,
                "lines": lines,
                "container": container_name if container_name else "docker"
            })
        else:
            return Response({
                "success": False,
                "error": result.get("error", "Неизвестная ошибка SSH")
            })

    except Exception as e:
        print(f"❌ Ошибка в get_docker_logs: {str(e)}")
        return Response({
            "success": False,
            "error": f"Ошибка получения Docker логов: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_auth_logs(request):
    """Получение логов авторизации"""
    try:
        lines = int(request.GET.get('lines', 30))

        result = log_service.get_auth_logs(lines=lines)

        if result["success"]:
            parsed_logs = log_service.parse_log_entries(result["logs"], "auth")

            return Response({
                "success": True,
                "logs": parsed_logs,
                "source": result["source"],
                "total_entries": len(parsed_logs)
            })
        else:
            return Response({
                "success": False,
                "error": result["error"]
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    except Exception as e:
        return Response({
            "success": False,
            "error": f"Ошибка получения логов авторизации: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_kernel_logs(request):
    """Получение логов ядра"""
    try:
        lines = int(request.GET.get('lines', 30))

        result = log_service.get_kernel_logs(lines=lines)

        if result["success"]:
            parsed_logs = log_service.parse_log_entries(result["logs"], "kernel")

            return Response({
                "success": True,
                "logs": parsed_logs,
                "source": result["source"],
                "total_entries": len(parsed_logs)
            })
        else:
            return Response({
                "success": False,
                "error": result["error"]
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    except Exception as e:
        return Response({
            "success": False,
            "error": f"Ошибка получения логов ядра: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def server_status(request):
    """Проверка статуса подключения"""
    return Response({
        "connected": ssh_service.connected,
        "status": "connected" if ssh_service.connected else "disconnected"
    })


@api_view(['GET'])
def system_resources(request):
    """Получение информации о системных ресурсах"""
    try:
        if not ssh_service.connected:
            return Response({
                "success": False,
                "error": "Сервер не подключен"
            }, status=status.HTTP_400_BAD_REQUEST)

        resources = diagnostic_service.get_system_resources()
        return Response({
            "success": True,
            "resources": resources
        })

    except Exception as e:
        return Response({
            "success": False,
            "error": f"Ошибка получения ресурсов: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def running_processes(request):
    """Получение списка запущенных процессов"""
    try:
        if not ssh_service.connected:
            return Response({
                "success": False,
                "error": "Сервер не подключен"
            }, status=status.HTTP_400_BAD_REQUEST)

        limit = int(request.GET.get('limit', 10))
        sort_by = request.GET.get('sort_by', 'cpu')  # cpu или memory

        processes = diagnostic_service.get_running_processes(limit=limit, sort_by=sort_by)
        return Response({
            "success": True,
            "processes": processes,
            "total": len(processes)
        })

    except Exception as e:
        return Response({
            "success": False,
            "error": f"Ошибка получения процессов: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def services_status(request):
    """Получение статуса системных сервисов"""
    try:
        if not ssh_service.connected:
            return Response({
                "success": False,
                "error": "Сервер не подключен"
            }, status=status.HTTP_400_BAD_REQUEST)

        services = diagnostic_service.get_services_status()
        return Response({
            "success": True,
            "services": services,
            "total": len(services)
        })

    except Exception as e:
        return Response({
            "success": False,
            "error": f"Ошибка получения сервисов: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def quick_diagnostic(request):
    """Полная быстрая диагностика системы"""
    try:
        if not ssh_service.connected:
            return Response({
                "success": False,
                "error": "Сервер не подключен"
            }, status=status.HTTP_400_BAD_REQUEST)

        diagnostic = diagnostic_service.quick_diagnostic()
        return Response(diagnostic)

    except Exception as e:
        return Response({
            "success": False,
            "error": f"Ошибка диагностики: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def network_info(request):
    """Получение сетевой информации"""
    try:
        if not ssh_service.connected:
            return Response({
                "success": False,
                "error": "Сервер не подключен"
            }, status=status.HTTP_400_BAD_REQUEST)

        network_info = diagnostic_service.get_network_info()
        return Response({
            "success": True,
            "network": network_info
        })

    except Exception as e:
        return Response({
            "success": False,
            "error": f"Ошибка получения сетевой информации: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def docker_containers(request):
    """Получение списка Docker контейнеров"""
    try:
        if not ssh_service.connected:
            return Response({
                "success": False,
                "error": "Сервер не подключен"
            }, status=status.HTTP_400_BAD_REQUEST)

        all_containers = request.GET.get('all', 'false').lower() == 'true'
        containers = docker_service.list_containers(all_containers=all_containers)

        # ПРАВИЛЬНЫЙ подсчет
        running_containers = [c for c in containers if c.get("is_running", False)]
        stopped_containers = [c for c in containers if not c.get("is_running", False)]

        print(f"🔧 API Docker: всего={len(containers)}, запущено={len(running_containers)}, остановлено={len(stopped_containers)}")

        return Response({
            "success": True,
            "containers": containers,
            "total": len(containers),
            "running": len(running_containers),
            "stopped": len(stopped_containers)  # Явно возвращаем количество остановленных
        })

    except Exception as e:
        print(f"❌ Ошибка получения контейнеров: {str(e)}")
        return Response({
            "success": False,
            "error": f"Ошибка получения контейнеров: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def docker_container_info(request, container_id):
    """Получение информации о конкретном контейнере"""
    try:
        if not ssh_service.connected:
            return Response({
                "success": False,
                "error": "Сервер не подключен"
            }, status=status.HTTP_400_BAD_REQUEST)

        container_info = docker_service.get_container_info(container_id)

        if "error" in container_info:
            return Response({
                "success": False,
                "error": container_info["error"]
            }, status=status.HTTP_404_NOT_FOUND)

        return Response({
            "success": True,
            "container": container_info
        })

    except Exception as e:
        return Response({
            "success": False,
            "error": f"Ошибка получения информации о контейнере: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def docker_container_logs(request, container_id):
    """Получение логов контейнера"""
    try:
        if not ssh_service.connected:
            return Response({
                "success": False,
                "error": "Сервер не подключен"
            }, status=status.HTTP_400_BAD_REQUEST)

        lines = int(request.GET.get('lines', 50))

        logs_result = docker_service.get_container_logs(container_id, lines=lines)

        if logs_result["success"]:
            return Response({
                "success": True,
                "logs": logs_result["logs"],
                "container_id": container_id,
                "lines": lines
            })
        else:
            return Response({
                "success": False,
                "error": logs_result["error"]
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    except Exception as e:
        return Response({
            "success": False,
            "error": f"Ошибка получения логов: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def docker_container_stats(request, container_id):
    """Получение статистики контейнера"""
    try:
        if not ssh_service.connected:
            return Response({
                "success": False,
                "error": "Сервер не подключен"
            }, status=status.HTTP_400_BAD_REQUEST)

        stats_result = docker_service.get_container_stats(container_id)

        return Response(stats_result)

    except Exception as e:
        return Response({
            "success": False,
            "error": f"Ошибка получения статистики: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def docker_container_action(request, container_id, action):
    """Выполнение действия с контейнером"""
    try:
        if not ssh_service.connected:
            return Response({
                "success": False,
                "error": "Сервер не подключен"
            }, status=status.HTTP_400_BAD_REQUEST)

        result = docker_service.container_action(container_id, action)

        return Response(result)

    except Exception as e:
        return Response({
            "success": False,
            "error": f"Ошибка выполнения действия: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def docker_system_info(request):
    """Получение информации о Docker системе"""
    try:
        if not ssh_service.connected:
            return Response({
                "success": False,
                "error": "Сервер не подключен"
            }, status=status.HTTP_400_BAD_REQUEST)

        system_info = docker_service.get_system_info()

        return Response({
            "success": True,
            "system": system_info
        })

    except Exception as e:
        return Response({
            "success": False,
            "error": f"Ошибка получения информации о системе: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def docker_container_processes(request, container_id):
    """Получение процессов внутри контейнера"""
    try:
        if not ssh_service.connected:
            return Response({
                "success": False,
                "error": "Сервер не подключен"
            }, status=status.HTTP_400_BAD_REQUEST)

        processes_result = docker_service.get_container_processes(container_id)

        return Response(processes_result)

    except Exception as e:
        return Response({
            "success": False,
            "error": f"Ошибка получения процессов: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@require_http_methods(["POST"])
@csrf_exempt
def ai_analyze(request):
    """Анализ системы с помощью ИИ агента"""
    try:
        print(f"🔍 AI Analyze request received")

        if not ssh_service.connected:
            return JsonResponse({
                "success": False,
                "error": "Основной сервер не подключен. Сначала подключитесь к серверу."
            }, status=400)

        # Получаем данные из разных источников
        user_query = ""

        # Пробуем получить из POST данных (form-data)
        if request.POST:
            user_query = request.POST.get('query', '') or request.POST.get('message', '')

        # Пробуем получить из тела запроса (JSON)
        if not user_query and request.body:
            try:
                body_data = json.loads(request.body)
                user_query = body_data.get('query', '') or body_data.get('message', '')
            except json.JSONDecodeError:
                pass

        # Пробуем получить из GET параметров (hx-vals)
        if not user_query and request.GET:
            user_query = request.GET.get('query', '') or request.GET.get('message', '')

        if not user_query:
            return JsonResponse({
                "success": False,
                "error": "Не указан запрос для анализа. Используйте параметр 'query' или 'message'."
            }, status=400)

        print(f"🤖 Запрос на ИИ анализ: {user_query}")

        # Выполняем анализ
        analysis_result = ai_agent.analyze_system_state(user_query)

        return JsonResponse(analysis_result)

    except Exception as e:
        print(f"❌ Ошибка в ai_analyze: {str(e)}")
        import traceback
        traceback.print_exc()

        return JsonResponse({
            "success": False,
            "error": f"Ошибка ИИ анализа: {str(e)}"
        }, status=500)

    except Exception as e:
        print(f"❌ Ошибка в ai_analyze: {str(e)}")
        import traceback
        traceback.print_exc()

        return Response({
            "success": False,
            "error": f"Ошибка ИИ анализа: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def ai_chat(request):
    """Чат с ИИ агентом"""
    try:
        if not ssh_service.connected:
            return Response({
                "success": False,
                "error": "Основной сервер не подключен"
            }, status=status.HTTP_400_BAD_REQUEST)

        message = request.data.get('message', '')
        if not message:
            return Response({
                "success": False,
                "error": "Сообщение не может быть пустым"
            }, status=status.HTTP_400_BAD_REQUEST)

        print(f"💬 Чат с ИИ: {message}")

        chat_result = ai_agent.chat_with_ai(message)

        return Response(chat_result)

    except Exception as e:
        return Response({
            "success": False,
            "error": f"Ошибка чата с ИИ: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def ai_analyze_logs(request):
    """Анализ конкретных логов с помощью ИИ"""
    try:
        if not ssh_service.connected:
            return Response({
                "success": False,
                "error": "Сервер не подключен"
            }, status=status.HTTP_400_BAD_REQUEST)

        log_type = request.GET.get('type', 'system')  # system, docker, auth, kernel
        lines = int(request.GET.get('lines', 50))
        service_name = request.GET.get('service')

        # Получаем логи
        logs_data = {}
        if log_type == 'system':
            logs_result = log_service.get_system_logs(lines=lines, service=service_name)
            if logs_result["success"]:
                logs_data = {
                    "logs": logs_result.get("logs", ""),
                    "source": logs_result.get("source", "")
                }
        elif log_type == 'docker':
            container_name = request.GET.get('container')
            logs_result = log_service.get_docker_logs(container_name=container_name, lines=lines)
            if logs_result["success"]:
                logs_data = {
                    "logs": logs_result.get("logs", ""),
                    "container": logs_result.get("container", "")
                }
        elif log_type == 'auth':
            logs_result = log_service.get_auth_logs(lines=lines)
            if logs_result["success"]:
                logs_data = {
                    "logs": logs_result.get("logs", ""),
                    "source": logs_result.get("source", "")
                }
        elif log_type == 'kernel':
            logs_result = log_service.get_kernel_logs(lines=lines)
            if logs_result["success"]:
                logs_data = {
                    "logs": logs_result.get("logs", ""),
                    "source": logs_result.get("source", "")
                }

        if not logs_data.get("logs"):
            return Response({
                "success": False,
                "error": "Не удалось получить логи для анализа"
            }, status=status.HTTP_400_BAD_REQUEST)

        # Анализируем логи через ИИ
        query = f"Проанализируй эти {log_type} логи и выяви проблемы:\n\n{logs_data['logs'][:3000]}"
        analysis_result = ai_agent.analyze_system_state(query)

        # Добавляем информацию о логах в ответ
        analysis_result["log_info"] = {
            "type": log_type,
            "lines_analyzed": lines,
            "source": logs_data.get("source", ""),
            "container": logs_data.get("container", "")
        }

        return Response(analysis_result)

    except Exception as e:
        return Response({
            "success": False,
            "error": f"Ошибка анализа логов: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def ai_analyze_docker(request):
    """Анализ Docker состояния с помощью ИИ"""
    try:
        if not ssh_service.connected:
            return Response({
                "success": False,
                "error": "Сервер не подключен"
            }, status=status.HTTP_400_BAD_REQUEST)

        container_id = request.GET.get('container_id')

        # Получаем Docker информацию
        docker_data = {}
        if container_id:
            # Информация о конкретном контейнере
            container_info = docker_service.get_container_info(container_id)
            if "error" not in container_info:
                docker_data = {
                    "container": container_info,
                    "logs": docker_service.get_container_logs(container_id, lines=20)["logs"],
                    "stats": docker_service.get_container_stats(container_id)
                }
        else:
            # Общая информация о Docker
            containers = docker_service.list_containers(all_containers=True)
            system_info = docker_service.get_system_info()
            docker_data = {
                "containers": containers,
                "system_info": system_info
            }

        # Анализируем через ИИ
        if container_id:
            query = f"Проанализируй состояние Docker контейнера {container_id}:\n\n{str(docker_data)[:2000]}"
        else:
            query = f"Проанализируй общее состояние Docker системы:\n\n{str(docker_data)[:2000]}"

        analysis_result = ai_agent.analyze_system_state(query)
        analysis_result["docker_info"] = {
            "container_id": container_id,
            "containers_total": len(docker_data.get("containers", [])),
            "containers_running": len([c for c in docker_data.get("containers", []) if c.get("is_running", False)])
        }

        return Response(analysis_result)

    except Exception as e:
        return Response({
            "success": False,
            "error": f"Ошибка анализа Docker: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def ai_conversation_history(request):
    """Получение истории разговора с ИИ"""
    try:
        history = ai_agent.get_conversation_history()
        return Response({
            "success": True,
            "history": history,
            "total_messages": len(history)
        })

    except Exception as e:
        return Response({
            "success": False,
            "error": f"Ошибка получения истории: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def ai_clear_history(request):
    """Очистка истории разговора с ИИ"""
    try:
        ai_agent.clear_conversation_history()
        return Response({
            "success": True,
            "message": "История разговора очищена"
        })

    except Exception as e:
        return Response({
            "success": False,
            "error": f"Ошибка очистки истории: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def ai_status(request):
    """Проверка статуса ИИ агента"""
    try:
        status_info = ai_agent.get_status()

        return Response({
            "success": True,
            **status_info
        })

    except Exception as e:
        return Response({
            "success": False,
            "error": f"Ошибка проверки статуса ИИ: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

def dashboard(request):
    """Главная страница дашборда - перенаправляем на красивую версию"""
    return redirect('pretty_dashboard')

def diagnostics(request):
    """Страница диагностики - перенаправляем на ресурсы"""
    return redirect('pretty_resources')

def docker_view(request):
    """Страница Docker - перенаправляем на красивую версию"""
    return redirect('pretty_docker')

def logs_view(request):
    """Страница логов - перенаправляем на красивую версию"""
    return redirect('pretty_logs')

@api_view(['GET', 'POST'])
def ai_chat(request):
    """Страница чата с ИИ агентом (GET) и обработка сообщений (POST)"""
    if request.method == 'GET':
        quick_queries = [
            "Какие процессы больше всего нагружают систему?",
            "Проверь состояние Docker контейнеров",
            "Есть ли ошибки в системных логах?",
            "Какой общий статус системы?",
            "Покажи топ процессов по памяти",
            "Какие сервисы сейчас работают?",
            "Проверь использование диска",
            "Есть ли проблемы с сетью?"
        ]
        return render(request, 'monitor/ai_chat.html', {'quick_queries': quick_queries})
    else:
        # POST запрос - обрабатываем через API
        return ai_chat_api(request)


def format_ai_response(text):
    """Форматирует ответ ИИ для HTML отображения"""
    if not text:
        return "<p>Нет ответа</p>"

    # Экранируем HTML
    text = escape(text)

    # Форматируем переносы строк
    paragraphs = text.split('\n\n')
    formatted_paragraphs = []

    for paragraph in paragraphs:
        if paragraph.strip():
            # Заменяем одиночные переносы на <br>
            paragraph = paragraph.replace('\n', '<br>')
            formatted_paragraphs.append(f"<p>{paragraph}</p>")

    return ''.join(formatted_paragraphs)


@require_http_methods(["POST"])
@csrf_exempt
def ai_chat_api(request):
    """Чат с ИИ агентом (возвращает HTML)"""
    try:
        if not ssh_service.connected:
            return HttpResponse("""
                <div class="chat-message ai-message">
                    <div class="message-header">🤖 ИИ Агент</div>
                    <p class="text-red-600">❌ Основной сервер не подключен. Сначала подключитесь к серверу.</p>
                </div>
            """)

        # Получаем сообщение из form-data
        message = request.POST.get('message', '')

        if not message:
            return HttpResponse("""
                <div class="chat-message ai-message">
                    <div class="message-header">🤖 ИИ Агент</div>
                    <p class="text-red-600">❌ Сообщение не может быть пустым</p>
                </div>
            """)

        print(f"💬 Чат с ИИ: {message}")

        # Добавляем сообщение пользователя
        user_html = f"""
            <div class="chat-message user-message">
                <div class="message-header">👤 Вы</div>
                <p class="text-gray-800">{escape(message)}</p>
            </div>
        """

        # Получаем ответ от ИИ
        chat_result = ai_agent.chat_with_ai(message)

        # ВАЖНО: Проверяем что chat_result - словарь
        if not isinstance(chat_result, dict):
            print(f"⚠️ chat_with_ai вернул не словарь: {type(chat_result)}")
            chat_result = {
                "success": False,
                "error": "Некорректный ответ от AI агента",
                "response": "Произошла внутренняя ошибка"
            }

        if chat_result.get("success"):
            response_text = chat_result.get("response", "Нет ответа")
            suggested_commands = chat_result.get("suggested_commands", [])
            query_type = chat_result.get("query_type", "general")
            formatted_response = format_ai_response(response_text)

            ai_html = f"""
                <div class="chat-message ai-message">
                    <div class="message-header">
                        <span class="font-semibold">🤖 ИИ Агент</span>
                        <button class="show-full-btn bg-blue-100 hover:bg-blue-200 px-2 py-1 rounded text-xs transition-colors" 
                                data-content="{escape(response_text)}">
                            📄 Полный ответ
                        </button>
                    </div>
                    <div class="ai-response-content">
                        {formatted_response}
            """

            if suggested_commands:
                ai_html += """
                    <div class="mt-3 pt-3 border-t border-gray-200">
                        <p class="font-semibold text-sm text-gray-700 mb-2">💡 Предложенные команды:</p>
                        <div class="space-y-1">
                """
                for cmd in suggested_commands[:3]:
                    escaped_cmd = escape(cmd)
                    ai_html += f'''
                            <div class="flex items-center space-x-2">
                                <code class="bg-gray-800 text-green-400 px-2 py-1 rounded text-xs font-mono flex-1 overflow-x-auto">
                                    {escaped_cmd}
                                </code>
                                <button onclick="copyToClipboard(\"{escaped_cmd}\")" 
                                        class="bg-gray-600 text-white px-2 py-1 rounded text-xs hover:bg-gray-700 transition-colors">
                                    📋
                                </button>
                            </div>
                    '''
                ai_html += """
                        </div>
                    </div>
                """

            ai_html += """
                    </div>
                </div>
            """

            return HttpResponse(user_html + ai_html)
        else:
            error_html = f"""
                <div class="chat-message ai-message">
                    <div class="message-header">🤖 ИИ Агент</div>
                    <p class="text-red-600">❌ Ошибка: {escape(chat_result.get('error', 'Неизвестная ошибка'))}</p>
                </div>
            """
            return HttpResponse(user_html + error_html)

    except Exception as e:
        import traceback
        print(f"❌ Ошибка в ai_chat_api: {str(e)}")
        print(traceback.format_exc())

        error_html = f"""
            <div class="chat-message ai-message">
                <div class="message-header">🤖 ИИ Агент</div>
                <p class="text-red-600">❌ Ошибка чата с ИИ: {escape(str(e))}</p>
            </div>
        """
        return HttpResponse(error_html)


def pretty_dashboard(request):
    """Красивый дашборд"""
    # Пробуем автоматически подключиться если не подключены
    if not ssh_service.connected:
        try:
            from django.conf import settings
            ssh_config = settings.SSH_CONFIG
            ssh_service.connect(
                host=ssh_config['HOST'],
                username=ssh_config['USERNAME'],
                password=ssh_config['PASSWORD'],
                key_file=ssh_config.get('KEY_FILE'),
                port=ssh_config['PORT']
            )
        except Exception as e:
            print(f"⚠️ Автоподключение не удалось: {e}")

    context = {
        'ssh_service': ssh_service,
        'connected': ssh_service.connected
    }
    return render(request, 'monitor/pretty_dashboard.html', context)


def pretty_resources(request):
    """Красивое отображение ресурсов"""
    try:
        resources = diagnostic_service.get_system_resources()

        context = {
            'resources': resources,
            'cpu_usage': resources.get('cpu_usage', 0),
            'memory': resources.get('memory', {}),
            'disk': resources.get('disk', {}),
            'ssh_service': ssh_service,
            'connected': ssh_service.connected
        }
        return render(request, 'monitor/pretty_resources.html', context)
    except Exception as e:
        context = {
            'ssh_service': ssh_service,
            'connected': ssh_service.connected,
            'error': str(e)
        }
        return render(request, 'monitor/pretty_error.html', context)


def pretty_processes(request):
    """Красивое отображение процессов"""
    try:
        limit = int(request.GET.get('limit', 15))
        sort_by = request.GET.get('sort_by', 'cpu')

        processes = diagnostic_service.get_running_processes(limit=limit, sort_by=sort_by)

        context = {
            'processes': processes,
            'total': len(processes),
            'sort_by': sort_by,
            'limit': limit,
            'ssh_service': ssh_service,
            'connected': ssh_service.connected
        }
        return render(request, 'monitor/pretty_processes.html', context)
    except Exception as e:
        context = {
            'ssh_service': ssh_service,
            'connected': ssh_service.connected,
            'error': str(e)
        }
        return render(request, 'monitor/pretty_error.html', context)


def pretty_docker(request):
    """Красивое отображение Docker"""
    try:
        containers = docker_service.list_containers(all_containers=True)

        # ПРАВИЛЬНЫЙ подсчет
        running_containers = [c for c in containers if c.get("is_running", False)]
        stopped_containers = [c for c in containers if not c.get("is_running", False)]

        # Отладочная информация
        print(
            f"🔧 Docker контейнеры: всего={len(containers)}, запущено={len(running_containers)}, остановлено={len(stopped_containers)}")
        for container in containers:
            print(
                f"🔧 Контейнер: {container.get('name')}, Статус: {container.get('status')}, is_running: {container.get('is_running')}")

        context = {
            'containers': containers,
            'running_count': len(running_containers),
            'stopped_count': len(stopped_containers),  # Добавляем явный счетчик остановленных
            'total_count': len(containers),
            'ssh_service': ssh_service,
            'connected': ssh_service.connected
        }
        return render(request, 'monitor/pretty_docker.html', context)
    except Exception as e:
        context = {
            'ssh_service': ssh_service,
            'connected': ssh_service.connected,
            'error': str(e)
        }
        return render(request, 'monitor/pretty_error.html', context)


@api_view(['GET'])
def get_docker_logs_fixed(request):
    """Получение реальных Docker логов (исправленная версия)"""
    try:
        lines = int(request.GET.get('lines', 20))
        container_name = request.GET.get('container', '')

        print(f"🔧 Получение Docker логов: lines={lines}, container={container_name}")

        if container_name:
            # Логи конкретного контейнера
            cmd = f"docker logs {container_name} --tail {lines} 2>&1"
        else:
            # Пробуем разные источники Docker логов
            commands = [
                f"docker logs --tail {lines} $(docker ps -q) 2>&1 | head -{lines}",
                f"journalctl -u docker.service -n {lines} --no-pager 2>&1",
                f"tail -{lines} /var/log/docker.log 2>&1",
                "echo 'Docker logs not available in standard locations'"
            ]

            # Пробуем команды по очереди пока не получим результат
            result = {"success": False, "error": "No logs available"}
            for cmd in commands:
                temp_result = ssh_service.execute_command(cmd)
                if temp_result["success"] and temp_result["output"].strip():
                    result = temp_result
                    break

        result = ssh_service.execute_command(cmd)

        if result["success"]:
            logs_output = result["output"].strip()
            if not logs_output or "No entries" in logs_output or "не видите сообщения" in logs_output:
                # Если логи пустые, получаем список контейнеров как fallback
                containers_cmd = "docker ps -a --format 'table {{.Names}}\\t{{.Status}}\\t{{.Image}}'"
                containers_result = ssh_service.execute_command(containers_cmd)
                if containers_result["success"]:
                    logs_output = "🐳 Информация о Docker контейнерах:\n\n" + containers_result["output"]
                else:
                    logs_output = "📝 Docker логи пусты или недоступны\nПопробуйте выбрать конкретный контейнер"

            return Response({
                "success": True,
                "logs": logs_output,
                "lines": lines,
                "container": container_name if container_name else "all"
            })
        else:
            return Response({
                "success": False,
                "error": result.get("error", "Неизвестная ошибка")
            })

    except Exception as e:
        print(f"❌ Ошибка получения Docker логов: {str(e)}")
        return Response({
            "success": False,
            "error": f"Ошибка получения Docker логов: {str(e)}"
        })


@api_view(['GET'])
def get_docker_containers_list(request):
    """Получение списка Docker контейнеров для выбора в логах"""
    try:
        cmd = "docker ps -a --format '{{.Names}}'"
        result = ssh_service.execute_command(cmd)

        if result["success"]:
            containers = [name for name in result["output"].strip().split('\n') if name]
            return Response({
                "success": True,
                "containers": containers
            })
        else:
            return Response({
                "success": False,
                "error": "Не удалось получить список контейнеров"
            })

    except Exception as e:
        return Response({
            "success": False,
            "error": f"Ошибка получения списка контейнеров: {str(e)}"
        })


def pretty_logs(request):
    """Красивое отображение логов"""
    try:
        lines = int(request.GET.get('lines', 20))
        log_type = request.GET.get('type', 'system')
        container_name = request.GET.get('container', '')

        print(f"🔧 Pretty logs: type={log_type}, lines={lines}, container={container_name}")

        result = {}

        if log_type == 'system':
            result = log_service.get_system_logs(lines=lines)
        elif log_type == 'docker':
            # Используем исправленный метод для Docker логов
            if container_name:
                # Логи конкретного контейнера
                cmd = f"docker logs {container_name} --tail {lines} 2>&1"
                container_result = ssh_service.execute_command(cmd)
                if container_result["success"]:
                    result = {
                        "success": True,
                        "logs": container_result["output"],
                        "container": container_name
                    }
                else:
                    result = {
                        "success": False,
                        "error": f"Не удалось получить логи контейнера {container_name}"
                    }
            else:
                # Общие Docker логи - пробуем несколько источников
                commands = [
                    f"journalctl -u docker -n {lines} --no-pager 2>&1",
                    f"sudo journalctl -u docker.service -n {lines} --no-pager 2>&1",
                    f"docker logs --tail {lines} $(docker ps -q) 2>&1 | head -{lines}",
                    f"tail -n {lines} /var/log/docker.log 2>&1",
                ]

                result = {"success": False, "error": "Не удалось получить Docker логи"}
                for cmd in commands:
                    temp_result = ssh_service.execute_command(cmd)
                    if temp_result["success"] and temp_result["output"].strip():
                        if "No entries" not in temp_result["output"] and "не видите сообщения" not in temp_result[
                            "output"]:
                            result = {
                                "success": True,
                                "logs": temp_result["output"],
                                "source": cmd.split()[0] if ' ' in cmd else cmd
                            }
                            break

                # Если все команды вернули пустой результат, показываем информацию о контейнерах
                if not result["success"]:
                    containers_cmd = "docker ps -a --format '🚀 {{.Names}} | 📊 {{.Status}} | 🏷️ {{.Image}}' | head -20"
                    containers_result = ssh_service.execute_command(containers_cmd)
                    if containers_result["success"]:
                        result = {
                            "success": True,
                            "logs": "📝 Docker логи демона недоступны\n\n" +
                                    "🐳 Вот информация о контейнерах:\n\n" +
                                    containers_result["output"],
                            "source": "containers_info"
                        }
        else:
            result = {'success': False, 'error': 'Unknown log type'}

        # Получаем список контейнеров для выпадающего списка
        containers_cmd = "docker ps -a --format '{{.Names}}' 2>/dev/null || echo ''"
        containers_result = ssh_service.execute_command(containers_cmd)
        containers_list = []
        if containers_result["success"]:
            containers_list = [name for name in containers_result["output"].strip().split('\n') if name]

        context = {
            'logs': result.get('logs', '') if result.get('success') else result.get('error', 'No logs'),
            'lines': lines,
            'log_type': log_type,
            'container_name': container_name,
            'containers_list': containers_list,
            'success': result.get('success', False),
            'ssh_service': ssh_service,
            'connected': ssh_service.connected
        }
        return render(request, 'monitor/pretty_logs.html', context)
    except Exception as e:
        print(f"❌ Ошибка в pretty_logs: {str(e)}")
        context = {
            'ssh_service': ssh_service,
            'connected': ssh_service.connected,
            'error': str(e)
        }
        return render(request, 'monitor/pretty_error.html', context)


def pretty_services(request):
    """Красивое отображение сервисов"""
    try:
        services = diagnostic_service.get_services_status()

        # Сортировка сервисов
        sort_by = request.GET.get('sort', 'status')  # status или name
        if sort_by == 'name':
            services.sort(key=lambda x: x.get('name', '').lower())
        else:  # сортировка по статусу
            status_order = {'running': 0, 'active': 1, 'failed': 2, 'stopped': 3}
            services.sort(key=lambda x: status_order.get(x.get('status', ''), 4))

        running_services = [s for s in services if s.get('status') == 'running']
        failed_services = [s for s in services if s.get('status') == 'failed']

        context = {
            'services': services,
            'running_count': len(running_services),
            'failed_count': len(failed_services),
            'total_count': len(services),
            'sort_by': sort_by,
            'ssh_service': ssh_service,
            'connected': ssh_service.connected
        }
        return render(request, 'monitor/pretty_services.html', context)
    except Exception as e:
        print(f"❌ Ошибка в pretty_services: {str(e)}")
        context = {
            'ssh_service': ssh_service,
            'connected': ssh_service.connected,
            'error': str(e)
        }
        return render(request, 'monitor/pretty_error.html', context)

def pretty_ai_status(request):
    """Красивая страница статуса AI агента"""
    try:
        status_info = ai_agent.get_status()

        context = {
            'status': status_info,
            'connected': ssh_service.connected,
            'ai_connected': status_info.get('ai_agent_connected', False),
            'openai_available': status_info.get('openai_available', False),
            'model': status_info.get('model', 'unknown'),
            'history_count': status_info.get('conversation_history_count', 0)
        }
        return render(request, 'monitor/pretty_ai_status.html', context)

    except Exception as e:
        return render(request, 'monitor/pretty_error.html', {'error': str(e)})


def pretty_ai_history(request):
    """Красивая страница истории разговоров с AI"""
    try:
        history = ai_agent.get_conversation_history()

        context = {
            'history': history,
            'total_messages': len(history),
            'connected': ssh_service.connected
        }
        return render(request, 'monitor/pretty_ai_history.html', context)

    except Exception as e:
        return render(request, 'monitor/pretty_error.html', {'error': str(e)})


def pretty_ai_analyze_docker(request):
    """Красивая страница анализа Docker через AI"""
    try:
        container_id = request.GET.get('container_id')

        if not ssh_service.connected:
            return render(request, 'monitor/pretty_error.html', {
                'error': 'SSH не подключен. Сначала подключитесь к серверу.'
            })

        # Получаем Docker информацию
        docker_data = {}
        if container_id:
            container_info = docker_service.get_container_info(container_id)
            if "error" not in container_info:
                docker_data = {
                    "container": container_info,
                    "logs": docker_service.get_container_logs(container_id, lines=10).get("logs", ""),
                    "stats": docker_service.get_container_stats(container_id)
                }
        else:
            containers = docker_service.list_containers(all_containers=True)
            system_info = docker_service.get_system_info()
            docker_data = {
                "containers": containers,
                "system_info": system_info
            }

        # Анализируем через ИИ
        if container_id:
            query = f"Проанализируй состояние Docker контейнера {container_id}"
        else:
            query = "Проанализируй общее состояние Docker системы"

        analysis_result = ai_agent.analyze_system_state(query)

        context = {
            'analysis': analysis_result,
            'container_id': container_id,
            'docker_data': docker_data,
            'containers_total': len(docker_data.get("containers", [])),
            'containers_running': len([c for c in docker_data.get("containers", []) if c.get("is_running", False)]),
            'connected': ssh_service.connected
        }

        return render(request, 'monitor/pretty_ai_docker.html', context)

    except Exception as e:
        return render(request, 'monitor/pretty_error.html', {'error': f"Ошибка анализа Docker: {str(e)}"})