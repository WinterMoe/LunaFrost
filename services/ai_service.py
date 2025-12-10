import json
import re
import requests
import html
from collections import Counter

def clean_korean_text(text):

    text = re.sub(r'[A-Za-z0-9+/]{40,}={0,2}', '', text)
    text = html.unescape(text)
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        cleaned = ' '.join(line.split())
        cleaned_lines.append(cleaned)
    text = '\n'.join(cleaned_lines)
    text = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F-\x9F]', '', text)
    return text

def extract_translation_text(result):

    if isinstance(result, dict):
        if result.get('error'):
            return None, result.get('error'), None
        return result.get('translated_text'), None, result.get('token_usage')
    elif isinstance(result, str):
        if result.startswith("Error") or any(result.startswith(p) for p in ["OpenRouter", "OpenAI", "Google"]):
            return None, result, None
        return result, None, None
    return None, "Unknown result format", None

def translate_text(text, provider, api_key, selected_model, glossary=None, images=None, is_thinking_mode=False, source_language=None, custom_prompt_suffix=None):

    if not api_key:
        return {'error': 'API key not configured.', 'translated_text': None, 'token_usage': None}
    
    try:
        text = clean_korean_text(text)
        
        glossary_instructions = ""
        if glossary and len(glossary) > 0:
            glossary_instructions = "\n\nCHARACTER GLOSSARY - Use these EXACT translations:\n"
            for char_id, char_info in glossary.items():
                korean_name = char_info.get('korean_name', '')
                english_name = char_info.get('english_name', '')
                gender = char_info.get('gender', '')
                
                glossary_instructions += f"\n- {korean_name} → {english_name}"
                
                if gender == 'male':
                    glossary_instructions += " (Use he/him pronouns)"
                elif gender == 'female':
                    glossary_instructions += " (Use she/her pronouns)"
                elif gender == 'other':
                    glossary_instructions += " (Use they/them pronouns)"
                elif gender == 'auto':
                    glossary_instructions += " (Determine appropriate pronouns from context)"
                
        
        image_context = ""
        if images and len(images) > 0:
            image_context = "\n\nNote: This chapter contains images at the following positions:\n"
            for img in images:
                image_context += f"[IMAGE_{img.get('index', 0)}] - {img.get('alt', 'Image')}\n"
        
        system_prompt = """
You are a professional Korean-to-English literary translator specializing in web novels. 
Your goal is to produce natural, fluent English that faithfully reflects the tone, personality, and style of the original Korean text.

-------------------------------
CRITICAL FORMATTING RULES
-------------------------------
1. Preserve ALL line breaks EXACTLY as they appear in the original Korean text.  
2. Each paragraph separation (double newline) must be maintained.  
3. Single line breaks within paragraphs must be preserved.  
4. Do NOT add or remove any line breaks.  
5. Maintain the same number of blank lines between paragraphs.  
6. Translate naturally but keep the original paragraph and sentence structure intact.  
7. Do NOT include encoded strings, metadata, tags, or system text.  
8. Only output readable English text.  

-------------------------------
CHARACTER CONSISTENCY
-------------------------------
- If a character glossary is provided, you MUST use those exact names.  
- If pronouns (he/him, she/her, they/them) are specified, apply them consistently.  
- For characters marked "AI Auto-select," determine pronouns contextually based on tone and narrative cues.  
- Maintain consistent naming and pronoun choices throughout the story.  
- Never alter character names, ranks, or titles.  

-------------------------------
KOREAN→ENGLISH TRANSLATION STYLE GUIDE
-------------------------------
1. **Tone and Register**
   - Accurately reflect Korean honorifics, formality, and speech hierarchy in natural English.
   - Avoid overly literal translations of politeness levels; instead, express them through tone, diction, or context.
   - Preserve the emotional tone of dialogue (e.g., playful, formal, awkward, deferential, cold, etc.).

2. **Cultural and Linguistic Nuance**
   - For these specific relationship terms, romanize instead of translating:
     - 오빠 → "oppa", 언니 → "unnie", 형 → "hyung", 누나 → "noona", 선배 → "sunbae"
   - All OTHER Korean terms should be translated to their English meaning (e.g., 아저씨 → "mister/uncle", 사장님 → "boss", 괜찮다 → "it's okay")
   - CRITICAL: The output must contain ZERO Korean characters (한글). Every single Korean word must be either romanized or translated.
   - Preserve the spirit of idioms and proverbs using equivalent English expressions.

3. **Internal Monologue and Dialogue**
   - Clearly differentiate between spoken dialogue, thoughts, and narration.
   - Inner monologues should sound natural in English while preserving the Korean tone (e.g., self-deprecating, ironic, etc.).
   - Avoid robotic or overly formal phrasing.

4. **Terminology and Worldbuilding**
   - For fantasy or system-based novels, maintain consistent translation of recurring terms (skills, titles, items, etc.).
   - Use capitalization for system messages or interface terms if the original does (e.g., "Quest Completed", "Dungeon Gate").

5. **Faithfulness and Flow**
   - Translate meaning, not word order — prioritize readability and emotional accuracy.
   - Do not embellish or censor content; keep to the author's tone.
   - Do NOT soften profanity, insults, or expletives. Preserve coarse language with equivalent or stronger intensity in natural English when context calls for it (e.g., "개새끼" → "son of a bitch"/"bastard" based on tone).
   - When nuance is ambiguous, default to the interpretation most consistent with prior context.

-------------------------------
QUALITY CONTROL
-------------------------------
- Double-check that each translated section preserves the **same paragraphing, line breaks, and structure** as the Korean text.  
- Eliminate mistranslations, missing lines, or formatting drift.  
- Ensure smooth, fluent English that reads like a professionally published web novel translation.

-------------------------------
OUTPUT RULES
-------------------------------
- Output only the translated English text.  
- Do NOT include explanations, metadata, or internal notes.  
- Maintain all formatting rules exactly.

{custom_prompt_suffix if custom_prompt_suffix else ""}
"""

        user_prompt = f"""CRITICAL INSTRUCTIONS:
1. Preserve ALL line breaks and paragraph spacing EXACTLY as in the original
2. Keep the same number of blank lines between paragraphs
3. Maintain the exact formatting structure
4. Preserve any [IMAGE_X] markers in their exact positions
5. Do not add or remove any line breaks
6. Translate the content naturally while keeping the original structure
7. IGNORE any encoded strings or metadata - only translate readable text
8. Output ONLY readable English text, no encoded content

{glossary_instructions}

{image_context}

Korean text:
{text}"""

        headers = {"Content-Type": "application/json"}
        json_payload = {}
        
        # Roughly size the output limit to the input so long chapters don't get truncated.
        # Tokens ~= chars/3; add a buffer and cap to 64k (provider/model limits should still enforce tighter caps if needed).
        approx_tokens = max(1000, int(len(text) / 3))
        if is_thinking_mode:
            max_tokens = min(64000, approx_tokens + 8000)
        else:
            max_tokens = min(64000, max(4000, approx_tokens + 4000))
        
        def detect_source_lang(text_value, source_lang_hint):
                                                                             
            if source_lang_hint:
                lower = source_lang_hint.lower()
                if 'korean' in lower or lower == 'ko':
                    return 'KO'
                if 'japanese' in lower or 'japan' in lower or lower == 'ja':
                    return 'JA'
                                            
            if re.search(r'[\uac00-\ud7a3]', text_value):
                return 'KO'
            if re.search(r'[\u3040-\u30ff\u31f0-\u31ff]', text_value):
                return 'JA'
            return None

        def normalize_korean_spacing(text_value: str) -> str:
                                                                                          
            particles = [
                '은', '는', '이', '가', '을', '를', '에', '에서', '으로', '로',
                '와', '과', '도', '만', '까지', '부터', '에게', '한테', '보다',
                '라도', '라고', '로서', '처럼', '같이', '뿐', '으로부터', '에게서', '의'
            ]
            pattern = r'([\uac00-\ud7a3])\s+(' + '|'.join(particles) + r')'
            return re.sub(pattern, r'\1\2', text_value)

        def normalize_korean_informal(text_value: str) -> str:
                                                                                        
            replacements = {
                'ㅇㅇ': '응',
                'ㅇㅋ': '응',
                'ㅇㅇㅋ': '응',
                'ㅇㅈ': '인정',
                'ㄴㄴ': '아니',
                'ㅇㄱㄹㅇ': '이거 레알',
            }
            for src, dst in replacements.items():
                text_value = text_value.replace(src, dst)
                                      
            text_value = re.sub(r'\s{2,}', ' ', text_value).strip()
            return text_value

        if provider == 'deepl':
                                                                      
            url = "https://api.deepl.com/v2/translate"
                                                               
            if api_key and api_key.strip().endswith(':fx'):
                url = "https://api-free.deepl.com/v2/translate"
            headers = {
                "Authorization": f"DeepL-Auth-Key {api_key}"
            }
            text_for_deepl = normalize_korean_informal(text)
            deepl_source_lang = detect_source_lang(text, source_language)
            if deepl_source_lang == 'KO':
                text_for_deepl = normalize_korean_spacing(text_for_deepl)
            data_payload = {
                "text": text_for_deepl,
                "target_lang": "EN",
            }
            if deepl_source_lang:
                data_payload["source_lang"] = deepl_source_lang
                                                                
            data_payload["split_sentences"] = 1
            data_payload["preserve_formatting"] = 0
            response = requests.post(url, headers=headers, data=data_payload)
        
        elif provider == 'openrouter':
            headers["Authorization"] = f"Bearer {api_key}"
            headers["HTTP-Referer"] = "http://localhost:5000"
            headers["X-Title"] = "Novel Translator"
            json_payload = {
                "model": selected_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.3,
                "max_tokens": max_tokens
            }
            response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=json_payload)
        
        elif provider == 'openai':
            headers["Authorization"] = f"Bearer {api_key}"
            
            token_param = "max_completion_tokens" if "o1-" in selected_model else "max_tokens"
            
            json_payload = {
                "model": selected_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 1 if "o1-" in selected_model else 0.3,                
            }
            json_payload[token_param] = max_tokens
            
            response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=json_payload)
        
        elif provider == 'google':
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{selected_model}:generateContent?key={api_key}"
            json_payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": f"{system_prompt}\n\n{user_prompt}"}
                        ]
                    }
                ],
                "generationConfig": {
                    "maxOutputTokens": max_tokens,
                    "temperature": 0.3
                }
            }
            response = requests.post(url, headers=headers, json=json_payload)
        
        else:
            return {'error': 'Unsupported provider. Please use OpenRouter, OpenAI, Google Gemini, or DeepL.', 'translated_text': None, 'token_usage': None}
        
        if response.status_code == 200:
            data = response.json()
            
            token_usage = None
            if provider == 'deepl':
                translations = data.get('translations', [])
                if translations:
                    translated_text = translations[0].get('text', '')
                else:
                    return {'error': 'DeepL API Error: No translations in response.', 'translated_text': None, 'token_usage': None}
            elif provider == 'google':
                candidates = data.get('candidates', [])
                if candidates:
                    content = candidates[0].get('content', {})
                    parts = content.get('parts', [])
                    if parts:
                        translated_text = parts[0].get('text', '')
                    else:
                        return {'error': 'Google API Error: No content in response.', 'translated_text': None, 'token_usage': None}
                else:
                    return {'error': 'Google API Error: No candidates in response.', 'translated_text': None, 'token_usage': None}
                
                usage_metadata = data.get('usageMetadata', {})
                if usage_metadata:
                    token_usage = {
                        'input_tokens': usage_metadata.get('promptTokenCount', 0),
                        'output_tokens': usage_metadata.get('candidatesTokenCount', 0),
                        'total_tokens': usage_metadata.get('totalTokenCount', 0),
                        'provider': provider,
                        'model': selected_model
                    }
            else:
                choices = data.get('choices', [])
                if choices:
                    translated_text = choices[0].get('message', {}).get('content', '')
                else:
                    return {'error': f'{provider.capitalize()} API Error: No choices in response.', 'translated_text': None, 'token_usage': None}
                
                usage = data.get('usage', {})
                if usage:
                    token_usage = {
                        'input_tokens': usage.get('prompt_tokens', 0),
                        'output_tokens': usage.get('completion_tokens', 0),
                        'total_tokens': usage.get('total_tokens', 0),
                        'provider': provider,
                        'model': selected_model
                    }
            
            translated_text = re.sub(r'[A-Za-z0-9+/]{40,}={0,2}', '[corrupted data removed]', translated_text)
            
            return {
                'translated_text': translated_text,
                'token_usage': token_usage,
                'error': None
            }
        else:
            error_msg = f"{provider.capitalize()} API Error: {response.status_code}"
            try:
                error_data = response.json()
                error_msg += f" - {error_data.get('error', {}).get('message', 'Unknown error')}"
            except:
                pass
            return {'error': error_msg, 'translated_text': None, 'token_usage': None}
            
    except Exception as e:
        return {'error': f'{provider.capitalize()} error: {str(e)}', 'translated_text': None, 'token_usage': None}

