   

                                                                                     
            
                    
from PIL import Image, ImageDraw, ImageFont
from typing import List, Dict
import os

class ImageProcessingService:
                                                                             
    
    def __init__(self):
        self.default_font_path = self._get_default_font()
    
    def _get_default_font(self) -> str:
                                                           
                                   
        font_paths = [
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',         
            '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',                     
            '/System/Library/Fonts/Helvetica.ttc',         
            'C:\\Windows\\Fonts\\arial.ttf',           
            'C:\\Windows\\Fonts\\arialbd.ttf',                
        ]
        
        for path in font_paths:
            if os.path.exists(path):
                return path
        
                                 
        return None
    
    def remove_text(self, image_path: str, text_regions: List[Dict]):
                   
                                                                      
        try:
            import cv2
            import numpy as np
        except ImportError as e:
            raise ImportError(
                f"OpenCV (cv2) is required for image processing. "
                f"Install it with: pip install opencv-python-headless. "
                f"Also install system library: sudo apt-get install libgl1-mesa-glx libglib2.0-0. "
                f"Original error: {str(e)}"
            )
        
                    
        img = cv2.imread(image_path)
        
        if img is None:
            raise ValueError(f"Could not read image: {image_path}")
        
                                          
        mask = np.zeros(img.shape[:2], dtype=np.uint8)
        
        for region in text_regions:
            x, y, w, h = region['bbox']
                                          
            padding = 5
            x = max(0, int(x - padding))
            y = max(0, int(y - padding))
            w = min(img.shape[1] - x, int(w + 2 * padding))
            h = min(img.shape[0] - y, int(h + 2 * padding))
            
                              
            cv2.rectangle(mask, (x, y), (x + w, y + h), 255, -1)
        
                                                                           
        inpainted = cv2.inpaint(img, mask, inpaintRadius=7, flags=cv2.INPAINT_TELEA)
        
        return inpainted
    
    def render_text(self, image, translated_regions: List[Dict], 
                   output_path: str) -> str:
                   
                                                            
        try:
            import cv2
        except ImportError as e:
            raise ImportError(
                f"OpenCV (cv2) is required for image processing. "
                f"Install it with: pip install opencv-python-headless. "
                f"Also install system library: sudo apt-get install libgl1-mesa-glx libglib2.0-0. "
                f"Original error: {str(e)}"
            )
        
                                           
        img_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(img_rgb)
        draw = ImageDraw.Draw(pil_img)
        
        for region in translated_regions:
            text = region['text']
            x, y, w, h = region['bbox']
            
                                                         
            font_size = self._calculate_font_size(text, w, h)
            
            try:
                if self.default_font_path:
                    font = ImageFont.truetype(self.default_font_path, font_size)
                else:
                    font = ImageFont.load_default()
            except:
                font = ImageFont.load_default()
            
                                         
            wrapped_text = self._wrap_text(text, font, w, draw)
            
                                                      
            bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            text_x = int(x + (w - text_width) // 2)
            text_y = int(y + (h - text_height) // 2)
            
                                                           
                                  
            outline_range = 2
            for adj_x in range(-outline_range, outline_range + 1):
                for adj_y in range(-outline_range, outline_range + 1):
                    if adj_x == 0 and adj_y == 0:
                        continue
                    draw.multiline_text(
                        (text_x + adj_x, text_y + adj_y),
                        wrapped_text,
                        font=font,
                        fill='black',
                        align='center'
                    )
            
                               
            draw.multiline_text(
                (text_x, text_y),
                wrapped_text,
                font=font,
                fill='white',
                align='center'
            )
        
                                                 
        try:
            import cv2
            import numpy as np
        except ImportError as e:
            raise ImportError(
                f"OpenCV (cv2) and numpy are required for image processing. "
                f"Install them with: pip install opencv-python-headless numpy. "
                f"Also install system library: sudo apt-get install libgl1-mesa-glx libglib2.0-0. "
                f"Original error: {str(e)}"
            )
        final_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        cv2.imwrite(output_path, final_img)
        
        return output_path
    
    def _calculate_font_size(self, text: str, width: int, height: int) -> int:
                                                                  
                                                                               
        base_size = int(height * 0.9)
        
                                                         
        chars_per_line = max(1, width // (base_size * 0.5))
        lines_needed = len(text) // chars_per_line + 1
        
        if lines_needed > 1:
            adjusted_size = int(height / (lines_needed * 1.1))
            return min(base_size, adjusted_size)
        
                                                                    
        return max(24, min(base_size, 120))                                        
    
    def _wrap_text(self, text: str, font: ImageFont, max_width: int, 
                   draw: ImageDraw) -> str:
                                               
        words = text.split()
        lines = []
        current_line = []
        
        for word in words:
            current_line.append(word)
            test_line = ' '.join(current_line)
            bbox = draw.textbbox((0, 0), test_line, font=font)
            line_width = bbox[2] - bbox[0]
            
            if line_width > max_width and len(current_line) > 1:
                                                
                current_line.pop()
                lines.append(' '.join(current_line))
                current_line = [word]
        
        if current_line:
            lines.append(' '.join(current_line))
        
        return '\n'.join(lines)
    
    def process_image(self, image_path: str, ocr_results: List[Dict], 
                     translated_results: List[Dict], output_path: str, 
                     overwrite_text: bool = True) -> str:
                   
        if overwrite_text:
                                          
            inpainted_img = self.remove_text(image_path, ocr_results)
            
                                            
            final_path = self.render_text(inpainted_img, translated_results, output_path)
        else:
                                                              
                                                                    
            import shutil
            shutil.copy2(image_path, output_path)
            final_path = output_path
        
        return final_path

                           
image_processing_service = ImageProcessingService()

