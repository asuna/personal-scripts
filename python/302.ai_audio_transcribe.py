import argparse
import requests
import os
import json
import glob
import time

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
    """将 ElevenLabs 的词级数据拼装成句子，兼容 audio_event 标签，并提取说话人"""
    segments = []
    if not words: return segments
    start_time = None
    end_time = None
    text_buffer = ""
    current_speaker = None
    
    for w in words:
        w_type = w.get("type")
        # 兼容普通的 word 和异步接口特有的 audio_event (如音效标签)
        if w_type in ("word", "audio_event"):
            if start_time is None:
                start_time = w.get("start", 0)
            end_time = w.get("end", 0)
            if current_speaker is None and w.get("speaker_id") is not None:
                current_speaker = w.get("speaker_id")
                
        text_buffer += w.get("text", "")
        if text_buffer.endswith(('. ', '? ', '! ', '。', '？', '！', ')', '）')):
            segments.append({
                "start": start_time if start_time is not None else 0,
                "end": end_time if end_time is not None else 0,
                "text": text_buffer.strip(),
                "speaker": current_speaker
            })
            start_time = None
            text_buffer = ""
            current_speaker = None
            
    if text_buffer.strip():
        segments.append({
            "start": start_time if start_time is not None else 0,
            "end": end_time if end_time is not None else 0,
            "text": text_buffer.strip(),
            "speaker": current_speaker
        })
    return segments

def format_speaker_text(text, speaker):
    if speaker is not None:
        return f"[{speaker}] {text}"
    return text

