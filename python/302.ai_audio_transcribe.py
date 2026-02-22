import argparse
import requests
import os
import json

def format_srt_time(seconds):
    """将秒数转换为 SRT 字幕格式的时间戳 (HH:MM:SS,mmm)"""
    if seconds is None: seconds = 0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def format_standard_time(seconds):
    """将秒数转换为标准时间戳格式 (HH:MM:SS.mmm)"""
    if seconds is None: seconds = 0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"

def extract_elevenlabs_segments(words):
    """将 ElevenLabs 的词级时间戳拼装成句子级别的 segments"""
    segments = []
    if not words: return segments
    
    start_time = None
    end_time = None
    text_buffer = ""
    
    for w in words:
        if w.get("type") == "word":
            if start_time is None:
                start_time = w.get("start", 0)
            end_time = w.get("end", 0)
            
        text_buffer += w.get("text", "")
        
        # 遇到标点及后续空格时，进行断句
        if text_buffer.endswith(('. ', '? ', '! ', '。', '？', '！')):
            segments.append({
                "start": start_time if start_time is not None else 0,
                "end": end_time if end_time is not None else 0,
                "text": text_buffer.strip()
            })
            start_time = None
            text_buffer = ""
            
    # 处理最后一段未以标点结尾的文本
    if text_buffer.strip():
        segments.append({
            "start": start_time if start_time is not None else 0,
            "end": end_time if end_time is not None else 0,
            "text": text_buffer.strip()
        })
    return segments

def transcribe_audio(file_input, api_key, model_id, output_file=None, show_timestamps=False, language="zh"):
    headers = {
        'Authorization': f'Bearer {api_key}'
    }

    print(f"⏳ 正在处理音频: {file_input} [模型: {model_id}, 语言: {language}] ...")

    try:
        segments = []
        transcribed_text = ""
        result_json = {}

        # ==========================================
        # 1. WhisperX 模型处理
        # ==========================================
        if model_id.lower() == "whisperx":
            api_url = "https://api.302.ai/302/whisperx"
            
            if file_input.startswith("http://") or file_input.startswith("https://"):
                print("❌ 错误: whisperx 模型不支持通过 URL 传参，请提供本地文件路径。")
                return
            if not os.path.exists(file_input):
                print(f"❌ 错误: 找不到本地文件 '{file_input}'")
                return

            with open(file_input, 'rb') as audio_file:
                files = {'audio_input': (os.path.basename(file_input), audio_file)}
                data = {
                    'processing_type': 'align', 
                    'translate': 'false', 
                    'output': 'text',
                    'language': language  # 传入语言参数
                }
                response = requests.post(api_url, headers=headers, files=files, data=data)

            if response.status_code == 200:
                result_json = response.json()
                segments = result_json.get("segments", [])
                transcribed_text = " ".join([seg.get("text", "").strip() for seg in segments])

        # ==========================================
        # 2. ElevenLabs (scribe_v1) 处理
        # ==========================================
        else:
            api_url = "https://api.302.ai/elevenlabs/speech-to-text"
            
            if file_input.startswith("http://") or file_input.startswith("https://"):
                headers['Content-Type'] = 'application/json'
                payload = {
                    "file": file_input, 
                    "model_id": model_id,
                    "language_code": language  # 传入语言参数
                }
                response = requests.post(api_url, headers=headers, json=payload)
            else:
                if not os.path.exists(file_input):
                    print(f"❌ 错误: 找不到本地文件 '{file_input}'")
                    return
                with open(file_input, 'rb') as audio_file:
                    files = {'file': (os.path.basename(file_input), audio_file)}
                    data = {
                        'model_id': model_id,
                        'language_code': language  # 传入语言参数
                    }
                    response = requests.post(api_url, headers=headers, files=files, data=data)

            if response.status_code == 200:
                result_json = response.json()
                transcribed_text = result_json.get("text", "（未解析到文本）")
                words = result_json.get("words", [])
                segments = extract_elevenlabs_segments(words)

        # ==========================================
        # 3. 统一输出逻辑
        # ==========================================
        if response.status_code == 200:
            print("\n✅ 转写成功！\n" + "-" * 40)
            
            # 终端打印：使用标准时间戳格式
            if show_timestamps and segments:
                for seg in segments:
                    start_str = format_standard_time(seg.get('start', 0))
                    end_str = format_standard_time(seg.get('end', 0))
                    text = seg.get('text', '')
                    print(f"[{start_str} --> {end_str}] {text}")
            else:
                print(transcribed_text)
                
            print("-" * 40)
            
            # 处理输出文件
            if output_file:
                try:
                    with open(output_file, 'w', encoding='utf-8') as f:
                        output_ext = output_file.lower()
                        
                        # 导出 JSON
                        if output_ext.endswith('.json'):
                            json.dump(result_json, f, indent=4, ensure_ascii=False)
                            print(f"📄 完整结果已保存至: {output_file}")
                            
                        # 导出 SRT 字幕
                        elif output_ext.endswith('.srt'):
                            for i, seg in enumerate(segments, 1):
                                start_str = format_srt_time(seg.get('start', 0))
                                end_str = format_srt_time(seg.get('end', 0))
                                text = seg.get('text', '').strip()
                                f.write(f"{i}\n{start_str} --> {end_str}\n{text}\n\n")
                            print(f"🎬 SRT 字幕已生成并保存至: {output_file}")
                            
                        # 导出 TXT 文本：使用标准时间戳格式写入
                        else:
                            if show_timestamps and segments:
                                for seg in segments:
                                    start_str = format_standard_time(seg.get('start', 0))
                                    end_str = format_standard_time(seg.get('end', 0))
                                    text = seg.get('text', '')
                                    f.write(f"[{start_str} --> {end_str}] {text}\n")
                                print(f"📄 带标准时间戳的文本已保存至: {output_file}")
                            else:
                                f.write(transcribed_text)
                                print(f"📄 纯文本已保存至: {output_file}")
                except IOError as e:
                    print(f"❌ 保存文件时发生错误: {str(e)}")
        else:
            print(f"❌ 请求失败，状态码: {response.status_code}")
            print(f"详细信息: {response.text}")

    except Exception as e:
        print(f"❌ 发生异常: {str(e)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="调用 302.ai API 将音频转写为文本")
    parser.add_argument("-f", "--file", required=True, help="音频文件的本地路径 (或 ElevenLabs 允许的 URL)")
    parser.add_argument("-k", "--key", required=True, help="API 授权密钥")
    parser.add_argument("-m", "--model", default="scribe_v1", help="模型 ID (例如: scribe_v1, whisperx)")
    parser.add_argument("-o", "--output", help="输出文件路径 (支持 .txt, .json, .srt)")
    parser.add_argument("-t", "--timestamps", action="store_true", help="在终端输出及 txt 导出中启用标准时间戳")
    # 新增语言参数
    parser.add_argument("-l", "--language", default="zh", help="目标语言代码 (默认: zh)")

    args = parser.parse_args()
    transcribe_audio(args.file, args.key, args.model, args.output, args.timestamps, args.language)
