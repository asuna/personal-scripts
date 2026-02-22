import argparse
import requests
import os
import json

def transcribe_audio(file_input, api_key, model_id, output_file=None):
    # 基础 Headers：只保留鉴权信息
    headers = {
        'Authorization': f'Bearer {api_key}'
    }

    print(f"⏳ 正在处理音频: {file_input} [模型: {model_id}] ...")

    try:
        # ==========================================
        # 逻辑分支 1: WhisperX 模型
        # ==========================================
        if model_id.lower() == "whisperx":
            api_url = "https://api.302.ai/302/whisperx"
            
            # WhisperX 不支持 URL 格式
            if file_input.startswith("http://") or file_input.startswith("https://"):
                print("❌ 错误: whisperx 模型不支持通过 URL 传参，请提供本地文件路径。")
                return
            
            if not os.path.exists(file_input):
                print(f"❌ 错误: 找不到本地文件 '{file_input}'")
                return

            with open(file_input, 'rb') as audio_file:
                # 注意：WhisperX 的文件字段名为 'audio_input'
                files = {
                    'audio_input': (os.path.basename(file_input), audio_file)
                }
                # WhisperX 特有的表单参数
                data = {
                    'processing_type': 'align',
                    'translate': 'false',
                    'output': 'text'
                }
                response = requests.post(api_url, headers=headers, files=files, data=data)

            # 解析 WhisperX 的响应 (从 segments 数组中提取文字)
            if response.status_code == 200:
                result_json = response.json()
                segments = result_json.get("segments", [])
                # 拼接所有片段的文本
                transcribed_text = " ".join([seg.get("text", "").strip() for seg in segments])
                if not transcribed_text:
                    transcribed_text = "（未解析到文本）"

        # ==========================================
        # 逻辑分支 2: 默认的 ElevenLabs 模型 (例如 scribe_v1)
        # ==========================================
        else:
            api_url = "https://api.302.ai/elevenlabs/speech-to-text"
            
            if file_input.startswith("http://") or file_input.startswith("https://"):
                headers['Content-Type'] = 'application/json'
                payload = {
                    "file": file_input,
                    "model_id": model_id
                }
                response = requests.post(api_url, headers=headers, json=payload)
                
            else:
                if not os.path.exists(file_input):
                    print(f"❌ 错误: 找不到本地文件 '{file_input}'")
                    return

                with open(file_input, 'rb') as audio_file:
                    # 注意：ElevenLabs 的文件字段名为 'file'
                    files = {
                        'file': (os.path.basename(file_input), audio_file)
                    }
                    data = {
                        'model_id': model_id
                    }
                    response = requests.post(api_url, headers=headers, files=files, data=data)

            # 解析 ElevenLabs 的响应
            if response.status_code == 200:
                result_json = response.json()
                transcribed_text = result_json.get("text", "（未解析到文本）")


        # ==========================================
        # 统一处理成功响应与输出逻辑
        # ==========================================
        if response.status_code == 200:
            print("\n✅ 转写成功！")
            print("-" * 40)
            print(transcribed_text)
            print("-" * 40)
            
            # 处理输出文件
            if output_file:
                try:
                    with open(output_file, 'w', encoding='utf-8') as f:
                        if output_file.lower().endswith('.json'):
                            json.dump(result_json, f, indent=4, ensure_ascii=False)
                            print(f"📄 完整结果已保存至 JSON 文件: {output_file}")
                        else:
                            f.write(transcribed_text)
                            print(f"📄 转写文本已保存至 TXT 文件: {output_file}")
                except IOError as e:
                    print(f"❌ 保存文件时发生错误: {str(e)}")
        else:
            print(f"❌ 请求失败，状态码: {response.status_code}")
            print(f"详细信息: {response.text}")

    except Exception as e:
        print(f"❌ 发生异常: {str(e)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="调用 302.ai API 将音频转写为文本 (支持 ElevenLabs 及 WhisperX)")
    parser.add_argument(
        "-f", "--file", 
        required=True, 
        help="音频文件的本地路径 (或 ElevenLabs 允许的线上 URL)"
    )
    parser.add_argument(
        "-k", "--key", 
        required=True, 
        help="API 授权密钥 (Bearer Token)"
    )
    parser.add_argument(
        "-m", "--model", 
        default="scribe_v1", 
        help="使用的模型 ID (例如: scribe_v1, whisperx)"
    )
    parser.add_argument(
        "-o", "--output", 
        help="输出文件路径 (例如: result.txt 或 result.json)"
    )

    args = parser.parse_args()

    transcribe_audio(args.file, args.key, args.model, args.output)
