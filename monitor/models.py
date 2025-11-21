from django.db import models


class ServerConnection(models.Model):
    host = models.CharField(max_length=255)
    username = models.CharField(max_length=100)
    port = models.IntegerField(default=22)
    connected = models.BooleanField(default=False)
    last_connection = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'server_connections'


class CommandExecution(models.Model):
    command = models.TextField()
    output = models.TextField()
    error = models.TextField(blank=True)
    success = models.BooleanField(default=False)
    execution_time = models.FloatField()
    executed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'command_executions'
        ordering = ['-executed_at']


class ServiceLog(models.Model):
    SERVICE_TYPES = [
        ('system', 'System'),
        ('docker', 'Docker'),
        ('web', 'Web Service'),
        ('database', 'Database'),
    ]

    service_name = models.CharField(max_length=100)
    service_type = models.CharField(max_length=20, choices=SERVICE_TYPES)
    log_content = models.TextField()
    log_file_path = models.CharField(max_length=500)
    lines_count = models.IntegerField()
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'service_logs'
        ordering = ['-fetched_at']