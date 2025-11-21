from django.urls import path
from django.shortcuts import redirect
from . import views


def redirect_to_dashboard(request):
    """Перенаправление с /api/ на главную страницу"""
    return redirect('dashboard')


# Web URLs - доступны в корне
web_urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('diagnostics/', views.diagnostics, name='diagnostics'),
    path('docker/', views.docker_view, name='docker'),
    path('logs/', views.logs_view, name='logs'),
    path('ai-chat/', views.ai_chat, name='ai_chat'),  # Теперь поддерживает GET и POST
]

# API URLs - все под /api/
api_urlpatterns = [
    # Redirect для /api/
    path('api/', redirect_to_dashboard, name='api-root'),

    # Подключение
    path('api/connect/', views.connect_server, name='connect'),
    path('api/connect/simple/', views.connect_server_simple, name='connect-simple'),
    path('api/disconnect/', views.disconnect_server, name='disconnect'),
    path('api/status/', views.server_status, name='status'),

    # Логи
    path('api/logs/system/', views.get_system_logs, name='system-logs'),
    path('api/logs/docker/', views.get_docker_logs, name='docker-logs'),
    path('api/logs/auth/', views.get_auth_logs, name='auth-logs'),
    path('api/logs/kernel/', views.get_kernel_logs, name='kernel-logs'),

    # Диагностика
    path('api/diagnostic/quick/', views.quick_diagnostic, name='quick-diagnostic'),
    path('api/diagnostic/resources/', views.system_resources, name='system-resources'),
    path('api/diagnostic/processes/', views.running_processes, name='running-processes'),
    path('api/diagnostic/services/', views.services_status, name='services-status'),
    path('api/diagnostic/network/', views.network_info, name='network-info'),

    # Docker
    path('api/docker/containers/', views.docker_containers, name='docker-containers'),
    path('api/docker/containers/<str:container_id>/', views.docker_container_info, name='docker-container-info'),
    path('api/docker/containers/<str:container_id>/logs/', views.docker_container_logs, name='docker-container-logs'),
    path('api/docker/containers/<str:container_id>/stats/', views.docker_container_stats,
         name='docker-container-stats'),
    path('api/docker/containers/<str:container_id>/processes/', views.docker_container_processes,
         name='docker-container-processes'),
    path('api/docker/containers/<str:container_id>/<str:action>/', views.docker_container_action,
         name='docker-container-action'),
    path('api/docker/system/', views.docker_system_info, name='docker-system-info'),

    # ИИ Агент API
    path('api/ai/analyze/', views.ai_analyze, name='ai-analyze'),
    path('api/ai/chat/', views.ai_chat_api, name='ai-chat-api'),  # Только API
    path('api/ai/analyze/logs/', views.ai_analyze_logs, name='ai-analyze-logs'),
    path('api/ai/analyze/docker/', views.ai_analyze_docker, name='ai-analyze-docker'),
    path('api/ai/history/', views.ai_conversation_history, name='ai-history'),
    path('api/ai/clear-history/', views.ai_clear_history, name='ai-clear-history'),
    path('api/ai/status/', views.ai_status, name='ai-status'),
]

# Объединяем все URL
urlpatterns = web_urlpatterns + api_urlpatterns