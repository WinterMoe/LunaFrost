   

import os
import json
from typing import List, Dict, Optional
                                                                                     
            
                    
from PIL import Image

class OCRService:
                                                                               
    
    def __init__(self):
        self.paddleocr_instances = {}                                
    
    def detect_text(self, image_path: str, method: str, source_language: str = 'korean',
                   api_key: Optional[str] = None, endpoint: Optional[str] = None) -> List[Dict]:
                   
        if method == 'google':
            return self._google_ocr(image_path, api_key, source_language)
        elif method == 'azure':
            return self._azure_ocr(image_path, api_key, endpoint, source_language)
        elif method == 'nanobananapro':
            return self._nanobananapro_ocr(image_path, api_key, source_language)
        else:
            raise ValueError(f"Unknown OCR method: {method}")
    
    def detect_text_in_region(self, image_path: str, x: int, y: int, w: int, h: int,
                              method: str, source_language: str = 'korean',
                              api_key: Optional[str] = None, endpoint: Optional[str] = None) -> Optional[Dict]:
                   
        try:
            import cv2
            import numpy as np
            import tempfile
            
                            
            img = cv2.imread(image_path)
            if img is None:
                return None
            
                                                           
            img_h, img_w = img.shape[:2]
            x = max(0, min(x, img_w - 1))
            y = max(0, min(y, img_h - 1))
            w = min(w, img_w - x)
            h = min(h, img_h - y)
            
            if w <= 0 or h <= 0:
                return None
            
                             
            cropped = img[y:y+h, x:x+w]
            
                               
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                tmp_path = tmp.name
                cv2.imwrite(tmp_path, cropped)
            
            try:
                                               
                results = self.detect_text(tmp_path, method, source_language, api_key, endpoint)
                
                if results and len(results) > 0:
                                                             
                                                                          
                    separator = '' if source_language in ['japanese', 'korean', 'chinese'] else ' '
                    combined_text = separator.join([r.get('text', '') for r in results if r.get('text')])
                    avg_confidence = sum(r.get('confidence', 0) for r in results) / len(results) if results else 0
                    
                    return {
                        'text': combined_text.strip(),
                        'confidence': avg_confidence
                    }
                return None
            finally:
                                    
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except:
                    pass
                    
        except Exception as e:
            import traceback
            print(f"Error in detect_text_in_region: {e}")
            traceback.print_exc()
            return None
    
    def _google_ocr(self, image_path: str, api_key: str, source_language: str = 'korean') -> List[Dict]:
                   
        import base64
        import io
        
                                                                               
        is_service_account = api_key and (os.path.exists(api_key) or api_key.endswith('.json'))
        
        if is_service_account:
                                                            
            try:
                from google.cloud import vision
            except ImportError:
                raise ImportError("google-cloud-vision is not installed. Install it with: pip install google-cloud-vision")
            
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = api_key
            client = vision.ImageAnnotatorClient()
            
            with io.open(image_path, 'rb') as image_file:
                content = image_file.read()
            
            image = vision.Image(content=content)
            
                                                          
            image_context = vision.ImageContext()
            if source_language == 'japanese':
                image_context.language_hints = ['ja']
            elif source_language == 'korean':
                image_context.language_hints = ['ko']
            
            response = client.text_detection(image=image, image_context=image_context)
            texts = response.text_annotations
            
            if response.error.message:
                raise Exception(f"Google Vision API error: {response.error.message}")
            
            results = []
                                                                            
            for text in texts[1:]:
                vertices = text.bounding_poly.vertices
                x = min(v.x for v in vertices)
                y = min(v.y for v in vertices)
                width = max(v.x for v in vertices) - x
                height = max(v.y for v in vertices) - y
                
                results.append({
                    'text': text.description,
                    'bbox': [int(x), int(y), int(width), int(height)],
                    'confidence': 0.95                                              
                })
            
            return results
        else:
                                              
            try:
                import requests
            except ImportError:
                raise ImportError("requests is not installed. Install it with: pip install requests")
            
                                   
            with open(image_path, 'rb') as image_file:
                image_content = image_file.read()
            
            image_base64 = base64.b64encode(image_content).decode('utf-8')
            
                             
            url = f'https://vision.googleapis.com/v1/images:annotate?key={api_key}'
            
                                      
            language_hints = []
            if source_language == 'japanese':
                language_hints = ['ja']
            elif source_language == 'korean':
                language_hints = ['ko']
            
            payload = {
                'requests': [{
                    'image': {
                        'content': image_base64
                    },
                    'features': [{
                        'type': 'TEXT_DETECTION',
                        'maxResults': 100
                    }],
                    'imageContext': {
                        'languageHints': language_hints
                    } if language_hints else {}
                }]
            }
            
            response = requests.post(url, json=payload)
            response.raise_for_status()
            
            data = response.json()
            
            if 'error' in data:
                raise Exception(f"Google Vision API error: {data['error'].get('message', 'Unknown error')}")
            
            results = []
            if 'responses' in data and len(data['responses']) > 0:
                text_annotations = data['responses'][0].get('textAnnotations', [])
                                                                                
                for text in text_annotations[1:]:
                    vertices = text.get('boundingPoly', {}).get('vertices', [])
                    if len(vertices) >= 4:
                        x_coords = [v.get('x', 0) for v in vertices]
                        y_coords = [v.get('y', 0) for v in vertices]
                        x = min(x_coords)
                        y = min(y_coords)
                        width = max(x_coords) - x
                        height = max(y_coords) - y
                        
                        results.append({
                            'text': text.get('description', ''),
                            'bbox': [int(x), int(y), int(width), int(height)],
                            'confidence': 0.95
                        })
            
            return results
    
    def _azure_ocr(self, image_path: str, api_key: str, endpoint: str, source_language: str = 'korean') -> List[Dict]:
                                                   
        try:
            from azure.cognitiveservices.vision.computervision import ComputerVisionClient
            from msrest.authentication import CognitiveServicesCredentials
            from azure.cognitiveservices.vision.computervision.models import OperationStatusCodes
        except ImportError:
            raise ImportError("azure-cognitiveservices-vision-computervision is not installed. Install it with: pip install azure-cognitiveservices-vision-computervision")
        
                                  
        if not endpoint:
            raise ValueError("Azure endpoint is required")
        if not endpoint.startswith('http'):
                                                                           
            endpoint = f"https://{endpoint}"
                                                  
        endpoint = endpoint.rstrip('/')
        
                          
        if not api_key:
            raise ValueError("Azure API key is required")
        
                                                                    
                                  
        image_to_process = image_path
        temp_image_path = None
        try:
            if image_path.lower().endswith('.webp'):
                                               
                from PIL import Image
                img = Image.open(image_path)
                                                                            
                if img.mode == 'RGBA':
                    rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                    rgb_img.paste(img, mask=img.split()[3])                             
                    img = rgb_img
                temp_image_path = image_path.rsplit('.', 1)[0] + '_temp_azure.png'
                img.save(temp_image_path, 'PNG')
                image_to_process = temp_image_path
                print(f"🔄 Converted WebP to PNG for Azure OCR: {temp_image_path}")
        except Exception as e:
            print(f"⚠️ Warning: Could not convert image format: {e}. Trying original format...")
        
        try:
            client = ComputerVisionClient(endpoint, CognitiveServicesCredentials(api_key))
            
                                              
                                                                                                        
            language = 'ja' if source_language == 'japanese' else 'ko'
            
            with open(image_to_process, 'rb') as image_file:
                read_response = client.read_in_stream(image_file, language=language, raw=True)
            
                                    
            if not hasattr(read_response, 'headers') or 'Operation-Location' not in read_response.headers:
                raise Exception("Azure OCR did not return an operation location. Check your endpoint and API key.")
            
            operation_location = read_response.headers["Operation-Location"]
            operation_id = operation_location.split("/")[-1]
            
                             
            import time
            max_wait = 30                                
            wait_time = 0
            result = None
            while wait_time < max_wait:
                result = client.get_read_result(operation_id)
                if result.status not in ['notStarted', 'running']:
                    break
                time.sleep(0.5)
                wait_time += 0.5
            
            if result is None:
                raise Exception("Azure OCR operation timed out")
            
            if result.status == OperationStatusCodes.failed:
                error_msg = getattr(result, 'message', 'Unknown error')
                raise Exception(f"Azure OCR operation failed: {error_msg}")
            
            results = []
            if result.status == OperationStatusCodes.succeeded:
                if hasattr(result, 'analyze_result') and hasattr(result.analyze_result, 'read_results'):
                    for page in result.analyze_result.read_results:
                        if hasattr(page, 'lines'):
                            for line in page.lines:
                                bbox = line.bounding_box
                                if bbox and len(bbox) >= 8:
                                    x = min(bbox[0], bbox[6])
                                    y = min(bbox[1], bbox[3])
                                    width = max(bbox[2], bbox[4]) - x
                                    height = max(bbox[5], bbox[7]) - y
                                    
                                    confidence = 0.9
                                    if hasattr(line, 'appearance') and hasattr(line.appearance, 'style'):
                                        confidence = line.appearance.style.confidence
                                    
                                    results.append({
                                        'text': line.text,
                                        'bbox': [int(x), int(y), int(width), int(height)],
                                        'confidence': confidence
                                    })
                else:
                    raise Exception("Azure OCR succeeded but returned no read results")
            else:
                raise Exception(f"Azure OCR operation status: {result.status}")
            
            return results
            
        except Exception as e:
            error_msg = str(e)
                                                 
            if 'Bad Request' in error_msg or '400' in error_msg:
                raise Exception(
                    f"Azure OCR Bad Request. This could be due to:\n"
                    f"1. Invalid endpoint URL (should be like: https://your-resource.cognitiveservices.azure.com/)\n"
                    f"2. Invalid API key\n"
                    f"3. Unsupported image format (Azure may not support WebP - we tried to convert it)\n"
                    f"4. Image too large (max 50MB)\n"
                    f"Original error: {error_msg}"
                )
            raise Exception(f"Azure OCR error: {error_msg}")
        finally:
                                     
            if temp_image_path and os.path.exists(temp_image_path):
                try:
                    os.remove(temp_image_path)
                except:
                    pass
    
    def _nanobananapro_ocr(self, image_path: str, api_key: str, source_language: str = 'korean') -> List[Dict]:
                   
                                                                  
                                                               
                                                              
        raise NotImplementedError("Nano Banana Pro uses a different workflow - see translation task")
    
    def detect_text_with_grouping(self, image_path: str, method: str, source_language: str = 'korean',
                                   api_key: Optional[str] = None, endpoint: Optional[str] = None,
                                   enable_bubble_detection: bool = True) -> Dict:
                   
                                
        ocr_regions = self.detect_text(image_path, method, source_language, api_key, endpoint)
        
        if not enable_bubble_detection or not ocr_regions:
                                                                      
            return {
                'regions': ocr_regions,
                'bubble_groups': [],
                'panel_boundaries': [],
                'detected_bubbles': []
            }
        
        try:
                                             
            from services.bubble_detection_service import bubble_detection_service
            
                                                              
            print(f"🔍 Detecting speech bubbles in {image_path}...")
            bubbles = bubble_detection_service.detect_bubbles(image_path, save_debug=False)
            print(f"✅ Found {len(bubbles)} speech bubbles")
            
                                                                                    
            print(f"🔍 Detecting panel boundaries...")
            panels = bubble_detection_service.detect_panels(image_path, bubbles=bubbles)
            print(f"✅ Found {len(panels)} panels")
            
                                             
            print(f"🔍 Grouping {len(ocr_regions)} text regions by structure...")
            grouped_data = bubble_detection_service.group_text_by_structure(
                ocr_regions, bubbles, panels, source_language,
                image_path=image_path, save_debug=False
            )
            print(f"✅ Created {len(grouped_data.get('bubble_groups', []))} text groups")
            
            return grouped_data
            
        except Exception as e:
            print(f"⚠️ Bubble detection failed, falling back to ungrouped results: {e}")
                                                                      
            return {
                'regions': ocr_regions,
                'bubble_groups': [],
                'panel_boundaries': [],
                'detected_bubbles': [],
                'error': str(e)
            }

                           
ocr_service = OCRService()

