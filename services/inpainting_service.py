   

import os
import subprocess
import time
import requests
from typing import List, Dict, Optional, Tuple
from PIL import Image
import io
import base64

class InpaintingService:
                                                                           
    
    def __init__(self):
        self._cv2 = None
        self._np = None
        self._iopaint_process = None
        self._iopaint_port = 8081
        self._iopaint_ready = False
    
    def _ensure_cv2(self):
                                         
        if self._cv2 is None:
            try:
                import cv2
                import numpy as np
                self._cv2 = cv2
                self._np = np
            except ImportError as e:
                raise ImportError(
                    f"OpenCV (cv2) is required for inpainting. "
                    f"Install with: pip install opencv-python-headless. "
                    f"Error: {str(e)}"
                )
    
    def inpaint_opencv(self, image_path: str, regions: List[Dict], 
                       output_path: str, padding: int = 5) -> str:
                   
        self._ensure_cv2()
        cv2 = self._cv2
        np = self._np
        
                    
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Could not read image: {image_path}")
        
        h, w = img.shape[:2]
        
                                          
        mask = np.zeros((h, w), dtype=np.uint8)
        
        for region in regions:
            bbox = region.get('bbox', region.get('region', []))
            if not bbox or len(bbox) < 4:
                continue
                
            x, y, rw, rh = bbox
                           
            x1 = max(0, int(x - padding))
            y1 = max(0, int(y - padding))
            x2 = min(w, int(x + rw + padding))
            y2 = min(h, int(y + rh + padding))
            
                                                     
            cv2.rectangle(mask, (x1, y1), (x2, y2), 255, -1)
        
                                       
        inpainted = cv2.inpaint(img, mask, inpaintRadius=7, flags=cv2.INPAINT_TELEA)
        
                     
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        cv2.imwrite(output_path, inpainted)
        
        return output_path
    
    def _start_iopaint_server(self) -> bool:
                                                          
        if self._iopaint_ready:
            return True
            
                                  
        try:
            response = requests.get(f"http://localhost:{self._iopaint_port}/api/v1/model", timeout=2)
            if response.status_code == 200:
                self._iopaint_ready = True
                print(f"✅ IOPaint server already running on port {self._iopaint_port}")
                return True
        except:
            pass
        
                                 
        try:
            print(f"🚀 Starting IOPaint server on port {self._iopaint_port}...")
            self._iopaint_process = subprocess.Popen(
                [
                    'iopaint', 'start',
                    '--model=lama',
                    f'--port={self._iopaint_port}',
                    '--device=cpu',
                    '--disable-model-switch'
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
                                                            
            for i in range(30):
                time.sleep(1)
                try:
                    response = requests.get(f"http://localhost:{self._iopaint_port}/api/v1/model", timeout=2)
                    if response.status_code == 200:
                        self._iopaint_ready = True
                        print(f"✅ IOPaint server ready after {i+1} seconds")
                        return True
                except:
                    pass
            
            print("❌ IOPaint server failed to start within 30 seconds")
            return False
            
        except FileNotFoundError:
            print("❌ IOPaint not installed. Install with: pip install iopaint")
            return False
        except Exception as e:
            print(f"❌ Failed to start IOPaint: {e}")
            return False
    
    def inpaint_lama(self, image_path: str, regions: List[Dict], 
                     output_path: str, padding: int = 5) -> str:
                   
                                        
        if not self._start_iopaint_server():
                                                    
            print("⚠️ Falling back to OpenCV inpainting")
            return self.inpaint_opencv(image_path, regions, output_path, padding)
        
        self._ensure_cv2()
        cv2 = self._cv2
        np = self._np
        
                    
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Could not read image: {image_path}")
        
        h, w = img.shape[:2]
        
                                          
        mask = np.zeros((h, w), dtype=np.uint8)
        
        for region in regions:
            bbox = region.get('bbox', region.get('region', []))
            if not bbox or len(bbox) < 4:
                continue
                
            x, y, rw, rh = bbox
            x1 = max(0, int(x - padding))
            y1 = max(0, int(y - padding))
            x2 = min(w, int(x + rw + padding))
            y2 = min(h, int(y + rh + padding))
            cv2.rectangle(mask, (x1, y1), (x2, y2), 255, -1)
        
                                   
        _, img_encoded = cv2.imencode('.png', img)
        img_base64 = base64.b64encode(img_encoded).decode('utf-8')
        
        _, mask_encoded = cv2.imencode('.png', mask)
        mask_base64 = base64.b64encode(mask_encoded).decode('utf-8')
        
                          
        try:
            response = requests.post(
                f"http://localhost:{self._iopaint_port}/api/v1/inpaint",
                json={
                    "image": f"data:image/png;base64,{img_base64}",
                    "mask": f"data:image/png;base64,{mask_base64}"
                },
                timeout=60                                
            )
            
            if response.status_code == 200:
                               
                result_data = response.json()
                result_base64 = result_data.get('image', '').split(',')[-1]
                result_bytes = base64.b64decode(result_base64)
                
                             
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, 'wb') as f:
                    f.write(result_bytes)
                
                return output_path
            else:
                print(f"❌ IOPaint API error: {response.status_code}")
                return self.inpaint_opencv(image_path, regions, output_path, padding)
                
        except Exception as e:
            print(f"❌ IOPaint request failed: {e}")
            return self.inpaint_opencv(image_path, regions, output_path, padding)
    
    def clean_text(self, image_path: str, regions: List[Dict], 
                   output_path: str, method: str = 'opencv') -> str:
                   
        if not regions:
                                                      
            import shutil
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            shutil.copy2(image_path, output_path)
            return output_path
        
        if method == 'lama':
            return self.inpaint_lama(image_path, regions, output_path)
        else:
            return self.inpaint_opencv(image_path, regions, output_path)
    
    def cleanup(self):
                                             
        if self._iopaint_process:
            self._iopaint_process.terminate()
            self._iopaint_process = None
            self._iopaint_ready = False

                    
inpainting_service = InpaintingService()