def detect_characters(text, provider, api_key, selected_model):

    if not api_key:
        return {'error': 'API key not configured'}
    
    try:
                                               
        sample_text = text[:8000] if len(text) > 8000 else text
        
        system_prompt = """You are a Korean web novel character name extraction expert.
Your task is to identify ALL character names mentioned in the Korean text.

CRITICAL: Only extract PERSONAL NAMES of characters, not common nouns or objects.

✅ EXTRACT (Character Names):
- Full Korean names: 김철수, 이영희, 박민수, 서해은 (VERY IMPORTANT - include even if appears only once!)
- Single names: 철수, 영희, 민수, 해은
- Names with titles: 김 사장님, 박 대표님
- Family terms when referring to specific characters: 아버지, 어머니 (if they refer to a specific person, not general)
- Titles used as names for specific people: 선배, 오빠, 형, 언니, 누나 (only if consistently used for one character)

SPECIAL ATTENTION TO FULL NAMES:
- Full names (surname + given name like 서해은) often appear ONLY ONCE at character introduction
- Even if a full name appears just 1 time, INCLUDE IT if it looks like a character name
- The given name alone (해은) may appear many times after the initial full name introduction
- ALWAYS include full names even with single occurrence if they have surname + given name structure

❌ DO NOT EXTRACT (Common Words):
- Abstract nouns: 힘 (power), 능력 (ability), 마법 (magic)
- Quest/game terms: 임무 (mission), 퀘스트 (quest), 던전 (dungeon), 몬스터 (monster)
- Common objects: 검 (sword), 방패 (shield), 물약 (potion)
- Actions: 공격 (attack), 방어 (defense), 전투 (battle)
- Status words: 레벨 (level), 스킬 (skill), 능력치 (stats)
- Time/place: 시간 (time), 장소 (place), 세상 (world)
- Generic titles: 대표 (CEO), 사장 (president), 부장 (manager) - unless part of a name
- Emotions: 기분 (mood), 생각 (thought), 마음 (heart)

STRICT RULES:
1. ALWAYS extract full names (김철수, 서해은) even if they appear only once
2. Extract both full names (김철수) and single names (철수) if both appear
3. Only extract words that clearly refer to specific individuals
4. If unsure whether something is a name or common word, SKIP it
5. Return as a JSON array of unique Korean names
6. Focus on all character names - full names are especially important!
7. Do NOT include quest terms, game mechanics, or abstract concepts

Return ONLY character names that would have English equivalents like "John Kim" or "Sarah Lee"."""

        user_prompt = f"""Analyze this Korean novel chapter and extract ALL character names.

Return ONLY a valid JSON array like this:
["김철수", "철수", "이영희", "영희", "박민수"]

Korean text:
{sample_text}"""

        headers = {"Content-Type": "application/json"}
        json_payload = {
            "model": selected_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 1000
        }
        
        if provider == 'openrouter':
            headers["Authorization"] = f"Bearer {api_key}"
            headers["HTTP-Referer"] = "http://localhost:5000"
            headers["X-Title"] = "Novel Translator"
            response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=json_payload)
        
        elif provider == 'openai':
            headers["Authorization"] = f"Bearer {api_key}"
            response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=json_payload)
        
        elif provider == 'google':
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{selected_model}:generateContent?key={api_key}"
            json_payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": f"{system_prompt}\n\n{user_prompt}"}
                        ]
                    }
                ]
            }
            response = requests.post(url, headers=headers, json=json_payload)
        
        else:
            return {'error': 'Unsupported provider. Please use OpenRouter, OpenAI, or Google Gemini.'}
        
        if response.status_code == 200:
            data = response.json()
            
            if provider == 'google':
                candidates = data.get('candidates', [])
                if candidates:
                    content = candidates[0].get('content', {})
                    parts = content.get('parts', [])
                    if parts:
                        content_str = parts[0].get('text', '')
                    else:
                        return {'error': 'Google API: No content.'}
                else:
                    return {'error': 'Google API: No candidates.'}
            else:
                choices = data.get('choices', [])
                if choices:
                    content_str = choices[0].get('message', {}).get('content', '')
                else:
                    return {'error': f'{provider.capitalize()} API: No choices.'}
            
            try:
                if '```json' in content_str:
                    content_str = content_str.split('```json')[1].split('```')[0].strip()
                elif '```' in content_str:
                    content_str = content_str.split('```')[1].split('```')[0].strip()
                
                characters = json.loads(content_str)
                return {'success': True, 'characters': characters}
            except json.JSONDecodeError:
                return {'error': 'Failed to parse AI response'}
        else:
            return {'error': f'{provider.capitalize()} API Error: {response.status_code}'}
            
    except Exception as e:
        return {'error': str(e)}

