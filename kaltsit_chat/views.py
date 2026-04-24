import os
import json
import hashlib
import random
import logging
import requests
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from asgiref.sync import sync_to_async
from dotenv import load_dotenv
from .models import ChatHistory
from .serializers import ChatHistorySerializer
from pathlib import Path  # 新增：处理文件路径

# 加载环境变量
load_dotenv()

# -------------------------- 核心配置：从JSON文件读取提示词 --------------------------
BASE_DIR = Path(__file__).resolve().parent.parent  # 获取项目根目录
PROMPTS_FILE = BASE_DIR / 'prompts' / 'kaltsit_prompts.json'  # 提示词文件路径

# 读取JSON文件里的所有角色提示词
with open(PROMPTS_FILE, 'r', encoding='utf-8') as f:
    CHARACTER_PROMPTS = json.load(f)

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

# -------------------------- 核心配置 --------------------------
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
MAX_HISTORY_LENGTH = 6



# 角色化错误提示
ERROR_REPLIES = {
    "kaltsit": {
        "timeout": "（医疗部的通讯线路出现短暂波动，猫耳微微动了动，抬手轻敲终端）网络延迟，博士。稍等片刻，我这边重新建立连接。",
        "api_error": "（指尖划过终端屏幕，眉头微蹙）医疗部的临时数据库访问受限，我需要调整权限。你先稍坐，不会太久。",
        "unknown": "（放下手中的报告，看向你）终端出现了一点小故障，博士。不过不用担心，我已经让Mon3tr去排查了，很快就能恢复。"
    }
}

