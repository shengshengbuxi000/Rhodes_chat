import os
import json
import hashlib
import random
import re
import logging
import requests
from django.http import JsonResponse, HttpResponse  # 补全HttpResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.utils import timezone  # 🔥 修复缺失导入
from asgiref.sync import sync_to_async
from dotenv import load_dotenv
from .models import ChatHistory
from .serializers import ChatHistorySerializer
from pathlib import Path

# 加载环境变量
load_dotenv()

# -------------------------- 核心配置：从JSON文件读取提示词 --------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
SYSTEM_PROMPT_FILE = BASE_DIR / 'prompts' / 'kaltsit_prompts.txt'

with open(SYSTEM_PROMPT_FILE, 'r', encoding='utf-8') as f:
    KALTSIT_SYSTEM_PROMPT = f.read()

# 保持 CHARACTER_PROMPTS 字典结构，便于其他角色扩展（如有）
CHARACTER_PROMPTS = {
    "kaltsit": KALTSIT_SYSTEM_PROMPT,
    # 以后如需添加其他角色，可以继续加
}

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

# -------------------------- 工具函数 --------------------------
def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
        if ip and not ip.startswith(('192.168.', '10.', '172.', '127.')):
            return ip
    return request.META.get('REMOTE_ADDR')

def generate_id_from_ip(ip: str):
    if not ip or ip.startswith(('192.168.', '10.', '172.', '127.')):
        return ''.join(random.choices('0123456789abcdef', k=32))
    salt = "rhodes_island_medical_2026_v1.4"
    ip_with_salt = (ip + salt).encode("utf-8")
    return hashlib.sha256(ip_with_salt).hexdigest()[:32]

# 异步数据库操作
@sync_to_async
def async_save_chat(user_id, character, role, content):
    ChatHistory.objects.create(
        user_id=user_id, 
        character=character, 
        role=role, 
        content=content
    )
    
@sync_to_async
def async_get_history(user_id, character):
    history = ChatHistory.objects.filter(user_id=user_id, character=character).order_by('create_time')
    return list(history.values('role', 'content'))[-MAX_HISTORY_LENGTH:]
    
@sync_to_async
def async_get_all_history(user_id, character):
    history = ChatHistory.objects.filter(user_id=user_id, character=character).order_by('create_time')
    return list(history.values('role', 'content', 'create_time'))

@sync_to_async
def async_clear_history(user_id, character):
    ChatHistory.objects.filter(user_id=user_id, character=character).delete()

# -------------------------- 视图类 --------------------------
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

# ========== 总结函数（放在 views.py 顶部工具函数区域） ==========
async def summarize_history(history_messages: list) -> str:
    """
    对给定的消息列表进行总结，返回摘要字符串
    history_messages: list of dict with keys 'role', 'content'
    """
    if not history_messages:
        return "（无历史内容）"

    summary_prompt = {
        "role": "system",
        "content": "你是一个总结助手。请将以下对话提炼成一段简洁的摘要（100字以内），保留关键信息：话题、事件、情绪或重要结论。只输出摘要，不要输出其他内容。"
    }

    # 将消息列表转换为文本
    history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history_messages])

    # 如果文本太长，可以截断前3000字符避免超限
    if len(history_text) > 3000:
        history_text = history_text[:3000] + "……（已截断）"

    request_data = {
        "model": "deepseek-v4-flash",
        "messages": [
            summary_prompt,
            {"role": "user", "content": f"请总结以下对话：\n{history_text}"}
        ],
        "temperature": 0.3,
        "max_tokens": 2000,
        "stream": False
    }

    try:
        response = requests.post(
            url=DEEPSEEK_API_URL,
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
            json=request_data,
            timeout=15
        )
        response.raise_for_status()
        result = response.json()
        summary = result["choices"][0]["message"]["content"].strip()
        # 添加说明，提示模型后续基于此摘要
        return f"【以下为最近10条历史对话摘要，后续对话请基于此摘要并结合最新消息】\n{summary}"
    except Exception as e:
        logger.warning(f"历史总结失败：{e}")
        return "（总结失败）"