def detect_full_korean_names(text):
    detected_full_names = set()
    surnames = get_korean_surnames()
    
    full_name_patterns = [
        r'([' + ''.join(surnames) + r'][가-힣]{2})',
        r'([' + ''.join(surnames) + r'][가-힣]{3})',
    ]
    
    for pattern in full_name_patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            if len(match) >= 3 and len(match) <= 5:
                if match[0] in surnames or match[:2] in surnames:
                    blacklist = get_korean_common_words_blacklist()
                    if match not in blacklist:
                        if check_name_context(match, text) or text.count(match) >= 1:
                            detected_full_names.add(match)
    
    return detected_full_names


def link_full_and_short_names(full_names, short_names, text):
    linked_names = {}
    surnames = get_korean_surnames()
    
    for full_name in full_names:
        if len(full_name) >= 3:
            if full_name[0] in surnames:
                given_name_2char = full_name[-2:]
                given_name_3char = full_name[-3:] if len(full_name) >= 4 else None
                
                if given_name_2char in short_names:
                    linked_names[full_name] = given_name_2char
                elif given_name_3char and given_name_3char in short_names:
                    linked_names[full_name] = given_name_3char
            
            elif len(full_name) >= 4 and full_name[:2] in surnames:
                given_name_2char = full_name[-2:]
                given_name_3char = full_name[-3:] if len(full_name) >= 5 else None
                
                if given_name_2char in short_names:
                    linked_names[full_name] = given_name_2char
                elif given_name_3char and given_name_3char in short_names:
                    linked_names[full_name] = given_name_3char
    
    return linked_names

