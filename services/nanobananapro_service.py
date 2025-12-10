   

from typing import Optional, Literal, List, Dict
from PIL import Image
import io
import base64
import requests
import json
import re

class NanoBananaProService:
           
    
    def translate_image(self, image_path: str, api_key: str, source_language: str = 'korean',
                       target_lang: str = 'English', use_openrouter: bool = False, custom_prompt_suffix: str = None):
                   
        if use_openrouter:
            return self._translate_with_openrouter(image_path, api_key, source_language, target_lang, custom_prompt_suffix)
        else:
            return self._translate_with_gemini_direct(image_path, api_key, source_language, target_lang, custom_prompt_suffix)
    
    def _translate_with_openrouter(self, image_path: str, api_key: str, source_language: str, target_lang: str, custom_prompt_suffix: str = None) -> List[Dict]:
                   
                               
        with open(image_path, 'rb') as img_file:
            image_bytes = img_file.read()
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        
                                   
        img = Image.open(image_path)
        mime_type = f"image/{img.format.lower()}" if img.format else "image/png"
        img_width, img_height = img.size
        
                                        
        source_lang_name = 'Korean' if source_language == 'korean' else 'Japanese'
        cultural_notes = ""
        if source_language == 'korean':
            cultural_notes = """
        - Preserve Korean honorifics and formality levels in natural English
        - Adapt culture-specific terms (oppa, sunbae, etc.) contextually
        - Maintain the introspective tone typical of Korean webtoons
        """
        elif source_language == 'japanese':
            cultural_notes = """
        - Preserve Japanese honorifics (-san, -kun, -chan, etc.) when contextually appropriate
        - Adapt culture-specific terms (senpai, kohai, etc.) naturally
        - Maintain the visual storytelling style typical of Japanese manga/webtoons
        - Preserve onomatopoeia style if present
        """
        
                                                             
                                                                                        
        prompt = f"""You are a professional webtoon/manga translator and image editor.

I'm providing you with a webtoon/manga image that contains {source_lang_name} text in speech bubbles, captions, and/or sound effects.

Your task: Generate a NEW version of this exact image with all {source_lang_name} text replaced by accurate {target_lang} translations.

Requirements:
1. Identify ALL {source_lang_name} text in the image (speech bubbles, captions, narration boxes, sound effects)
2. Translate each piece of text accurately and naturally to {target_lang}
3. Generate a new image that is IDENTICAL to the original EXCEPT the text is now in {target_lang}
4. Preserve the original art style, colors, character appearances, and layout EXACTLY
5. Make sure the translated text fits naturally within the speech bubbles and text areas
6. Use an appropriate font style that matches the original aesthetic (manga/webtoon style)
7. Maintain proper text sizing so it remains readable
{cultural_notes}

{custom_prompt_suffix if custom_prompt_suffix else ""}

IMPORTANT: Generate the translated image as your response. The image should look exactly like the original but with {target_lang} text instead of {source_lang_name} text."""
        
                                    
        headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "http://localhost:5000",
            "X-Title": "Novel Translator",
            "Content-Type": "application/json"
        }
        
        json_payload = {
            "model": "google/gemini-3-pro-image-preview",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_base64}"
                            }
                        }
                    ]
                }
            ],
            "temperature": 0.3,
            "max_tokens": 16000,
            "modalities": ["image", "text"]
        }
        
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=json_payload,
                timeout=120                                       
            )
            response.raise_for_status()
            
            data = response.json()
            
                                                                                                    
            print(f"🔍 OpenRouter response keys: {list(data.keys())}")
            if 'choices' in data:
                print(f"🔍 Number of choices: {len(data['choices'])}")
            
                                                
                                                                                        
            if 'choices' in data and len(data['choices']) > 0:
                choice = data['choices'][0]
                print(f"🔍 Choice keys: {list(choice.keys())}")
                
                if 'message' in choice:
                    message = choice['message']
                    print(f"🔍 Message keys: {list(message.keys())}")
                    
                                                                           
                    if message.get('images'):
                        print(f"🔍 Found {len(message['images'])} image(s) in response")
                        first_image = message['images'][0]
                        data_url = first_image.get('image_url', {}).get('url')
                        if data_url and isinstance(data_url, str) and data_url.startswith('data:'):
                                                       
                            try:
                                header, b64data = data_url.split(',', 1)
                                mime = header.split(';')[0].replace('data:', '') or 'image/png'
                                img_bytes = base64.b64decode(b64data)
                                print(f"✅ Successfully received translated image from Gemini via OpenRouter")
                                print(f"   Image format: {mime}, size: {len(img_bytes)} bytes")
                                return {"image_bytes": img_bytes, "mime_type": mime, "regions": []}
                            except Exception as e:
                                print(f"⚠️ Failed to decode returned image: {e}")
                                raise Exception(f"Gemini returned an image but it could not be decoded: {e}")
                    else:
                        print(f"🔍 No 'images' key in message")
                    
                                                                                                             
                                                                               
                    content = message.get('content', '')
                    print(f"🔍 Content type: {type(content).__name__}, length: {len(content) if isinstance(content, (str, list)) else 'N/A'}")
                    
                    if isinstance(content, list):
                        print(f"🔍 Content is a list with {len(content)} items")
                        if len(content) > 0:
                            print(f"🔍 First item type: {type(content[0]).__name__}")
                            if isinstance(content[0], dict):
                                print(f"🔍 First item keys: {list(content[0].keys())}")
                                                                         
                        if all(isinstance(item, dict) and {'text', 'bbox'}.issubset(set(item.keys())) for item in content):
                            print(f"⚠️ Gemini returned OCR data instead of image. Using fallback rendering pipeline.")
                            return content
                                            
                        text_content = ''
                        for item in content:
                            if isinstance(item, dict) and item.get('type') == 'text':
                                text_content += item.get('text', '')
                        content = text_content
                        print(f"🔍 Extracted text content length: {len(content)}")
                    
                                                                       
                    if content and isinstance(content, str):
                        print(f"⚠️ Gemini returned text instead of image. Attempting to parse as translation data...")
                        print(f"🔍 Content preview: {content[:500]}...")
                        json_str = content
                        
                                                   
                        if json_str.strip().startswith('['):
                            last_bracket = json_str.rfind(']')
                            if last_bracket != -1:
                                json_str = json_str[:last_bracket+1]
                        
                        json_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', json_str, re.DOTALL)
                        if json_match:
                            json_str = json_match.group(1)
                        else:
                            json_match = re.search(r'(\[.*?\])', json_str, re.DOTALL)
                            if json_match:
                                json_str = json_match.group(1)
                        
                        try:
                            translated_regions = json.loads(json_str)
                            if isinstance(translated_regions, list) and len(translated_regions) > 0:
                                print(f"✅ Parsed {len(translated_regions)} translated regions as fallback")
                                return translated_regions
                        except json.JSONDecodeError:
                            pass
                        
                                                                         
                        print(f"❌ Gemini did not generate an image. Response preview: {content[:300]}...")
                        raise Exception(
                            "Gemini did not return a generated image. "
                            "This may be because the model doesn't support image generation for this use case, "
                            "or the image could not be processed. Try using a different OCR method."
                        )
                    else:
                        print(f"❌ Content is empty or not a string. Content value: {repr(content)[:200]}")
                else:
                    print(f"❌ No 'message' key in choice. Choice: {choice}")
            
            raise Exception("OpenRouter/Gemini did not return a valid response. Check logs for details.")
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    error_msg += f" Response: {error_data}"
                except:
                    error_msg += f" Response status: {e.response.status_code}"
            raise Exception(f"OpenRouter API error: {error_msg}")
        except Exception as e:
            raise Exception(f"Error processing OpenRouter response: {str(e)}")
    
    def _translate_with_gemini_direct(self, image_path: str, api_key: str, source_language: str, target_lang: str, custom_prompt_suffix: str = None) -> bytes:
                                                     
        try:
            import google.generativeai as genai
        except ImportError:
            raise ImportError("google-generativeai is not installed. Install it with: pip install google-generativeai")
        
                          
        genai.configure(api_key=api_key)
        
                                                     
        model = genai.GenerativeModel('gemini-1.5-pro')
        
                    
        img = Image.open(image_path)
        
                                        
        source_lang_name = 'Korean' if source_language == 'korean' else 'Japanese'
        cultural_notes = ""
        if source_language == 'korean':
            cultural_notes = """
        - Preserve Korean honorifics and formality levels in natural English
        - Adapt culture-specific terms (oppa, sunbae, etc.) contextually
        - Maintain the introspective tone typical of Korean webtoons
        """
        elif source_language == 'japanese':
            cultural_notes = """
        - Preserve Japanese honorifics (-san, -kun, -chan, etc.) when contextually appropriate
        - Adapt culture-specific terms (senpai, kohai, etc.) naturally
        - Maintain the visual storytelling style typical of Japanese manga/webtoons
        - Preserve onomatopoeia style if present
        """
        
                                       
        prompt = f"""
        This is a webtoon/manga image with {source_lang_name} text.
        
        Please:
        1. Detect all text in the image (including {source_lang_name} characters)
        2. Translate the text from {source_lang_name} to {target_lang}
        3. Generate a new version of this image with the {source_lang_name} text replaced by the {target_lang} translation
        4. Maintain the same art style, positioning, and speech bubble layout
        5. Ensure the translated text fits naturally within the existing speech bubbles
        6. Make the translated text large and readable
        {cultural_notes}

        {custom_prompt_suffix if custom_prompt_suffix else ""}
        
        Return only the translated image.
        """
        
                                   
        try:
            response = model.generate_content([prompt, img])
            
                                         
            if hasattr(response, 'images') and response.images:
                return response.images[0]
            
                                                                 
            if hasattr(response, 'text') and response.text:
                                                         
                import re
                base64_match = re.search(r'data:image/[^;]+;base64,([A-Za-z0-9+/=]+)', response.text)
                if base64_match:
                    return base64.b64decode(base64_match.group(1))
            
                                                         
            raise Exception("Gemini did not return a translated image. The API response format may need adjustment.")
        except Exception as e:
            raise Exception(f"Gemini API error: {str(e)}. Note: Image generation with Gemini may require different API endpoints or models.")
    
    def save_translated_image(self, image_bytes: bytes, output_path: str) -> str:
                                               
        img = Image.open(io.BytesIO(image_bytes))
        img.save(output_path)
        return output_path

                           
nanobananapro_service = NanoBananaProService()

