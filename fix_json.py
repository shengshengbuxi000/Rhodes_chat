import json

# 原文件路径
input_file = 'prompts/kaltsit_prompts.json'
# 备份文件路径
backup_file = 'prompts/kaltsit_prompts.json.backup'
# 修复后文件路径
output_file = 'prompts/kaltsit_prompts.json'

try:
    # 1. 先备份原文件
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()
    with open(backup_file, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✅ 原文件已备份到：{backup_file}")

    # 2. 尝试用宽松模式读取JSON（忽略控制字符）
    data = json.loads(content, strict=False)
    print("✅ JSON数据读取成功")

    # 3. 重新格式化写回（确保没有非法字符）
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ JSON文件已修复并保存到：{output_file}")
    print("\n🎉 修复完成！现在可以重启Django服务了")

except Exception as e:
    print(f"❌ 修复失败：{str(e)}")
    print("\n请把原文件内容发给我，我手动帮你修复")
