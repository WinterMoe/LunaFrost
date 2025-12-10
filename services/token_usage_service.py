

from datetime import datetime, timedelta
from database.database import db_session_scope
from database.db_models import TranslationTokenUsage, Chapter, Novel
import tiktoken

def save_token_usage(user_id, chapter_id, provider, model, input_tokens, output_tokens, total_tokens, translation_type='content'):

    try:
        with db_session_scope() as session:
            token_usage = TranslationTokenUsage(
                user_id=user_id,
                chapter_id=chapter_id,
                provider=provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                translation_type=translation_type
            )
            session.add(token_usage)
            session.flush()
            return token_usage
    except Exception as e:
        return None

def get_chapter_token_usage(chapter_id):

    try:
        with db_session_scope() as session:
            records = session.query(TranslationTokenUsage).filter(
                TranslationTokenUsage.chapter_id == chapter_id
            ).order_by(TranslationTokenUsage.created_at.desc()).all()
            return records
    except Exception as e:
        return []

def get_novel_token_usage(novel_id, user_id):

    try:
        with db_session_scope() as session:
            chapters = session.query(Chapter).filter(
                Chapter.novel_id == novel_id
            ).all()
            
            chapter_ids = [ch.id for ch in chapters]
            
            if not chapter_ids:
                return {
                    'total_input_tokens': 0,
                    'total_output_tokens': 0,
                    'total_tokens': 0,
                    'record_count': 0
                }
            
            records = session.query(TranslationTokenUsage).filter(
                TranslationTokenUsage.chapter_id.in_(chapter_ids),
                TranslationTokenUsage.user_id == user_id
            ).all()
            
            total_input = sum(r.input_tokens for r in records)
            total_output = sum(r.output_tokens for r in records)
            total = sum(r.total_tokens for r in records)
            
            return {
                'total_input_tokens': total_input,
                'total_output_tokens': total_output,
                'total_tokens': total,
                'record_count': len(records)
            }
    except Exception as e:
        return {
            'total_input_tokens': 0,
            'total_output_tokens': 0,
            'total_tokens': 0,
            'record_count': 0
        }

def get_user_token_usage(user_id, start_date=None, end_date=None):

    try:
        with db_session_scope() as session:
            query = session.query(TranslationTokenUsage).filter(
                TranslationTokenUsage.user_id == user_id
            )
            
            if start_date:
                query = query.filter(TranslationTokenUsage.created_at >= start_date)
            if end_date:
                query = query.filter(TranslationTokenUsage.created_at <= end_date)
            
            records = query.all()
            
            total_input = sum(r.input_tokens for r in records)
            total_output = sum(r.output_tokens for r in records)
            total = sum(r.total_tokens for r in records)
            
            return {
                'total_input_tokens': total_input,
                'total_output_tokens': total_output,
                'total_tokens': total,
                'record_count': len(records)
            }
    except Exception as e:
        return {
            'total_input_tokens': 0,
            'total_output_tokens': 0,
            'total_tokens': 0,
            'record_count': 0
        }

def clear_user_token_usage(user_id):

    try:
        with db_session_scope() as session:
            session.query(TranslationTokenUsage).filter(
                TranslationTokenUsage.user_id == user_id
            ).delete()
            return True
    except Exception as e:
        return False

def get_token_usage_by_provider(user_id, start_date=None, end_date=None):

    try:
        with db_session_scope() as session:
            query = session.query(TranslationTokenUsage).filter(
                TranslationTokenUsage.user_id == user_id
            )
            
            if start_date:
                query = query.filter(TranslationTokenUsage.created_at >= start_date)
            if end_date:
                query = query.filter(TranslationTokenUsage.created_at <= end_date)
            
            records = query.all()
            
            provider_stats = {}
            for record in records:
                provider = record.provider
                if provider not in provider_stats:
                    provider_stats[provider] = {
                        'input_tokens': 0,
                        'output_tokens': 0,
                        'total_tokens': 0,
                        'count': 0
                    }
                
                provider_stats[provider]['input_tokens'] += record.input_tokens
                provider_stats[provider]['output_tokens'] += record.output_tokens
                provider_stats[provider]['total_tokens'] += record.total_tokens
                provider_stats[provider]['count'] += 1
            
            return provider_stats
    except Exception as e:
        return {}

def get_token_usage_by_model(user_id, start_date=None, end_date=None):

    try:
        with db_session_scope() as session:
            query = session.query(TranslationTokenUsage).filter(
                TranslationTokenUsage.user_id == user_id
            )
            
            if start_date:
                query = query.filter(TranslationTokenUsage.created_at >= start_date)
            if end_date:
                query = query.filter(TranslationTokenUsage.created_at <= end_date)
            
            records = query.all()
            
            model_stats = {}
            for record in records:
                model = record.model
                if model not in model_stats:
                    model_stats[model] = {
                        'input_tokens': 0,
                        'output_tokens': 0,
                        'total_tokens': 0,
                        'count': 0,
                        'provider': record.provider
                    }
                
                model_stats[model]['input_tokens'] += record.input_tokens
                model_stats[model]['output_tokens'] += record.output_tokens
                model_stats[model]['total_tokens'] += record.total_tokens
                model_stats[model]['count'] += 1
            
            return model_stats
    except Exception as e:
        return {}