# -------------------------- 工具函数（从FastAPI迁移） --------------------------
def get_client_ip(request):
    """获取用户真实公网IP（兼容代理）"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
        if ip and not ip.startswith(('192.168.', '10.', '172.', '127.')):
            return ip
    return request.META.get('REMOTE_ADDR')

def generate_id_from_ip(ip: str):
    """将IP哈希成32位唯一ID"""
    if not ip or ip.startswith(('192.168.', '10.', '172.', '127.')):
        return ''.join(random.choices('0123456789abcdef', k=32))
    salt = "rhodes_island_medical_2026_v1.4"
    ip_with_salt = (ip + salt).encode("utf-8")
    return hashlib.sha256(ip_with_salt).hexdigest()[:32]

# 异步数据库操作（适配Django异步视图）
@sync_to_async
def async_save_chat(user_id, character, role, content):
    ChatHistory.objects.create(user_id=user_id, character=character, role=role, content=content)

@sync_to_async
def async_get_history(user_id, character):
    history = ChatHistory.objects.filter(user_id=user_id, character=character).order_by('create_time')
    return list(history.values('role', 'content'))[-MAX_HISTORY_LENGTH:]
    
@sync_to_async
def async_get_all_history(user_id, character):
    # 给前端渲染的：取全部历史记录
    history = ChatHistory.objects.filter(user_id=user_id, character=character).order_by('create_time')
    return list(history.values('role', 'content', 'create_time'))

@sync_to_async
def async_clear_history(user_id, character):
    ChatHistory.objects.filter(user_id=user_id, character=character).delete()

# -------------------------- 视图类（对应FastAPI的四个接口） --------------------------
# 1. 基于IP获取用户ID
@method_decorator(csrf_exempt, name='dispatch')
class GetIpUserIdView(View):
    async def get(self, request):
        client_ip = get_client_ip(request)
        user_id = generate_id_from_ip(client_ip)
        logger.info(f"用户IP：{client_ip} → 生成ID：{user_id[:8]}...")
        return JsonResponse({
            "code": 200,
            "user_id": user_id,
            "ip": client_ip,
            "success": True
        })

# 2. 核心对话接口
@method_decorator(csrf_exempt, name='dispatch')
class ChatView(View):
    async def post(self, request):
        try:
            data = json.loads(request.body)
            user_id = data.get('user_id')
            character = data.get('character', 'kaltsit')
            message = data.get('message', '').strip()

            # 验证参数
            if not user_id or not message:
                return JsonResponse({"code": 400, "reply": "缺少必要参数", "success": False})
            if character not in CHARACTER_PROMPTS:
                return JsonResponse({"code": 400, "reply": "该角色暂未上线", "success": False})

            # 获取用户历史
            history = await async_get_history(user_id, character)
            # 构造DeepSeek请求
            request_data = {
                "model": "deepseek-v4-flash",
                "messages": [
                    {"role": "system", "content": CHARACTER_PROMPTS[character]},
                    *history,
                    {"role": "user", "content": message}
                ],
                "temperature": 0.85,
                "max_tokens": 2000,
                "stream": False
            }

            # 调用DeepSeek API
            if not DEEPSEEK_API_KEY:
                return JsonResponse({"code": 500, "reply": "未配置API密钥", "success": False})
            response = requests.post(
                url=DEEPSEEK_API_URL,
                headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
                json=request_data,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            reply_content = result["choices"][0]["message"]["content"].strip()

            # 保存对话
            await async_save_chat(user_id, character, 'user', message)
            await async_save_chat(user_id, character, 'assistant', reply_content)

            return JsonResponse({"code": 200, "reply": reply_content, "success": True})

        except requests.exceptions.Timeout:
            return JsonResponse({"code": 504, "reply": ERROR_REPLIES[character]["timeout"], "success": False})
        except requests.exceptions.HTTPError as e:
            logger.error(f"API调用失败：{str(e)}")
            return JsonResponse({"code": 500, "reply": ERROR_REPLIES[character]["api_error"], "success": False})
        except Exception as e:
            logger.error(f"未知错误：{str(e)}")
            return JsonResponse({"code": 500, "reply": ERROR_REPLIES[character]["unknown"], "success": False})

# 3. 清空历史接口
@method_decorator(csrf_exempt, name='dispatch')
class ClearHistoryView(View):
    async def post(self, request):
        data = json.loads(request.body)
        user_id = data.get('user_id')
        character = data.get('character', 'kaltsit')
        if not user_id:
            return JsonResponse({"code": 400, "msg": "参数错误", "success": False})
        await async_clear_history(user_id, character)
        return JsonResponse({"code": 200, "msg": f"已清空{character}对话记忆", "success": True})

# 4. 获取历史接口
@method_decorator(csrf_exempt, name='dispatch')
class GetHistoryView(View):
    async def post(self, request):
        data = json.loads(request.body)
        user_id = data.get('user_id')
        character = data.get('character', 'kaltsit')
        if not user_id:
            return JsonResponse({"code": 400, "data": [], "success": False})
        history = await async_get_all_history(user_id, character)
        return JsonResponse({"code": 200, "data": history, "success": True})

@method_decorator(csrf_exempt, name='dispatch')
class DownloadHistoryView(View):
    async def get(self, request):
        # 1. 复用现有逻辑获取用户ID
        client_ip = get_client_ip(request)
        user_id = generate_id_from_ip(client_ip)
        character = 'kaltsit'  # 默认角色，可根据需要调整

        # 2. 获取该用户的所有历史记录
        history = await async_get_all_history(user_id, character)

        # 3. 生成TXT内容
        txt_content = "=== 罗德岛医疗部终端 - 聊天记录 ===\n"
        txt_content += f"导出时间：{timezone.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        txt_content += f"用户ID：{user_id[:8]}...\n"
        txt_content += "=" * 50 + "\n\n"

        for msg in history:
            role = "博士" if msg['role'] == "user" else "凯尔希"
            # 格式化时间（如果有）
            time_str = msg.get('create_time', '').strftime('%Y-%m-%d %H:%M:%S') if msg.get('create_time') else ''
            if time_str:
                txt_content += f"[{time_str}]\n"
            txt_content += f"[{role}]\n{msg['content']}\n\n"
            txt_content += "-" * 30 + "\n\n"

        # 4. 返回TXT文件响应
        response = HttpResponse(txt_content, content_type='text/plain; charset=utf-8')
        filename = f"Rhodes_chat_history_{timezone.now().strftime('%Y%m%d_%H%M%S')}.txt"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

# -------------------------- 【新增】6. 回档：删除最近一次对话 --------------------------
@sync_to_async
def async_rollback_last_chat(user_id, character):
    """删除该用户最近的两条记录（用户一条+AI一条）"""
    # 1. 按时间倒序，取最近的2条记录（先取出来）
    last_two = list(ChatHistory.objects.filter(
        user_id=user_id, 
        character=character
    ).order_by('-create_time')[:2])
    
    # 2. 获取这两条记录的ID
    ids_to_delete = [record.id for record in last_two]
    
    # 3. 根据ID删除（绕过切片限制）
    if ids_to_delete:
        count = ChatHistory.objects.filter(id__in=ids_to_delete).delete()[0]
        return count
    return 0

@method_decorator(csrf_exempt, name='dispatch')
class RollbackView(View):
    async def post(self, request):
        data = json.loads(request.body)
        user_id = data.get('user_id')
        character = data.get('character', 'kaltsit')
        
        if not user_id:
            return JsonResponse({"code": 400, "msg": "参数错误", "success": False})
        
        # 执行回档
        deleted_count = await async_rollback_last_chat(user_id, character)
        
        if deleted_count > 0:
            return JsonResponse({
                "code": 200, 
                "msg": f"已回档，删除了最近{deleted_count}条记录", 
                "success": True
            })
        else:
            return JsonResponse({
                "code": 400, 
                "msg": "没有可回档的对话记录", 
                "success": False
            })