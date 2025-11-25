from django.urls import path
from django.shortcuts import redirect
from . import views


def redirect_to_dashboard(request):
    return redirect('dashboard')


# API URLs - все под /api/
api_urlpatterns = [
    path('api/', redirect_to_dashboard, name='api-root'),
    path('api/connect/', views.connect_server, name='connect'),
    path('api/connect/simple/', views.connect_server_simple, name='connect-simple'),
    path('api/disconnect/', views.disconnect_server, name='disconnect'),
    path('api/status/', views.server_status, name='status'),
    path('api/logs/system/', views.get_system_logs, name='system-logs'),
    path('api/logs/docker/', views.get_docker_logs, name='docker-logs'),
    path('api/logs/auth/', views.get_auth_logs, name='auth-logs'),
    path('api/logs/kernel/', views.get_kernel_logs, name='kernel-logs'),
    path('api/diagnostic/quick/', views.quick_diagnostic, name='quick-diagnostic'),
    path('api/diagnostic/resources/', views.system_resources, name='system-resources'),
    path('api/diagnostic/processes/', views.running_processes, name='running-processes'),
    path('api/diagnostic/services/', views.services_status, name='services-status'),
    path('api/diagnostic/network/', views.network_info, name='network-info'),
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
    path('api/ai/analyze/', views.ai_analyze, name='ai-analyze'),
    path('api/ai/chat/', views.ai_chat_api, name='ai-chat-api'),
    path('api/ai/analyze/logs/', views.ai_analyze_logs, name='ai-analyze-logs'),
    path('api/ai/analyze/docker/', views.ai_analyze_docker, name='ai-analyze-docker'),
    path('api/ai/history/', views.ai_conversation_history, name='ai-history'),
    path('api/ai/clear-history/', views.ai_clear_history, name='ai-clear-history'),
    path('api/ai/status/', views.ai_status, name='ai-status'),
    path('api/logs/docker/fixed/', views.get_docker_logs_fixed, name='docker-logs-fixed'),
    path('api/docker/containers/list/', views.get_docker_containers_list, name='docker-containers-list'),
]

# Web URLs - красивые HTML страницы
web_urlpatterns = [
    # Главная страница и основные разделы
    path('', views.pretty_dashboard, name='dashboard'),
    path('resources/', views.pretty_resources, name='resources'),
    path('processes/', views.pretty_processes, name='processes'),
    path('docker/', views.pretty_docker, name='docker'),
    path('services/', views.pretty_services, name='services'),
    path('logs/', views.pretty_logs, name='logs'),

    # AI разделы
    path('ai-chat/', views.ai_chat, name='ai_chat'),
    path('ai/status/', views.pretty_ai_status, name='ai_status'),
    path('ai/history/', views.pretty_ai_history, name='ai_history'),
    path('ai/docker/', views.pretty_ai_analyze_docker, name='ai_docker'),


    # Редиректы со старых URL на новые
    path('diagnostics/', lambda request: redirect('resources')),
    path('docker-view/', lambda request: redirect('docker')),
    path('logs-view/', lambda request: redirect('logs')),

    # Редиректы с pretty/ на обычные URLs
    path('pretty/dashboard/', lambda request: redirect('/')),
    path('pretty/resources/', lambda request: redirect('resources')),
    path('pretty/processes/', lambda request: redirect('processes')),
    path('pretty/docker/', lambda request: redirect('docker')),
    path('pretty/services/', lambda request: redirect('services')),
    path('pretty/logs/', lambda request: redirect('logs')),
    path('pretty/ai/status/', lambda request: redirect('ai_status')),
    path('pretty/ai/history/', lambda request: redirect('ai_history')),
    path('pretty/ai/docker/', lambda request: redirect('ai_docker')),
]

# Объединяем все URL
urlpatterns = web_urlpatterns + api_urlpatterns