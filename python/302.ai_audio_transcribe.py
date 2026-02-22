import argparse
import requests
import os
import json

SUPPORTED_EXTENSIONS = ('.mp3', '.wav', '.m4a', '.flac', '.ogg', '.aac')

def format_srt_time(seconds):
    if seconds is None: seconds = 0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def format_standard_time(seconds):
    if seconds is None: seconds = 0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"

def extract_elevenlabs_segments(words):
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
        if text_buffer.endswith(('. ', '? ', '! ', '。', '？', '！')):
            segments.append({
                "start": start_time if start_time is not None else 0,
                "end": end_time if end_time is not None else 0,
                "text": text_buffer.strip()
            })
            start_time = None
            text_buffer = ""
    if text_buffer.strip():
        segments.append({
            "start": start_time if start_time is not None else 0,
            "end": end_time if end_time is not None else 0,
            "text": text_buffer.strip()
        })
    return segments

def process_single_audio(file_input, api_key, model_id, output_path=None, batch_dir=None, batch_basename=None, target_ext=None, show_timestamps=False, language="zh"):
    """
    处理核心逻辑：
    - 单文件模式使用 output_path
    - 批量模式使用 batch_dir, batch_basename 和 target_ext 动态拼装带语言代码的文件名
    """
    headers = {'Authorization': f'Bearer {api_key}'}
    print(f"\n⏳ 正在处理: {file_input} [模型: {model_id}, 预设语言: {language}] ...")

    try:
        segments = []
        transcribed_text = ""
        result_json = {}

        # ================== 1. WhisperX ==================
        if model_id.lower() == "whisperx":
            api_url = "https://api.302.ai/302/whisperx"
            if file_input.startswith("http://") or file_input.startswith("https://"):
                print("❌ 错误: whisperx 模型不支持通过 URL 传参，已跳过。")
                return False
            
            with open(file_input, 'rb') as audio_file:
                files = {'audio_input': (os.path.basename(file_input), audio_file)}
                data = {'processing_type': 'align', 'translate': 'false', 'output': 'text', 'language': language}
                response = requests.post(api_url, headers=headers, files=files, data=data)

            if response.status_code == 200:
                result_json = response.json()
                segments = result_json.get("segments", [])
                transcribed_text = " ".join([seg.get("text", "").strip() for seg in segments])

        # ================== 2. ElevenLabs ==================
        else:
            api_url = "https://api.302.ai/elevenlabs/speech-to-text"
            if file_input.startswith("http://") or file_input.startswith("https://"):
                headers['Content-Type'] = 'application/json'
                payload = {"file": file_input, "model_id": model_id, "language_code": language}
                response = requests.post(api_url, headers=headers, json=payload)
            else:
                with open(file_input, 'rb') as audio_file:
                    files = {'file': (os.path.basename(file_input), audio_file)}
                    data = {'model_id': model_id, 'language_code': language}
                    response = requests.post(api_url, headers=headers, files=files, data=data)

            if response.status_code == 200:
                result_json = response.json()
                transcribed_text = result_json.get("text", "（未解析到文本）")
                segments = extract_elevenlabs_segments(result_json.get("words", []))

        # ================== 3. 输出逻辑 ==================
        if response.status_code == 200:
            # 优先从 API 结果中提取实际检测到的语言代码，如果未返回则回退到预设语言
            detected_lang = result_json.get("language_code", result_json.get("language", language))
            
            print(f"✅ 转写成功！(检测语言: {detected_lang})")
            print("-" * 40)
            if show_timestamps and segments:
                for seg in segments[:3]:
                    print(f"[{format_standard_time(seg.get('start', 0))} --> {format_standard_time(seg.get('end', 0))}] {seg.get('text', '')}")
                if len(segments) > 3: print("... (内容已省略，请查看输出文件)")
            else:
                print(transcribed_text[:100] + ("..." if len(transcribed_text) > 100 else ""))
            print("-" * 40)
            
            # 确定最终输出文件的路径
            final_output_file = None
            if output_path:
                # 单文件模式，直接使用用户指定的文件名
                final_output_file = output_path
            elif batch_dir and batch_basename and target_ext is not None:
                # 批量模式：原文件名_语言代码.后缀
                final_output_file = os.path.join(batch_dir, f"{batch_basename}_{detected_lang}{target_ext}")

            # 写入文件
            if final_output_file:
                try:
                    with open(final_output_file, 'w', encoding='utf-8') as f:
                        output_ext = final_output_file.lower()
                        if output_ext.endswith('.json'):
                            json.dump(result_json, f, indent=4, ensure_ascii=False)
                        elif output_ext.endswith('.srt'):
                            for i, seg in enumerate(segments, 1):
                                start_str = format_srt_time(seg.get('start', 0))
                                end_str = format_srt_time(seg.get('end', 0))
                                f.write(f"{i}\n{start_str} --> {end_str}\n{seg.get('text', '').strip()}\n\n")
                        else:
                            if show_timestamps and segments:
                                for seg in segments:
                                    start_str = format_standard_time(seg.get('start', 0))
                                    end_str = format_standard_time(seg.get('end', 0))
                                    f.write(f"[{start_str} --> {end_str}] {seg.get('text', '')}\n")
                            else:
                                f.write(transcribed_text)
                    print(f"📄 已保存至: {final_output_file}")
                except IOError as e:
                    print(f"❌ 保存文件时发生错误: {str(e)}")
            return True
        else:
            print(f"❌ 请求失败，状态码: {response.status_code}")
            print(f"详细信息: {response.text}")
            return False

    except Exception as e:
        print(f"❌ 发生异常: {str(e)}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="调用 302.ai API 将音频转写为文本 (批量模式支持文件名附带语言代码)")
    parser.add_argument("-f", "--file", required=True, help="音频文件路径、URL，或包含音频的【文件夹路径】")
    parser.add_argument("-k", "--key", required=True, help="API 授权密钥")
    parser.add_argument("-m", "--model", default="scribe_v1", help="模型 ID (例如: scribe_v1, whisperx)")
    parser.add_argument("-o", "--output", help="输出文件路径或格式后缀 (如 .srt)。如果是批量目录，会作为后缀生成文件")
    parser.add_argument("-t", "--timestamps", action="store_true", help="启用标准时间戳 [HH:MM:SS.mmm --> HH:MM:SS.mmm]")
    parser.add_argument("-l", "--language", default="zh", help="预设目标语言代码 (默认: zh)")

    args = parser.parse_args()

    input_path = args.file

    # 1. 如果输入的是一个 URL 或者是个独立文件
    if input_path.startswith("http://") or input_path.startswith("https://") or os.path.isfile(input_path):
        process_single_audio(
            input_path, args.key, args.model, 
            output_path=args.output, 
            show_timestamps=args.timestamps, 
            language=args.language
        )

    # 2. 如果输入的是一个目录（批量处理逻辑）
    elif os.path.isdir(input_path):
        print(f"\n📁 检测到目录: {input_path}，开启批量处理模式！")
        
        target_ext = ".txt"
        if args.output:
            _, ext = os.path.splitext(args.output)
            target_ext = ext if ext else f".{args.output.strip('.')}"
        
        success_count = 0
        failed_count = 0
        
        for root, dirs, files in os.walk(input_path):
            for file in files:
                if file.lower().endswith(SUPPORTED_EXTENSIONS):
                    full_path = os.path.join(root, file)
                    base_name = os.path.splitext(file)[0]
                    
                    is_success = process_single_audio(
                        full_path, args.key, args.model, 
                        batch_dir=root,
                        batch_basename=base_name,
                        target_ext=target_ext,
                        show_timestamps=args.timestamps, 
                        language=args.language
                    )
                    
                    if is_success: success_count += 1
                    else: failed_count += 1
                    
        print("\n" + "="*40)
        print(f"🎉 批量任务执行完毕！成功: {success_count} 个，失败: {failed_count} 个。")
        print("="*40)
        
    else:
        print(f"❌ 错误: '{input_path}' 既不是有效的文件或目录，也不是 URL。")