def get_korean_common_words_blacklist():

    return {
                      
        '사람', '것', '때', '곳', '수', '말', '생각', '마음', '얼굴', '손', '눈', '귀', 
        '코', '입', '머리', '다리', '발', '몸', '세상', '나라', '집', '방', '문', '창문',
        '하늘', '땅', '바다', '산', '강', '물', '불', '바람', '공기', '햇빛', '달빛',
        '아침', '저녁', '밤', '낮', '시간', '분', '초', '날', '주', '달', '년',
        
                                        
        '소녀', '소년', '남자', '여자', '아이', '어린이', '청년', '중년', '노인',
        '할아버지', '할머니', '아버지', '어머니', '아빠', '엄마', '형', '누나', '언니', '오빠',
        '형제', '자매', '동생', '아들', '딸', '손자', '손녀', '부모', '자식',
        '아저씨', '아줌마', '꼬마', '녀석', '자식', '놈', '년', '애',
        '사장님', '부장님', '과장님', '대리님', '선생님', '교수님', '선배님', '사모님',
        '괜찮다', '괜찮아', '알겠다', '알겠어', '그렇다', '그래', '응', '네', '예',
        '싫다', '좋다', '나쁘다', '맞다', '틀리다', '모르다', '알다', '보다', '듣다',
        
                                    
        '일', '행동', '움직임', '시작', '끝', '과정', '결과', '원인', '이유', '목적',
        '방법', '수단', '도구', '무기', '장비', '아이템', '물건', '물품', '재료',
        
                             
        '발차기', '주먹', '공격', '방어', '회피', '반격', '돌진', '도약', '점프',
        '타격', '베기', '찌르기', '던지기', '막기', '튕겨내기', '피하기',
        '피해', '데미지', '위력', '충격', '폭발', '파괴', '살상', '치명타',
        
                      
        '마법', '주문', '마나', '기술', '스킬', '능력', '특성', '재능', '천재',
        '결계', '결계술', '봉인', '소환', '변신', '치유', '회복', '강화', '약화',
        '마력', '영력', '기력', '정신력', '체력', '생명력',
        
                           
        '힘', '능력', '기술', '레벨', '경험', '지식', '정보', '소식',
        '소문', '이야기', '전설', '역사', '미래', '과거', '현재', '순간', '영원',
        '진실', '거짓', '비밀', '약속', '계약', '규칙', '법', '명령', '금지',
        
                         
        '기분', '감정', '느낌', '분위기', '상황', '상태', '조건', '환경', '모습',
        '표정', '태도', '행동', '말투', '목소리', '소리', '침묵', '고요',
        '분노', '슬픔', '기쁨', '두려움', '공포', '놀라움', '혼란', '당황',
        
                                        
        '하지만', '그러나', '그래서', '그런데', '어쨌든', '아무튼', '그리고', '또한',
        '게다가', '그렇지만', '그러므로', '따라서', '왜냐하면', '만약',
        
                                 
        '이것', '그것', '저것', '무엇', '누구', '어디', '언제', '어떻게', '왜',
        '여기', '거기', '저기', '이곳', '그곳', '저곳', '어느', '모든', '각각',
        '아무', '아무도', '아무것', '아무데', '아무때', '누군가', '무언가', '어딘가',
        
                                 
        '임무', '퀘스트', '미션', '목표', '보상', '경험치', '골드', '아이템', '장비',
        '던전', '몬스터', '보스', '길드', '파티', '팀', '그룹', '동료', '적',
        '전투', '싸움', '방어', '회복', '버프', '디버프', '스탯', '능력치',
        '인벤토리', '상점', '상인', '거래', '교환', '구매', '판매',
        
                                    
        '대표', '사장', '부장', '과장', '대리', '사원', '회장', '이사', '팀장',
        '선배', '후배', '동기', '상사', '부하', '직원', '친구', '적',
        '마왕', '용사', '영웅', '전사', '마법사', '궁수', '도적', '암살자',
        '성직자', '사제', '기사', '검사', '검객', '무사',
        
                                
        '가족', '부모', '자식', '형제', '자매', '친척', '조상', '후손',
        
                          
        '장소', '위치', '지역', '마을', '도시', '왕국', '제국', '세계', '차원',
        '공간', '영역', '구역', '층', '건물', '시설', '기관', '조직', '단체',
        '학교', '회사', '병원', '은행', '상점', '시장', '광장', '공원',
        
                                
        '알림', '메시지', '시스템', '상태창', '인벤토리', '정보창', '확인', '취소',
        '선택', '결정', '저장', '불러오기', '진행', '완료', '실패', '성공',
        
                                              
        '하나', '둘', '셋', '넷', '다섯', '여섯', '일곱', '여덟', '아홉', '열',
        
                                        
        '좋음', '나쁨', '큼', '작음', '많음', '적음', '빠름', '느림', '강함', '약함',
        '밝음', '어둠', '뜨거움', '차가움', '높음', '낮음', '길음', '짧음',
        
                                    
        '문제', '답', '질문', '의문', '예상', '예측', '계획', '준비', '연습', '훈련',
        '이름', '제목', '설명', '내용', '부분', '전체', '일부', '나머지', '전부',
        '아무것', '모두', '모든것', '하나',
        '그저', '단지', '오직', '단순', '복잡', '간단', '어려움', '쉬움',
        
                                              
        '가슴', '배', '등', '어깨', '팔', '무릎', '허리', '목', '이마', '뺨', '턱',
        
                                                           
        '모두', '전부', '이미', '아직', '벌써', '이제', '지금', '방금', '곧', '즉시',
        '항상', '절대', '결코', '결국', '과연', '정말', '진짜', '확실', '분명',
        
                                               
        '검', '칼', '도', '창', '활', '화살', '방패', '갑옷', '투구', '장갑', '신발',
        '무기', '방어구', '장비', '도구', '물약', '포션', '엘릭서',
        
                                     
        '불', '물', '바람', '땅', '번개', '얼음', '빛', '어둠', '독', '성', '악',
        
                                                                         
        '것들', '사람들', '아이들', '때문', '덕분', '탓',
        
                                                                                     
        '걱정', '등장', '자세', '미소', '나누', '얼굴', '시선', '표정', '목소리',
        '생각', '행동', '움직임', '반응', '태도', '눈빛', '미간', '입술',
        '손길', '발걸음', '숨결', '한숨', '웃음', '울음', '비명', '말투',
        '분위기', '기운', '느낌', '인기', '명성', '평판', '악명',
        '의지', '결의', '각오', '마음가짐', '심정', '기억', '추억',
        
                                                    
        '시작', '끝', '마무리', '중단', '정지', '계속', '지속', '반복',
        '확인', '점검', '검사', '조사', '탐색', '발견', '찾기',
        '이동', '추적', '도망', '회피', '방어', '반격',
        
                                                                
        '그래', '아니', '네', '예', '응', '어', '음', '흠', '엉',
        '와', '우와', '헉', '어머', '이런', '저런', '그럼', '물론',
        '당연', '확실', '정확', '분명', '역시', '과연', '설마', '혹시',
        '그냥', '그저', '단지', '오직', '이미', '벌써', '아직', '이제',
        '곧', '즉시', '바로', '금방', '잠시', '잠깐', '조금', '많이',
        
                                                   
        '가문', '재능', '권력', '방침', '역할', '환경', '가르침', '폭력',
        '겉모습', '판단', '진심', '특별', '대우', '성향', '비교', '영향',
        '자산', '총액', '이유', '세월', '도리', '차별', '여자', '업적',
        '형태', '심성', '수단', '사욕', '악행', '정의', '학대', '사상',
        '혈통', '평가', '경향', '상층부', '보수', '개혁', '우두머리',
        '사회', '부패', '자정', '작용', '소감', '의욕', '부응', '의식',
        '결과', '소식', '격려', '안전', '장치', '고위', '간부', '댓글',
        '추천', '기대', '소유자', '축복', '부담', '만남', '응석', '받이',
        
                                                            
                                 
        '상대', '자신', '그녀', '자네', '상대방', '녀석',
                      
        '학생들', '대화', '무리', '신경', '페인트',
                                              
        '학장', '당주',
                                
        '최강', '최고',
                                                     
        '학년', '주령', '주술', '술식',
                                        
        '피하고', '다니',
    }

def get_korean_surnames():

    return {
                                                        
        '김', '이', '박', '최', '정', '강', '조', '윤', '장', '임',
        
                                                          
        '한', '오', '서', '신', '권', '황', '안', '송', '전', '홍',
        '유', '고', '문', '양', '손', '배', '조', '백', '허', '남',
        '심', '노', '하', '곽', '성', '차', '주', '우', '구', '라',
        '진', '류', '전', '민', '엄', '방', '원', '천', '공', '소',
        
                                                     
        '석', '선', '설', '마', '변', '여', '추', '노', '도', '은',
        '소', '봉', '팽', '탁', '지', '피', '옥', '목', '엽', '감',
        '호', '연', '염', '제', '갈', '단', '가', '복', '태', '명',
        '예', '경', '음', '용', '국', '흥', '간', '상', '증', '탄',
        
                                   
        '왕', '황보', '선우', '독고', '제갈', '남궁', '사공', '황보',
    }

def is_valid_korean_name(word):

    if not word or len(word) < 2 or len(word) > 4:
        return False
    
    surnames = get_korean_surnames()
    
                                        
    first_char = word[0]
    if first_char not in surnames:
        return False
    
                                                                          
    if len(word) == 2:
        return True
    
                                                                         
    if len(word) == 3:
        return True
    
                                                                   
                                                   
    first_two = word[:2]
    if first_two in surnames:
        return True
    
                                                  
    return False

def check_name_context(word, text):

    import re
    
                                                                
    common_word_patterns = [
        f'{word}하다',                    
        f'{word}했다',                   
        f'{word}하고',              
        f'{word}하는',              
        f'{word}을 짓다',                             
        f'{word}를 짓다',  
        f'{word}히',                                   
        f'{word}스럽',                    
        f'{word}되다',                 
        f'{word}시키다',             
    ]
    
    for pattern in common_word_patterns:
        if pattern in text:
            return False                                
    
                                                             
    name_patterns = [
        f'{word}가 말했다',
        f'{word}는 말했다',
        f'{word}이 말했다',
        f'{word}가 물었다',
        f'{word}가 대답했다',
        f'{word}의 ',              
        f'"{word}"',          
        f"'{word}'",          
        f'{word}님',             
        f'{word}씨',             
    ]
    
    for pattern in name_patterns:
        if pattern in text:
            return True                         
    
                                                           
    return False

