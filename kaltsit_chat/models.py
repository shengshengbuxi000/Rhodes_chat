from django.db import models
from django.utils import timezone

class ChatHistory(models.Model):
    """对话历史模型（所有角色共用）"""
    # 角色选择（后续加新角色只需在这里加选项）
    CHARACTER_CHOICES = [
        ('kaltsit', '凯尔希'),
        # ('amiya', '阿米娅'),  # 后续加新角色取消注释即可
    ]

    user_id = models.CharField(max_length=64, verbose_name='用户ID（IP生成）')
    character = models.CharField(
        max_length=32,
        choices=CHARACTER_CHOICES,
        default='kaltsit',
        verbose_name='对话角色'
    )
    role = models.CharField(
        max_length=16,
        choices=[('user', '博士'), ('assistant', '角色')],
        verbose_name='发言角色'
    )
    content = models.TextField(verbose_name='对话内容')
    create_time = models.DateTimeField(default=timezone.now, verbose_name='创建时间')

    class Meta:
        ordering = ['create_time']
        verbose_name = '对话历史'
        verbose_name_plural = '对话历史'

    def __str__(self):
        return f'{self.user_id[:8]} - {self.character} - {self.content[:20]}'