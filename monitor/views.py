from django.shortcuts import render
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
    """Получение системных логов"""
    try:
        print("📨 Запрос на получение логов")

        # ПРАВИЛЬНАЯ проверка SSH
        if not hasattr(ssh_service, 'connected') or not ssh_service.connected:
            print("❌ SSH не подключен")
            return Response({
                "success": False,
                "error": "SSH сервер не подключен. Сначала подключитесь к серверу."
            }, status=400)

        # Безопасно получаем lines
        lines_str = request.GET.get('lines', '50')
        try:
            lines = int(lines_str)
        except:
            lines = 50

        lines = min(lines, 100)

        service = request.GET.get('service', '')
        print(f"🔧 Получаем логи: lines={lines}, service={service}")

        # Простая команда для логов
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
    """Получение Docker логов"""
    try:
        lines = int(request.GET.get('lines', 50))
        container_name = request.GET.get('container')

        result = log_service.get_docker_logs(
            container_name=container_name,
            lines=lines
        )

        if result["success"]:
            parsed_logs = log_service.parse_log_entries(result["logs"], "docker")

            return Response({
                "success": True,
                "logs": parsed_logs,
                "container": result["container"],
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

        return Response({
            "success": True,
            "containers": containers,
            "total": len(containers),
            "running": len([c for c in containers if c.get("is_running", False)])
        })

    except Exception as e:
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
    """Главная страница дашборда"""
    return render(request, 'monitor/dashboard.html')

def diagnostics(request):
    """Страница диагностики"""
    return render(request, 'monitor/diagnostics.html')

def docker_view(request):
    """Страница Docker"""
    return render(request, 'monitor/docker.html')

def logs_view(request):
    """Страница логов"""
    return render(request, 'monitor/logs.html')

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