def pattern_match_names(text):

    detected_names = set()
    blacklist = get_korean_common_words_blacklist()
    
                          
    patterns = [
                                                                
        r'([가-힣]{2,4})(이|가|은|는|을|를|와|과|의|에게|한테|도)\s',
        
                                                
        r'([가-힣]{2,4})(님|씨|양|군|선생|선생님)',
        
                                  
        r'"([가-힣]{2,4})"',
        r'\'([가-힣]{2,4})\'',
        
                                              
        r'([가-힣]{2,4})(가 말했다|는 말했다|이 말했다|가 물었다|는 물었다|이 물었다|가 대답했다)',
        
                          
        r'([가-힣]{2,4})(의)',
        
                                            
        r'([가-힣]{2,4})(야|아)[,\s]',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            name = match[0] if isinstance(match, tuple) else match
                                                   
            if len(name) >= 2 and name not in blacklist:
                detected_names.add(name)
    
    return detected_names

def is_likely_common_word(word):

    if not word or len(word) < 2:
        return True
    
                                                                    
    common_noun_endings = [
        '술', '법', '력', '치', '값', '량', '금', '비', '식', '물',                          
        '기', '차기', '하기', '던지기',                   
        '음', '움',                 
        '도', '과',                
    ]
    
    for ending in common_noun_endings:
        if word.endswith(ending) and len(word) > len(ending):
            return True
    
                                                                            
                                             
    compound_patterns = [
        '결계',             
        '마법',                                 
        '능력',            
        '공격',            
        '방어',            
        '회복',            
        '강화',            
        '스킬',                    
        '레벨',                    
    ]
    
    for pattern in compound_patterns:
        if pattern in word:
            return True
    
                                                                                    
                                             
    if len(word) >= 4:
                                      
        mid = len(word) // 2
        if word[:mid] == word[mid:] and not is_name_like_repetition(word):
            return True
    
    return False

def is_name_like_repetition(word):

    if len(word) == 4:
                                                  
        first_half = word[:2]
        second_half = word[2:]
        if first_half == second_half:
                                                                        
            return True
    return False
       
    return name1 in name2 or name2 in name1

def is_substring_name(name1, name2):

    return name1 in name2 or name2 in name1

def deduplicate_names(names, text):
    
    if not names:
        return []
    
    blacklist = get_korean_common_words_blacklist()
    
    filtered_names = set()
    for name in names:
        if name in blacklist:
            continue
        
        if len(name) < 2:
            continue
        
        if is_likely_common_word(name):
            continue
        
        filtered_names.add(name)
    
    names = filtered_names
    
    name_counts = Counter()
    for name in names:
        count = text.count(name)
        if count > 0:
            name_counts[name] = count
    
    full_names = detect_full_korean_names(text)
    
    for full_name in full_names:
        if full_name not in name_counts:
            name_counts[full_name] = text.count(full_name)
    
    frequent_names = {}
    for name, count in name_counts.items():
        surnames = get_korean_surnames()
        is_full_name = (len(name) >= 3 and len(name) <= 5 and 
                       (name[0] in surnames or name[:2] in surnames))
        
        if count >= 2 or (is_full_name and count >= 1):
            frequent_names[name] = count
    
    short_names = {name for name in frequent_names.keys() if len(name) == 2}
    full_to_short = link_full_and_short_names(full_names, short_names, text)
    
    name_groups = {}
    processed = set()
    
    for name1 in sorted(frequent_names.keys(), key=len, reverse=True):
        if name1 in processed:
            continue
        
        if name1 in full_to_short:
            short_name = full_to_short[name1]
            group = [name1, short_name]
            name_groups[name1] = group
            processed.update(group)
            continue
        
        group = [name1]
        for name2 in frequent_names.keys():
            if name2 != name1 and name2 not in processed:
                if is_substring_name(name1, name2):
                    group.append(name2)
        
        if len(group) > 1:
            group.sort(key=lambda n: (len(n), frequent_names[n]), reverse=True)
            longer_name = group[0]
            shorter_names = group[1:]
            
            keep_names = [longer_name]
            
            for shorter in shorter_names:
                if frequent_names[shorter] > frequent_names[longer_name] * 2:
                    keep_names.append(shorter)
            
            name_groups[longer_name] = keep_names
            processed.update(group)
        else:
            name_groups[name1] = [name1]
            processed.add(name1)
    
    final_names = []
    for group in name_groups.values():
        final_names.extend(group)
    
    final_names.sort(key=lambda n: frequent_names.get(n, 0), reverse=True)
    
    return final_names

def is_onomatopoeia_or_interjection(word):
    word_lower = word.lower()
    
    if len(word_lower) >= 4:
        half = len(word_lower) // 2
        if word_lower[:half] == word_lower[half:half*2]:
            return True
    
    if len(word_lower) == 4 and word_lower[0] == word_lower[2] and word_lower[1] == word_lower[3]:
        return True
    
    laugh_sounds = ['heh', 'hah', 'hih', 'hoh', 'huh', 'hee', 'hoo', 
                    'kek', 'kuk', 'kik', 'lol', 'lel', 'lul', 'keh', 'gah']
    for sound in laugh_sounds:
        if word_lower.startswith(sound) and len(word_lower) <= 6:
            return True
    
    if len(set(word_lower)) <= 2 and len(word_lower) >= 3:
        return True
    
    interjections = ['pfft', 'tsk', 'tch', 'ugh', 'argh', 'ooh', 'aah', 
                     'eek', 'yay', 'nah', 'shh', 'ssh', 'psst', 'aww', 
                     'oww', 'ouch', 'yikes', 'geez', 'gosh', 'dang',
                     'hmph', 'bah', 'pah', 'gah', 'ack', 'oof',
                     'whew', 'phew', 'ow']
    if word_lower in interjections:
        return True
    
    if len(word_lower) >= 3:
        unique_chars = set(word_lower[1:])
        if len(unique_chars) == 1:
            return True
        
    return False


def is_generic_title_usage(word, text):
    title_words = ['manager', 'director', 'ceo', 'president', 'boss', 
                   'chief', 'head', 'leader', 'master', 'elder',
                   'chairman', 'officer', 'executive', 'supervisor']
    
    if word.lower() not in title_words:
        return False
    
    generic_count = 0
    generic_patterns = [
        rf'(?:the|a|an)\s+{word}\b',
        rf'{word}\s+(?:position|role|job)\b',
    ]
    
    for pattern in generic_patterns:
        generic_count += len(re.findall(pattern, text, re.IGNORECASE))
    
    return generic_count >= 3


def has_strong_name_evidence(word, text, count):
    if count >= 3:
        return True
    
    if ' ' in word and all(part[0].isupper() for part in word.split() if part):
        return True
    
    strong_patterns = [
        rf'\b{word}\s+(?:said|asked|replied|answered|shouted|whispered|muttered|exclaimed|yelled|called|responded|interrupted|explained|suggested|wondered|thought|continued|added|began|finished|concluded)\b',
        rf'\b(?:said|asked|replied|answered|responded|called|yelled|whispered|muttered)\s+{word}\b',
        
        rf"\b{word}'s\s+(?:face|eyes|hand|voice|body|mind|heart|head|room|office|desk|car|house|family|father|mother|sister|brother|son|daughter|wife|husband)",
        rf'\b(?:to|at|with|from|for|by|toward|towards|beside|behind|near)\s+{word}\b',
        
        rf'["\'](?:[^"\']*\s)?{word}[,\.]?(?:\s[^"\']*)??["\']',
        rf'{word}[,\.]?\s+["\']',
        rf'["\'][^"\']*[,\.]?\s+{word}\s+(?:said|asked|replied)',
        
        rf'\b{word}\s+(?:was|is|were|are|had|has|have|would|could|should|might)\s+(?:a|an|the|not|never|always|still|now|already)\s+\w+',
        rf'\b(?:the|a|an)\s+(?:\w+\s+)?(?:named|called)\s+{word}\b',
        rf'\b{word},?\s+(?:who|whose|whom)\b',
        
        rf'\b{word}\s+(?:walked|ran|stood|sat|looked|turned|smiled|frowned|nodded|shook|grabbed|took|gave|opened|closed|moved|stepped|rushed|entered|left|arrived|departed|watched|stared|glanced|noticed|realized|understood|remembered|forgot|knew|thought|felt|sensed|reached|pulled|pushed|held|carried|dropped|picked|raised|lowered|pointed|touched|pressed|released)\b',
        
        rf'\b{word}\b[,\.]?\s+(?:He|She|They|His|Her|Their|Him|Them)\b',
        
        rf'\b{word}(?:\'s)?\s+(?:father|mother|brother|sister|son|daughter|wife|husband|parent|child|children|family|friend|friends|colleague|boss|subordinate|teacher|student)\b',
        
        rf'\b(?:Mr|Mrs|Ms|Miss|Dr|Professor|Sir|Madam|Lady|Lord)\s+{word}\b',
        
        rf'\b{word}\s+(?:felt|seemed|appeared|looked|sounded)\s+(?:angry|happy|sad|worried|concerned|surprised|shocked|confused|excited|nervous|calm|afraid|relieved)\b',
        
        rf'\b{word},?\s+(?:a|an|the)\s+(?:\w+\s+){{0,3}}(?:man|woman|person|boy|girl|warrior|mage|knight|hero|villain|student|teacher|doctor|soldier|agent|detective|officer)\b',
    ]
    
    evidence_count = 0
    matched_patterns = set()
    
    for i, pattern in enumerate(strong_patterns):
        if re.search(pattern, text, re.IGNORECASE):
            evidence_count += 1
            matched_patterns.add(i)
            if i < 3:
                if evidence_count >= 1:
                    return True
            if evidence_count >= 2:
                return True
    
    quote_pattern = rf'["\'][^"\']*\b{word}\b[^"\']*["\']'
    quote_matches = re.findall(quote_pattern, text, re.IGNORECASE)
    if len(quote_matches) >= 2:
        return True
    
    return False


def detect_names_from_english(english_text):
    
    import re
    
    words = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', english_text)
    
    word_counts = Counter(words)
    
    exclude_words = {
        'The', 'A', 'An', 'This', 'That', 'These', 'Those', 'It', 'He', 'She', 'They',
        'I', 'We', 'You', 'My', 'Your', 'His', 'Her', 'Their', 'Our', 'Its',
        'Mr', 'Mrs', 'Ms', 'Dr', 'Professor', 'Sir', 'Lady', 'Lord',
        'Chapter', 'Part', 'Section', 'Page', 'Book', 'Author', 'Volume',
        'Curse', 'Spirit', 'Domain', 'Expansion', 'Technique', 'Sorcerer',
        'Guild', 'Party', 'Team', 'Group',
        'God', 'Demon', 'Monster', 'Beast', 'Dragon', 'Angel', 'Devil',
        'Quest', 'Mission', 'Dungeon', 'Level', 'Skill', 'Ability', 'Power',
        'Rank', 'Class', 'Grade', 'Status', 'System', 'Interface',
        'Family', 'Clan', 'House', 'Tribe',
        'Student', 'Teacher', 'Instructor',
        'Idol', 'Star', 'Celebrity', 'Singer', 'Actor', 'Actress', 'Artist', 'Model',
        'Fan', 'Fans', 'Trainee', 'Rookie', 'Debut', 'Agency', 'Company',
        'Man', 'Woman', 'Person', 'People', 'Everyone', 'Someone', 'Anyone', 'Nobody',
        'Boy', 'Girl', 'Child', 'Kid', 'Baby', 'Youth', 'Adult',
        'January', 'February', 'March', 'April', 'May', 'June', 'July',
        'August', 'September', 'October', 'November', 'December',
        'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday',
        'Today', 'Tomorrow', 'Yesterday', 'Morning', 'Evening', 'Night', 'Day',
        'Week', 'Month', 'Year', 'Season', 'Spring', 'Summer', 'Fall', 'Winter',
        'Ha', 'Oh', 'Ah', 'Eh', 'Uh', 'Um', 'Huh', 'Hmm', 'Hm', 'Wow', 'Whoa',
        'Hehe', 'Haha', 'Hihi', 'Hoho', 'Huhu', 'Hehehe', 'Hahaha', 'Lol', 'Lmao',
        'Pfft', 'Tsk', 'Tch', 'Ugh', 'Argh', 'Ooh', 'Aah', 'Eek', 'Yay', 'Nah',
        'Shh', 'Ssh', 'Psst', 'Aww', 'Oww', 'Ouch', 'Yikes', 'Geez', 'Gosh', 'Dang',
        'Sigh', 'Gasp', 'Gulp', 'Sniff', 'Cough', 'Ahem', 'Ahhh', 'Ohhh', 'Eeee',
        'Hmph', 'Bah', 'Pah', 'Gah', 'Ack', 'Oof', 'Whew', 'Phew',
        'Yes', 'No', 'Ok', 'Okay', 'Hey', 'Hi', 'Hello', 'Bye', 'Well', 'Now',
        'What', 'Who', 'Where', 'When', 'Why', 'How', 'Which',
        'But', 'And', 'Or', 'So', 'If', 'Then', 'Just', 'Only', 'Even', 'Still',
        'Here', 'There', 'Back', 'Up', 'Down', 'Out', 'In', 'On', 'Off',
        'Very', 'Really', 'Too', 'Much', 'More', 'Most', 'Some', 'Any', 'All',
        'First', 'Second', 'Third', 'Last', 'Next', 'Other', 'Same', 'New', 'Old',
        'Good', 'Bad', 'Big', 'Small', 'Great', 'Little', 'Long', 'Short',
        'Right', 'Wrong', 'True', 'False', 'Real', 'Fake',
        'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten',
        'Time', 'Thing', 'Things', 'Something', 'Nothing', 'Everything', 'Anything',
        'Way', 'Place', 'World', 'Life', 'Death', 'Love', 'Hate', 'Hope', 'Fear',
        'Said', 'Says', 'Asked', 'Replied', 'Thought', 'Knew', 'Saw', 'Heard',
        'Come', 'Go', 'Get', 'Take', 'Make', 'Give', 'Let', 'See', 'Know', 'Think',
        'Look', 'Want', 'Need', 'Try', 'Use', 'Find', 'Tell', 'Feel', 'Leave', 'Call',
        'After', 'Before', 'During', 'Since', 'Until', 'While', 'Because', 'Although',
        'Like', 'Unlike', 'With', 'Without', 'About', 'Around', 'Through', 'Between',
        'Might', 'Must', 'Should', 'Would', 'Could', 'Can', 'Will', 'Shall',
        'Been', 'Being', 'Have', 'Has', 'Had', 'Do', 'Does', 'Did', 'Is', 'Are', 'Was', 'Were',
    }
    
    potential_names = set()
    
    for word, count in word_counts.items():
        if count < 1 or word in exclude_words or len(word) < 3:
            continue
        if word.lower() in {w.lower() for w in exclude_words}:
            continue
        
        if is_generic_title_usage(word, english_text):
            continue
        
        if is_onomatopoeia_or_interjection(word):
            dialogue_count = sum(1 for pattern in [
                rf'"{word}\s*[,\.]?\s*"',
                rf'{word}\s+(?:said|asked|replied|shouted|whispered|muttered|exclaimed)',
                rf'(?:said|asked|replied)\s+{word}',
                rf"{word}'s",
            ] if re.search(pattern, english_text, re.IGNORECASE))
            
            if dialogue_count < 2 and count < 3:
                continue
        
        if not has_strong_name_evidence(word, english_text, count):
            continue
        
        potential_names.add(word)
    
    contextual_patterns = [
        r'(?:named|called)\s+([A-Z][a-z]{2,})',
        r'([A-Z][a-z]{2,}),?\s+(?:who|whose)',
        r'([A-Z][a-z]{2,})\s+(?:was|is)\s+(?:a|an|the)\s+(?:\w+\s+){0,2}(?:man|woman|person|warrior|mage|knight|student|teacher)',
        r'(?:son|daughter|wife|husband|mother|father|sister|brother|friend)\s+(?:of\s+)?([A-Z][a-z]{2,})',
        r'"([A-Z][a-z]{2,})[!,\?]"',
        r'\b(?:Miss|Mister)\s+([A-Z][a-z]{2,})',
        r'([A-Z][a-z]{2,})\s+and\s+([A-Z][a-z]{2,})',
        r"([A-Z][a-z]{2,})'s\s+(?:face|eyes|voice|hand|room|office|family)",
    ]
    
    for pattern in contextual_patterns:
        matches = re.findall(pattern, english_text, re.IGNORECASE)
        for match in matches:
            if isinstance(match, tuple):
                names_to_add = match
            else:
                names_to_add = [match]
            
            for name_match in names_to_add:
                if isinstance(name_match, str) and len(name_match) >= 3:
                    name = name_match[0].upper() + name_match[1:].lower() if len(name_match) > 1 else name_match.upper()
                    name_lower = name.lower()
                    
                    if name_lower in {w.lower() for w in exclude_words}:
                        continue
                    if is_onomatopoeia_or_interjection(name):
                        continue
                    if is_generic_title_usage(name, english_text):
                        continue
                    
                    potential_names.add(name)
    
    return potential_names


def validate_detected_names(names_dict, korean_text, english_text=None):
    validated = {}
    
    korean_titles = ['대표', '사장', '부장', '과장', '팀장', '회장', '이사',
                     '선생', '교수', '선배', '후배', '형', '누나', '언니', '오빠']
    
    for korean_name, english_name in names_dict.items():
        if is_onomatopoeia_or_interjection(english_name):
            continue
        
        if korean_name in korean_titles:
            pattern = rf'[가-힣]{{2,4}}\s*{korean_name}'
            if not re.search(pattern, korean_text):
                has_character_context = any(re.search(p, korean_text) for p in [
                    rf'{korean_name}(?:이|가|은|는)\s+(?:말했다|물었다|대답했다|생각했다)',
                    rf'{korean_name}(?:의)',
                    rf'"{korean_name}"',
                ])
                
                if not has_character_context:
                    continue
        
        if len(english_name) == 1 and english_name not in ['I', 'A']:
            continue
        
        if english_name.isupper() and len(english_name) > 1:
            continue
        
        if any(char.isdigit() for char in english_name):
            continue
        
        if english_text:
            word_count = english_text.count(english_name)
            if word_count >= 1:
                validated[korean_name] = english_name
                continue
        
        validated[korean_name] = english_name
    
    return validated


def find_korean_equivalents(english_names, korean_text, english_text, provider, api_key, selected_model):
    
    if not english_names or not api_key:
        return {}
    
    try:
        names_list = '\n'.join(sorted(english_names))
        
        korean_sample = korean_text[:4000] if len(korean_text) > 4000 else korean_text
        english_sample = english_text[:4000] if len(english_text) > 4000 else english_text
        
        system_prompt = """You are an expert at matching character names between Korean source text and English translations.
Your task is to find the actual Korean names that correspond to the given English names by analyzing both texts.

You are EXTREMELY STRICT about what counts as a character name."""

        user_prompt = f"""I have a Korean web novel and its English translation. Find the Korean character names that correspond to these English names.

English names detected:
{names_list}

Korean source text (excerpt):
{korean_sample}

English translation (excerpt):
{english_sample}

CRITICAL RULES - READ CAREFULLY:

1. ONLY extract PERSONAL CHARACTER NAMES or TITLES USED AS CHARACTER IDENTIFIERS, NOT:
   ❌ Sound effects or interjections (Haha, Hehe, Hoho, Wow, Argh, Ugh)
   ❌ Generic descriptors without names (Young man, Old woman, Girl, Boy, Person)
   ❌ Abstract concepts (Power, Skill, Ability, Technique)
   ❌ System/Game terms (Quest, Mission, Level, Dungeon, Guild)
   
   ✅ BUT DO INCLUDE:
   ✅ Job titles when used as character identifiers (Manager, Director, CEO, Boss, Chief, Master)
   ✅ Titles when they refer to specific characters consistently
   ✅ Any word that acts as a character's name or identifier

2. The Korean name MUST:
   ✅ Appear in the Korean source text provided
   ✅ Be used as a character identifier (with dialogue, actions, or possessives)
   ✅ Refer to a specific individual person (even if by title/role)

3. Examples of VALID inclusions:
   - "Manager" if used like: "Manager said..." or "I spoke to Manager"
   - "Chief" if it refers to a specific person consistently
   - "Boss" if it's how a specific character is addressed
   - "Master" if it's a specific character's title

4. Verify by checking:
   - Does the Korean name appear with particles like 이/가/은/는/을/를?
   - Is it used in dialogue attribution (X가 말했다)?
   - Does it appear with possessive 의?
   - Is it used with action verbs?

Return ONLY a valid JSON object mapping English names to Korean names:
{{"Akari": "아카리", "Manager": "부장", "Chief": "대표"}}

Include titles if they're used as character identifiers. Only exclude obvious non-names like sound effects."""

        headers = {"Content-Type": "application/json"}
        json_payload = {
            "model": selected_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 1000
        }
        
        if provider == 'openrouter':
            headers["Authorization"] = f"Bearer {api_key}"
            headers["HTTP-Referer"] = "http://localhost:5000"
            headers["X-Title"] = "Novel Translator"
            response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=json_payload)
        elif provider == 'openai':
            headers["Authorization"] = f"Bearer {api_key}"
            response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=json_payload)
        elif provider == 'google':
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{selected_model}:generateContent?key={api_key}"
            json_payload = {
                "contents": [{
                    "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]
                }]
            }
            response = requests.post(url, headers=headers, json=json_payload)
        else:
            return {}
        
        if response.status_code == 200:
            data = response.json()
            
            if provider == 'google':
                candidates = data.get('candidates', [])
                if candidates:
                    content = candidates[0].get('content', {})
                    parts = content.get('parts', [])
                    if parts:
                        content_str = parts[0].get('text', '')
                    else:
                        return {}
                else:
                    return {}
            else:
                choices = data.get('choices', [])
                if choices:
                    content_str = choices[0].get('message', {}).get('content', '')
                else:
                    return {}
            
            try:
                if '```json' in content_str:
                    content_str = content_str.split('```json')[1].split('```')[0].strip()
                elif '```' in content_str:
                    content_str = content_str.split('```')[1].split('```')[0].strip()
                
                name_mapping = json.loads(content_str)
                
                validated_mapping = {}
                for eng_name, kor_name in name_mapping.items():
                    if kor_name in korean_text:
                        validated_mapping[kor_name] = eng_name
                
                validated_mapping = validate_detected_names(
                    validated_mapping, korean_text, english_text
                )
                
                return validated_mapping
                
            except json.JSONDecodeError:
                return {}
        else:
            return {}
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {}


