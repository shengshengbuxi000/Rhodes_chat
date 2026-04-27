from django.urls import path
from .views import (
    GetIpUserIdView,
    ChatView,
    ClearHistoryView,
    GetHistoryView,
    DownloadHistoryView,
    RollbackView,
    ImportHistoryView,
)

urlpatterns = [
    path('get_ip_user_id/', GetIpUserIdView.as_view()),
    path('chat/', ChatView.as_view()),
    path('clear_history/', ClearHistoryView.as_view()),
    path('get_history/', GetHistoryView.as_view()),
    path('download_history/', DownloadHistoryView.as_view()),
    path('rollback/', RollbackView.as_view()),
    path('import_history/', ImportHistoryView.as_view()),
]