# ========== 修改后的 ChatView（定时触发，只总结最近10条消息，不含保留的最近6条） ==========
@method_decorator(csrf_exempt, name='dispatch')
class ChatView(View):
    async def post(self, request):
        try:
            data = json.loads(request.body)
            user_id = data.get('user_id')
            character = data.get('character', 'kaltsit')
            original_message = data.get('message', '').strip()

            if not user_id or not original_message:
                return JsonResponse({"code": 400, "reply": "缺少必要参数", "success": False})
            if character not in CHARACTER_PROMPTS:
                return JsonResponse({"code": 400, "reply": "该角色暂未上线", "success": False})

            # 格式提醒（方案三）
            user_message_with_hint = (
                original_message +
                "\n\n【格式提醒】回复中括号内的动作/神态描写：指代凯尔希必须用“她”，指代博士必须用“你”。"
                "例如：（她放下报告，抬眼看向你）。引号对话中凯尔希自称“我”，称呼博士为“你”。"
                "请严格遵守，不要用“我”或“他”来描述括号内的动作。"
            )

            # 获取完整历史（按时间正序）
            history = await async_get_history(user_id, character)   # list of dict

            # ----- 定时触发总结配置 -----
            USE_SUMMARY = True
            SUMMARY_INTERVAL = 12            # 每12条消息触发一次总结（历史消息总数）
            KEEP_RECENT = 6                  # 保留最近6条消息完整
            # 需要总结的消息数量（最近的不含保留的6条）
            SUMMARY_COUNT = 12               # 总结最近10条

            total_messages = len(history)

            # 触发条件：
            # 1. 总消息数 >= (KEEP_RECENT + SUMMARY_COUNT) 才能提取出10条需要总结的消息
            # 2. 总消息数达到 SUMMARY_INTERVAL 的整数倍
            min_required = KEEP_RECENT + SUMMARY_COUNT   # = 16
            should_summarize = (
                USE_SUMMARY and 
                total_messages >= min_required and 
                total_messages % SUMMARY_INTERVAL == 0
            )

            if should_summarize:
                # 需要总结的消息：倒数第 (KEEP_RECENT+SUMMARY_COUNT) 条 到 倒数第 (KEEP_RECENT+1) 条
                # 即 history[-16:-6]  （因为 -16 到 -6 不包含 -6 本身，包含 -16）
                start = - (KEEP_RECENT + SUMMARY_COUNT)   # -16
                end = - KEEP_RECENT                       # -6
                to_summarize = history[start:end]         # 长度为 SUMMARY_COUNT 的列表
                recent_history = history[-KEEP_RECENT:] if KEEP_RECENT > 0 else []

                # 生成总结
                summary_text = await summarize_history(to_summarize)

                # 构建 messages：系统提示 + 总结 + 最近6条消息 + 当前用户消息（带提醒）
                messages = [
                    {"role": "system", "content": CHARACTER_PROMPTS[character]},
                    {"role": "system", "content": summary_text}
                ] + recent_history + [
                    {"role": "user", "content": user_message_with_hint}
                ]
            else:
                # 不满足阈值，直接使用完整历史
                messages = [
                    {"role": "system", "content": CHARACTER_PROMPTS[character]},
                    *history,
                    {"role": "user", "content": user_message_with_hint}
                ]

            # 构造请求数据
            request_data = {
                "model": "deepseek-v4-flash",
                "messages": messages,
                "temperature": 0.85,
                "max_tokens": 2000,
                "stream": False
            }

            if not DEEPSEEK_API_KEY:
                return JsonResponse({"code": 500, "reply": "未配置API密钥", "success": False})

            # 调用 DeepSeek API
            response = requests.post(
                url=DEEPSEEK_API_URL,
                headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
                json=request_data,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            reply_content = result["choices"][0]["message"]["content"].strip()

            # 保存原始消息和回复
            await async_save_chat(user_id, character, 'user', original_message)
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

# 4. 获取历史接口（原版异步，保留不动）
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

# 5. 下载历史接口
@method_decorator(csrf_exempt, name='dispatch')
class DownloadHistoryView(View):
    async def get(self, request):
        client_ip = get_client_ip(request)
        user_id = generate_id_from_ip(client_ip)
        character = 'kaltsit'

        history = await async_get_all_history(user_id, character)

        txt_content = "=== 罗德岛医疗部终端 - 聊天记录 ===\n"
        txt_content += f"导出时间：{timezone.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        txt_content += f"用户ID：{user_id[:8]}...\n"
        txt_content += "=" * 50 + "\n\n"

        for msg in history:
            role = "博士" if msg['role'] == "user" else "凯尔希"
            time_str = msg.get('create_time', '').strftime('%Y-%m-%d %H:%M:%S') if msg.get('create_time') else ''
            if time_str:
                txt_content += f"[{time_str}]\n"
            txt_content += f"[{role}]\n{msg['content']}\n\n"
            txt_content += "-" * 30 + "\n\n"

        response = HttpResponse(txt_content, content_type='text/plain; charset=utf-8')
        filename = f"Rhodes_chat_history_{timezone.now().strftime('%Y%m%d_%H%M%S')}.txt"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

# 6. 回档接口
@sync_to_async
def async_rollback_last_chat(user_id, character):
    last_two = list(ChatHistory.objects.filter(
        user_id=user_id, 
        character=character
    ).order_by('-create_time')[:2])
    
    ids_to_delete = [record.id for record in last_two]
    
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

# -------------------------- 解析函数 --------------------------
def parse_chat_txt(txt_content: str):
    lines = txt_content.split('\n')
    chat_list = []
    current_role = None
    current_content = []

    ROLE_MAP = {
        "博士": "user",
        "凯尔希": "assistant"
    }

    for line in lines:
        raw_line = line.rstrip('\n')
        
        if raw_line.startswith('【罗德岛') or raw_line.startswith('生成时间：') or raw_line.startswith('用户ID：'):
            continue
        if raw_line.startswith('-----------------------------'):
            continue
        if raw_line.startswith('[系统]'):
            continue
        
        if raw_line.startswith('> '):
            role_part = raw_line[2:].rstrip('：').strip()
            if role_part in ROLE_MAP:
                if current_role and current_content:
                    chat_list.append({
                        "role": current_role,
                        "content": '\n'.join(current_content).strip()
                    })
                    current_content = []
                current_role = ROLE_MAP[role_part]
                continue
        
        if current_role:
            current_content.append(raw_line)
    
    if current_role and current_content:
        chat_list.append({
            "role": current_role,
            "content": '\n'.join(current_content).strip()
        })
    
    print(f"✅ 解析成功！共解析到 {len(chat_list)} 条聊天记录")
    return chat_list

# 🔥 【修复缺失】导入历史接口（解决urls.py导入报错）
@method_decorator(csrf_exempt, name='dispatch')
class ImportHistoryView(View):
    async def post(self, request):
        try:
            data = json.loads(request.body)
            current_user_id = data.get('user_id')
            character = data.get('character', 'kaltsit')
            txt_content = data.get('txt_content')
            import_mode = data.get('mode', 'clear')

            if not current_user_id or not txt_content:
                return JsonResponse({"code": 400, "msg": "缺少参数", "success": False})

            # 解析聊天记录
            chat_list = parse_chat_txt(txt_content)
            if not chat_list:
                return JsonResponse({"code": 400, "msg": "未解析到有效记录", "success": False})

            # 清空模式
            if import_mode == 'clear':
                await async_clear_history(current_user_id, character)

            # 保存记录
            for item in chat_list:
                await async_save_chat(
                    user_id=current_user_id,
                    character=character,
                    role=item['role'],
                    content=item['content']
                )

            return JsonResponse({
                "code": 200,
                "msg": f"导入成功！共导入 {len(chat_list)} 条记录",
                "success": True
            })
        except Exception as e:
            return JsonResponse({"code": 500, "msg": str(e), "success": False})