def detect_characters_hybrid(text, provider, api_key, selected_model, translated_text=None):
    
    if not api_key:
        return {'error': 'API key not configured'}
    
    try:
        if translated_text and translated_text.strip():
            english_names = detect_names_from_english(translated_text)
            
            if not english_names:
                translated_text = None
            else:
                korean_mapping = find_korean_equivalents(
                    english_names, text, translated_text,
                    provider, api_key, selected_model
                )
                
                final_names = list(korean_mapping.keys())
                
                return {
                    'success': True,
                    'characters': final_names[:30],
                    'translations': korean_mapping,
                    'stats': {
                        'detection_mode': 'bilingual',
                        'english_names_found': len(english_names),
                        'korean_mapped': len(korean_mapping),
                        'final_count': len(final_names)
                    }
                }
        
        ai_result = detect_characters(text, provider, api_key, selected_model)
        ai_detected = set(ai_result.get('characters', [])) if ai_result.get('success') else set()
        
        pattern_detected = pattern_match_names(text)
        
        all_names = ai_detected | pattern_detected
        
        final_names = deduplicate_names(all_names, text)
        
        final_names = final_names[:30]
        
        return {
            'success': True,
            'characters': final_names,
            'stats': {
                'detection_mode': 'korean_only',
                'ai_detected': len(ai_detected),
                'pattern_detected': len(pattern_detected),
                'total_before_dedup': len(all_names),
                'final_count': len(final_names)
            }
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'error': str(e)}