def get_recent_token_usage(user_id, days=30):

    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        with db_session_scope() as session:
            records = session.query(TranslationTokenUsage).filter(
                TranslationTokenUsage.user_id == user_id,
                TranslationTokenUsage.created_at >= start_date,
                TranslationTokenUsage.created_at <= end_date
            ).order_by(TranslationTokenUsage.created_at).all()
            
            daily_stats = {}
            for record in records:
                date_key = record.created_at.date().isoformat()
                if date_key not in daily_stats:
                    daily_stats[date_key] = {
                        'input_tokens': 0,
                        'output_tokens': 0,
                        'total_tokens': 0,
                        'count': 0
                    }
                
                daily_stats[date_key]['input_tokens'] += record.input_tokens
                daily_stats[date_key]['output_tokens'] += record.output_tokens
                daily_stats[date_key]['total_tokens'] += record.total_tokens
                daily_stats[date_key]['count'] += 1
            
            return daily_stats
    except Exception as e:
        return {}

"""
Fixed token estimation for Korean to English translation.
"""
import re
import html
import tiktoken

def clean_text_for_estimation(text):

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

def build_translation_prompts(text, glossary=None, images=None):

    system_prompt = """You are a professional Korean-to-English literary translator specializing in web novels. 
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
   - Adapt culture-specific terms (e.g., oppa, sunbae, ahjumma) depending on context:
     - Retain them if they carry emotional or relational meaning not captured in English.
     - Translate descriptively if it improves clarity for the reader.
   - Preserve the spirit of idioms and proverbs using equivalent English expressions when possible.
   - Maintain flavor and rhythm typical of Korean web novels—introspective tone, casual inner monologue, or dramatic phrasing.

3. **Internal Monologue and Dialogue**
   - Clearly differentiate between spoken dialogue, thoughts, and narration.
   - Inner monologues should sound natural in English while preserving the Korean tone (e.g., self-deprecating, ironic, etc.).
   - Avoid robotic or overly formal phrasing.

4. **Terminology and Worldbuilding**
   - For fantasy or system-based novels, maintain consistent translation of recurring terms (skills, titles, items, etc.).
   - Use capitalization for system messages or interface terms if the original does (e.g., "Quest Completed", "Dungeon Gate").

5. **Faithfulness and Flow**
   - Translate meaning, not word order – prioritize readability and emotional accuracy.
   - Do not embellish or censor content; keep to the author's tone.
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
"""

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

    return system_prompt, user_prompt

def estimate_translation_tokens(text, provider, model, glossary=None, images=None):

    try:
        cleaned_text = clean_text_for_estimation(text)
        
        system_prompt, user_prompt = build_translation_prompts(
            cleaned_text, glossary, images
        )

        if provider in ['openrouter', 'openai']:
            try:
                encoding = tiktoken.get_encoding('cl100k_base')

                system_tokens = len(encoding.encode(system_prompt))
                
                user_tokens = len(encoding.encode(user_prompt))
                
                input_tokens = system_tokens + user_tokens

                korean_text_tokens = len(encoding.encode(cleaned_text))
                
                output_tokens = int(korean_text_tokens * 0.6)
                
                output_tokens = int(output_tokens * 1.2)

                return {
                    'input_tokens': input_tokens,
                    'output_tokens': output_tokens,
                    'total_tokens': input_tokens + output_tokens,
                    'estimation_method': 'tiktoken',
                    'korean_text_tokens': korean_text_tokens,
                    'system_tokens': system_tokens,
                    'user_tokens': user_tokens
                }
            except Exception as e:
                return estimate_tokens_rough(cleaned_text, system_prompt, user_prompt)
        else:
            return estimate_tokens_rough(cleaned_text, system_prompt, user_prompt)

    except Exception as e:
        return {
            'input_tokens': 0,
            'output_tokens': 0,
            'total_tokens': 0,
            'estimation_method': 'error',
            'error': str(e)
        }

def estimate_tokens_rough(text, system_prompt, user_prompt):

    korean_chars = sum(1 for c in text if 0xAC00 <= ord(c) <= 0xD7A3)
    
    
    korean_text_tokens = int(korean_chars / 2.5)
    other_chars = len(text) - korean_chars
    other_text_tokens = int(other_chars / 4)
    text_tokens = korean_text_tokens + other_text_tokens
    
    system_tokens = int(len(system_prompt) / 4)
    
    instructions_length = len(user_prompt) - len(text)
    instruction_tokens = int(instructions_length / 4)
    user_tokens = instruction_tokens + text_tokens
    
    input_tokens = system_tokens + user_tokens
    
    output_tokens = int(text_tokens * 0.6 * 1.2)                          

    return {
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'total_tokens': input_tokens + output_tokens,
        'estimation_method': 'rough',
        'korean_text_tokens': text_tokens,
        'system_tokens': system_tokens,
        'user_tokens': user_tokens
    }

def analyze_estimation_accuracy(estimated, actual):

    input_accuracy = (estimated['input_tokens'] / actual['input_tokens']) if actual['input_tokens'] > 0 else 0
    output_accuracy = (estimated['output_tokens'] / actual['output_tokens']) if actual['output_tokens'] > 0 else 0
    total_accuracy = (estimated['total_tokens'] / actual['total_tokens']) if actual['total_tokens'] > 0 else 0
    
    actual_output_ratio = actual['output_tokens'] / estimated.get('korean_text_tokens', 1)
    
    return {
        'input_accuracy': input_accuracy,
        'output_accuracy': output_accuracy,
        'total_accuracy': total_accuracy,
        'input_difference': estimated['input_tokens'] - actual['input_tokens'],
        'output_difference': estimated['output_tokens'] - actual['output_tokens'],
        'total_difference': estimated['total_tokens'] - actual['total_tokens'],
        'actual_output_ratio': actual_output_ratio,
        'was_underestimated': estimated['total_tokens'] < actual['total_tokens'],
        'percentage_error': abs(estimated['total_tokens'] - actual['total_tokens']) / actual['total_tokens'] * 100
    }