def process_single_audio(file_input, api_key, model_id, output_path=None, batch_dir=None, batch_basename=None, target_ext=None, show_timestamps=False, language="zh", diarize=False):
    # ==========================================
    # 提前检查：断点续传逻辑
    # ==========================================
    if output_path:
        if os.path.exists(output_path):
            print(f"\n⏭️ 跳过: {file_input} (目标文件 '{output_path}' 已存在)")
            return "skipped"
    elif batch_dir and batch_basename and target_ext is not None:
        pattern = os.path.join(batch_dir, f"{batch_basename}_{model_id}_*{target_ext}")
        existing_files = glob.glob(pattern)
        if existing_files:
            print(f"\n⏭️ 跳过: {file_input} (已存在输出结果: '{os.path.basename(existing_files[0])}')")
            return "skipped"

    headers = {'Authorization': f'Bearer {api_key}'}
    diarize_msg = "开启" if diarize else "关闭"
    print(f"\n⏳ 正在处理: {file_input} [模型: {model_id}, 语言: {language}, 说话人识别: {diarize_msg}] ...")

    try:
        segments = []
        transcribed_text = ""
        result_json = {}
        request_success = False

        # ================== 1. ElevenLabs (异步提交版本) ==================
        if model_id.lower() == "elevenlabs_async":
            submit_url = "https://api.302.ai/302/submit/elevenlabs/speech-to-text"
            
            # 该接口强制要求 audio_url，如果传入本地文件直接报错
            if not (file_input.startswith("http://") or file_input.startswith("https://")):
                print("❌ 错误: elevenlabs_async 模型当前仅支持 URL 格式传参。请传入以 http/https 开头的线上链接。")
                return False

            payload = {
                "audio_url": file_input,
                "language_code": language,
                "tag_audio_events": True
            }
            if diarize:
                payload["diarize"] = True
            
            headers['Content-Type'] = 'application/json'
            
            # 步骤 A：提交任务
            submit_resp = requests.post(submit_url, headers=headers, json=payload)
            if submit_resp.status_code != 200:
                print(f"❌ 任务提交失败，状态码: {submit_resp.status_code}")
                print(f"详细信息: {submit_resp.text}")
                return False
                
            submit_data = submit_resp.json()
            request_id = submit_data.get("request_id")
            if not request_id:
                print(f"❌ 无法从响应中获取 request_id: {submit_data}")
                return False
                
            print(f"📡 任务已提交，Request ID: {request_id}")
            print("⏳ 正在轮询结果，请耐心等待...")
            
            # 步骤 B：轮询结果
            query_url = f"https://api.302.ai/302/submit/elevenlabs/speech-to-text?request_id={request_id}"
            
            # 去除 Content-Type，GET 请求不需要
            headers.pop('Content-Type', None)
            
            while True:
                poll_resp = requests.get(query_url, headers=headers)
                if poll_resp.status_code == 200:
                    poll_data = poll_resp.json()
                    
                    # 检查是否仍在队列中或处理中
                    if "status" in poll_data and poll_data["status"] in ["IN_QUEUE", "PROCESSING", "PENDING"]:
                        time.sleep(5)  # 每5秒查询一次
                        continue
                        
                    # 检查是否发生错误
                    elif "status" in poll_data and poll_data["status"] in ["FAILED", "ERROR"]:
                        print(f"❌ 异步任务执行失败: {poll_data}")
                        return False
                        
                    # 如果结果中包含了 words 或 text，说明处理完成
                    elif "words" in poll_data or "text" in poll_data:
                        result_json = poll_data
                        segments = extract_elevenlabs_segments(result_json.get("words", []))
                        text_parts = []
                        for seg in segments:
                            spk_text = format_speaker_text(seg.get("text", "").strip(), seg.get("speaker"))
                            text_parts.append(spk_text)
                        transcribed_text = " ".join(text_parts) if text_parts else result_json.get("text", "（未解析到文本）")
                        request_success = True
                        break
                    else:
                        # 兜底：未知的状态，继续等
                        time.sleep(5)
                else:
                    print(f"❌ 轮询请求失败，状态码: {poll_resp.status_code}")
                    return False

        # ================== 2. WhisperX ==================
        elif model_id.lower() == "whisperx":
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
                text_parts = []
                for seg in segments:
                    spk_text = format_speaker_text(seg.get("text", "").strip(), seg.get("speaker"))
                    text_parts.append(spk_text)
                transcribed_text = " ".join(text_parts)
                request_success = True
            else:
                print(f"❌ 请求失败: {response.text}")

        # ================== 3. ElevenLabs (同步版) ==================
        else:
            api_url = "https://api.302.ai/elevenlabs/speech-to-text"
            payload_data = {'model_id': model_id, 'language_code': language}

            if file_input.startswith("http://") or file_input.startswith("https://"):
                headers['Content-Type'] = 'application/json'
                payload_data['file'] = file_input
                response = requests.post(api_url, headers=headers, json=payload_data)
            else:
                with open(file_input, 'rb') as audio_file:
                    files = {'file': (os.path.basename(file_input), audio_file)}
                    response = requests.post(api_url, headers=headers, files=files, data=payload_data)

            if response.status_code == 200:
                result_json = response.json()
                segments = extract_elevenlabs_segments(result_json.get("words", []))
                text_parts = []
                for seg in segments:
                    spk_text = format_speaker_text(seg.get("text", "").strip(), seg.get("speaker"))
                    text_parts.append(spk_text)
                transcribed_text = " ".join(text_parts) if text_parts else result_json.get("text", "（未解析到文本）")
                request_success = True
            else:
                print(f"❌ 请求失败: {response.text}")

        # ================== 统一的文件保存逻辑 ==================
        if request_success:
            detected_lang = result_json.get("language_code", result_json.get("language", language))
            
            print(f"✅ 转写成功！(检测语言: {detected_lang})")
            print("-" * 40)
            if show_timestamps and segments:
                for seg in segments[:5]: # 增加到打印前5条
                    display_text = format_speaker_text(seg.get('text', ''), seg.get('speaker'))
                    print(f"[{format_standard_time(seg.get('start', 0))} --> {format_standard_time(seg.get('end', 0))}] {display_text}")
                if len(segments) > 5: print("... (内容已省略，请查看输出文件)")
            else:
                print(transcribed_text[:100] + ("..." if len(transcribed_text) > 100 else ""))
            print("-" * 40)
            
            final_output_file = None
            if output_path:
                final_output_file = output_path
            elif batch_dir and batch_basename and target_ext is not None:
                final_output_file = os.path.join(batch_dir, f"{batch_basename}_{model_id}_{detected_lang}{target_ext}")

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
                                display_text = format_speaker_text(seg.get('text', '').strip(), seg.get('speaker'))
                                f.write(f"{i}\n{start_str} --> {end_str}\n{display_text}\n\n")
                        else:
                            if show_timestamps and segments:
                                for seg in segments:
                                    start_str = format_standard_time(seg.get('start', 0))
                                    end_str = format_standard_time(seg.get('end', 0))
                                    display_text = format_speaker_text(seg.get('text', ''), seg.get('speaker'))
                                    f.write(f"[{start_str} --> {end_str}] {display_text}\n")
                            else:
                                f.write(transcribed_text)
                    print(f"📄 已保存至: {final_output_file}")
                except IOError as e:
                    print(f"❌ 保存文件时发生错误: {str(e)}")
            return True
        else:
            return False

    except Exception as e:
        print(f"❌ 发生异常: {str(e)}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="调用 302.ai API 将音频转写为文本 (支持同步/异步模型)")
    parser.add_argument("-f", "--file", required=True, help="音频文件路径、URL，或包含音频的【文件夹路径】 (elevenlabs_async仅支持URL)")
    parser.add_argument("-k", "--key", required=True, help="API 授权密钥")
    parser.add_argument("-m", "--model", default="scribe_v1", help="模型 ID (支持: scribe_v1, whisperx, elevenlabs_async)")
    parser.add_argument("-o", "--output", help="输出文件路径或格式后缀 (如 .srt)")
    parser.add_argument("-t", "--timestamps", action="store_true", help="启用标准时间戳")
    parser.add_argument("-l", "--language", default="zh", help="预设目标语言代码 (默认: zh)")
    parser.add_argument("-d", "--diarize", action="store_true", help="尝试开启或提取说话人识别")

    args = parser.parse_args()

    input_path = args.file

    if input_path.startswith("http://") or input_path.startswith("https://") or os.path.isfile(input_path):
        process_single_audio(
            input_path, args.key, args.model, 
            output_path=args.output, 
            show_timestamps=args.timestamps, 
            language=args.language,
            diarize=args.diarize
        )
    elif os.path.isdir(input_path):
        print(f"\n📁 检测到目录: {input_path}，开启批量处理模式！")
        
        target_ext = ".txt"
        if args.output:
            _, ext = os.path.splitext(args.output)
            target_ext = ext if ext else f".{args.output.strip('.')}"
        
        success_count = 0
        failed_count = 0
        skipped_count = 0
        
        for root, dirs, files in os.walk(input_path):
            for file in files:
                if file.lower().endswith(SUPPORTED_EXTENSIONS):
                    full_path = os.path.join(root, file)
                    base_name = os.path.splitext(file)[0]
                    
                    status = process_single_audio(
                        full_path, args.key, args.model, 
                        batch_dir=root,
                        batch_basename=base_name,
                        target_ext=target_ext,
                        show_timestamps=args.timestamps, 
                        language=args.language,
                        diarize=args.diarize
                    )
                    
                    if status == "skipped":
                        skipped_count += 1
                    elif status is True: 
                        success_count += 1
                    else: 
                        failed_count += 1
                    
        print("\n" + "="*45)
        print(f"🎉 批量任务执行完毕！")
        print(f"✅ 成功: {success_count} 个")
        print(f"⏭️ 跳过: {skipped_count} 个")
        print(f"❌ 失败: {failed_count} 个")
        print("="*45)
        
    else:
        print(f"❌ 错误: '{input_path}' 既不是有效的文件或目录，也不是 URL。")