def translate_names(korean_names, provider, api_key, selected_model):

    if not api_key:
        return {'error': 'API key not configured'}
    
    try:
        system_prompt = """You are a Korean name romanization expert for web novels.
Your task is to romanize Korean names to their proper English spelling following standard Korean romanization.

Rules:
1. ROMANIZE Korean names - do NOT translate them to Western names
2. Use standard Korean romanization (Revised Romanization of Korean)
3. For full names (surname + given name): Romanize the surname, then hyphenate the given name syllables
   - 김수현 → Kim Su-hyeon (NOT "Kim Su" or "John Kim")
   - 박민수 → Park Min-su
   - 이영희 → Lee Yeong-hui
4. For given names only (no surname): Hyphenate the syllables
   - 수현 → Su-hyeon (NOT "Hyeon" or "Su")
   - 민수 → Min-su
   - 영희 → Yeong-hui
5. Single syllable names stay as-is
   - 현 → Hyeon
6. Common Korean surnames: 김→Kim, 이→Lee, 박→Park, 최→Choi, 정→Jeong, 강→Kang, 조→Jo, 윤→Yoon, 장→Jang, 임→Lim
7. Capitalize the first letter of each part
8. IMPORTANT - English loanwords: If a Korean name is a transliteration of an English word, convert it back to the original English spelling:
   - 러쉬 → Rush
   - 제시카 → Jessica
   - 마이클 → Michael
   - 크리스 → Chris
   - 앨리스 → Alice
   - 로즈 → Rose
   - 다니엘 → Daniel
9. Return as a JSON object mapping Korean names to romanized names"""

        names_list = "\n".join(korean_names)
        user_prompt = f"""Romanize these Korean character names to English.

Return ONLY a valid JSON object like this:
{{ "김수현": "Kim Su-hyeon", "수현": "Su-hyeon", "러쉬": "Rush", "제시카": "Jessica" }}

IMPORTANT: 
- Romanize native Korean names properly with hyphens
- Convert English loanwords back to original English spelling (러쉬→Rush, 마이클→Michael, etc.)

Korean names:
{names_list}"""

        headers = {"Content-Type": "application/json"}
        json_payload = {
            "model": selected_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 1000
        }
        
        if provider == 'openrouter':
            headers["Authorization"] = f"Bearer {api_key}"
            headers["HTTP-Referer"] = "http://localhost:5000"
            headers["X-Title"] = "Novel Translator"
            response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=json_payload)
        
        elif provider == 'openai':
            headers["Authorization"] = f"Bearer {api_key}"
            response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=json_payload)
        
        elif provider == 'google':
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{selected_model}:generateContent?key={api_key}"
            json_payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": f"{system_prompt}\n\n{user_prompt}"}
                        ]
                    }
                ]
            }
            response = requests.post(url, headers=headers, json=json_payload)
        
        else:
            return {'error': 'Unsupported provider. Please use OpenRouter, OpenAI, or Google Gemini.'}
        
        if response.status_code == 200:
            data = response.json()
            
            if provider == 'google':
                candidates = data.get('candidates', [])
                if candidates:
                    content = candidates[0].get('content', {})
                    parts = content.get('parts', [])
                    if parts:
                        content_str = parts[0].get('text', '')
                    else:
                        return {'error': 'Google API: No content.'}
                else:
                    return {'error': 'Google API: No candidates.'}
            else:
                choices = data.get('choices', [])
                if choices:
                    content_str = choices[0].get('message', {}).get('content', '')
                else:
                    return {'error': f'{provider.capitalize()} API: No choices.'}
            
            try:
                if '```json' in content_str:
                    content_str = content_str.split('```json')[1].split('```')[0].strip()
                elif '```' in content_str:
                    content_str = content_str.split('```')[1].split('```')[0].strip()
                
                translations = json.loads(content_str)
                return {'success': True, 'translations': translations}
            except json.JSONDecodeError:
                return {'error': 'Failed to parse AI response'}
        else:
            return {'error': f'{provider.capitalize()} API Error: {response.status_code}'}
            
    except Exception as e:
        return {'error': str(e)}

def detect_character_genders(korean_names, text_sample, provider, api_key, selected_model):

    if not api_key:
        return {'error': 'API key not configured'}
    
    try:
        system_prompt = """You are a Korean web novel character analysis expert.
Your task is to determine the most appropriate pronouns for each character based on the story context.

Rules:
1. Analyze how each character is portrayed in the text
2. Determine if the character should use he/him, she/her, or they/them pronouns
3. Base your decision on Korean pronouns, titles, descriptions, and context clues
4. Return as a JSON object mapping Korean names to pronoun types
5. Use "male" for he/him, "female" for she/her, "other" for they/them
6. If uncertain, default to "auto" which means the translator should decide based on broader context"""

        names_list = "\n".join(korean_names)
        user_prompt = f"""Analyze these character names in the context of the story and determine appropriate pronouns.

Character names:
{names_list}

Story excerpt:
{text_sample[:2000]}

Return ONLY a valid JSON object like this:
{ "김철수": "male", "이영희": "female", "박민수": "male"} 

Valid values are: "male" (he/him), "female" (she/her), "other" (they/them), or "auto" (let translator decide)"""

        headers = {"Content-Type": "application/json"}
        json_payload = {
            "model": selected_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 1000
        }
        
        if provider == 'openrouter':
            headers["Authorization"] = f"Bearer {api_key}"
            headers["HTTP-Referer"] = "http://localhost:5000"
            headers["X-Title"] = "Novel Translator"
            response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=json_payload)
        
        elif provider == 'openai':
            headers["Authorization"] = f"Bearer {api_key}"
            response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=json_payload)
        
        elif provider == 'google':
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{selected_model}:generateContent?key={api_key}"
            json_payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": f"{system_prompt}\n\n{user_prompt}"}
                        ]
                    }
                ]
            }
            response = requests.post(url, headers=headers, json=json_payload)
        
        else:
            return {'error': 'Unsupported provider. Please use OpenRouter, OpenAI, or Google Gemini.'}
        
        if response.status_code == 200:
            data = response.json()
            
            if provider == 'google':
                candidates = data.get('candidates', [])
                if candidates:
                    content = candidates[0].get('content', {})
                    parts = content.get('parts', [])
                    if parts:
                        content_str = parts[0].get('text', '')
                    else:
                        return {'error': 'Google API: No content.'}
                else:
                    return {'error': 'Google API: No candidates.'}
            else:
                choices = data.get('choices', [])
                if choices:
                    content_str = choices[0].get('message', {}).get('content', '')
                else:
                    return {'error': f'{provider.capitalize()} API: No choices.'}
            
            try:
                if '```json' in content_str:
                    content_str = content_str.split('```json')[1].split('```')[0].strip()
                elif '```' in content_str:
                    content_str = content_str.split('```')[1].split('```')[0].strip()
                
                genders = json.loads(content_str)
                return {'success': True, 'genders': genders}
            except json.JSONDecodeError:
                return {'error': 'Failed to parse AI response'}
        else:
            return {'error': f'{provider.capitalize()} API Error: {response.status_code}'}
            
    except Exception as e:
        return {'error': str(e)}
