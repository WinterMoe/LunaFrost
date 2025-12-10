   

from typing import List, Dict, Tuple, Optional
import os

class BubbleDetectionService:
                                                                             
    
    def __init__(self):
        self._cv2 = None
        self._np = None
    
    def _ensure_cv2(self):
                                                                       
        if self._cv2 is None:
            try:
                import cv2
                import numpy as np
                self._cv2 = cv2
                self._np = np
            except ImportError as e:
                raise ImportError(f"OpenCV (cv2) or numpy not installed: {e}")
    
    def detect_bubbles(self, image_path: str, save_debug: bool = False) -> List[Dict]:
                   
        self._ensure_cv2()
        cv2 = self._cv2
        np = self._np
        
                    
        image = cv2.imread(image_path)
        if image is None:
            print(f"Warning: Could not load image for bubble detection: {image_path}")
            return []
        
        height, width = image.shape[:2]
        image_area = height * width
        
                              
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
                                                                             
                                                                  
        _, thresh = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY)
        
                                                                        
        _, thresh_lower = cv2.threshold(gray, 220, 255, cv2.THRESH_BINARY)
        
                                 
        combined_thresh = cv2.bitwise_or(thresh, thresh_lower)
        
                                                       
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        
                                         
        closed = cv2.morphologyEx(combined_thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
        
                                    
        opened = cv2.morphologyEx(closed, cv2.MORPH_OPEN, kernel, iterations=1)
        
                       
        contours, _ = cv2.findContours(opened, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        bubbles = []
        bubble_id = 0
        
                                     
        for contour in contours:
            area = cv2.contourArea(contour)
            
                                    
            x, y, w, h = cv2.boundingRect(contour)
            
                                                          
            min_area = 500
            max_area = image_area * 0.4                                            
            
            if area < min_area or area > max_area:
                continue
            
                                    
            aspect_ratio = w / h if h > 0 else 0
            if aspect_ratio < 0.1 or aspect_ratio > 10:
                continue
            
                                                      
            hull = cv2.convexHull(contour)
            hull_area = cv2.contourArea(hull)
            
            solidity = 1.0
            if hull_area > 0:
                solidity = area / hull_area
                if solidity < 0.4:
                    continue
            
                                                        
            if w < 20 or h < 20:
                continue
            
            bubbles.append({
                'bubble_id': bubble_id,
                'bbox': [x, y, w, h],
                'area': area,
                'solidity': solidity if hull_area > 0 else 1.0,
                'contour_points': contour.tolist()                           
            })
            
            bubble_id += 1
        
                                                                                        
        bubbles.sort(key=lambda b: (b['bbox'][1], b['bbox'][0]))
        
                                    
        for i, bubble in enumerate(bubbles):
            bubble['bubble_id'] = i
        
        return bubbles
    
    def detect_panels(self, image_path: str, bubbles: List[Dict] = None) -> List[Dict]:
                   
        self._ensure_cv2()
        cv2 = self._cv2
        np = self._np
        
                    
        image = cv2.imread(image_path)
        if image is None:
            print(f"Warning: Could not load image for panel detection: {image_path}")
            return []
        
        height, width = image.shape[:2]
        image_area = height * width
        
                              
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
                                        
                                                                              
        _, white_mask = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY)
        
                                                                      
        vertical_gutter_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, height // 5))
        vertical_gutters = cv2.morphologyEx(white_mask, cv2.MORPH_OPEN, vertical_gutter_kernel)
        
                                                                        
        horizontal_gutter_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (width // 5, 1))
        horizontal_gutters = cv2.morphologyEx(white_mask, cv2.MORPH_OPEN, horizontal_gutter_kernel)
        
                         
        white_gutters = cv2.bitwise_or(vertical_gutters, horizontal_gutters)
        
                                                                  
        gutter_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        white_gutters = cv2.dilate(white_gutters, gutter_kernel, iterations=2)
        
                                      
                                    
        edges = cv2.Canny(gray, 50, 150)
        
                                              
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        dilated = cv2.dilate(edges, kernel, iterations=2)
        
                                                                           
                          
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (width // 10, 1))
        horizontal_lines = cv2.morphologyEx(dilated, cv2.MORPH_OPEN, horizontal_kernel)
        
                        
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, height // 10))
        vertical_lines = cv2.morphologyEx(dilated, cv2.MORPH_OPEN, vertical_kernel)
        
                             
        black_lines = cv2.bitwise_or(horizontal_lines, vertical_lines)
        
                                         
                                                           
        diagonal_mask = np.zeros_like(gray)
        hough_lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=80, 
                                       minLineLength=min(width, height) // 6, 
                                       maxLineGap=15)
        
        if hough_lines is not None:
            for line in hough_lines:
                x1, y1, x2, y2 = line[0]
                                 
                angle = abs(np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi)
                                                                                     
                                                               
                line_length = np.sqrt((x2 - x1)**2 + (y2 - y1)**2)
                if line_length > min(width, height) // 8:
                    cv2.line(diagonal_mask, (x1, y1), (x2, y2), 255, 3)
        
                                        
                                                                
        all_separators = cv2.bitwise_or(black_lines, white_gutters)
        all_separators = cv2.bitwise_or(all_separators, diagonal_mask)
        
                                        
                                                             
                                                                 
        if bubbles:
            bubble_mask = np.zeros_like(gray)
            for bubble in bubbles:
                bx, by, bw, bh = bubble['bbox']
                                                            
                padding = 5
                cv2.rectangle(bubble_mask, 
                            (max(0, bx - padding), max(0, by - padding)), 
                            (min(width, bx + bw + padding), min(height, by + bh + padding)), 
                            255, -1)
            
                                                     
                                                                                  
            all_separators = cv2.bitwise_and(all_separators, cv2.bitwise_not(bubble_mask))
        
                                                
        contours, _ = cv2.findContours(all_separators, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
                                                                           
        if len(contours) == 0:
            return [{
                'panel_id': 0,
                'bbox': [0, 0, width, height]
            }]
        
                                                                      
                                         
        separator_mask = cv2.dilate(all_separators, kernel, iterations=3)
        inverted = cv2.bitwise_not(separator_mask)
        
                                                   
        panel_contours, _ = cv2.findContours(inverted, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        panels = []
        min_panel_area = image_area * 0.01                        
        max_panel_area = image_area * 0.95                                              
        
        for contour in panel_contours:
            area = cv2.contourArea(contour)
            
            if area < min_panel_area or area > max_panel_area:
                continue
            
            x, y, w, h = cv2.boundingRect(contour)
            
                                      
            if w < 50 or h < 50:
                continue
            
            panels.append({
                'bbox': [x, y, w, h],
                'area': area
            })
        
                                                            
        if len(panels) == 0:
            return [{
                'panel_id': 0,
                'bbox': [0, 0, width, height]
            }]
        
                                                                        
        panels = self._remove_overlapping_panels(panels)
        
                                                                    
                                                                                            
        if bubbles:
            panels = self._filter_bubble_like_panels(panels, bubbles, image_area)
        
                                                                   
                                                                              
        panels = self._remove_nested_small_panels(panels, image_area)
        
                                                                               
        panels.sort(key=lambda p: (p['bbox'][1], -p['bbox'][0]))
        
                                  
        for i, panel in enumerate(panels):
            panel['panel_id'] = i
        
        return panels
    
    def _remove_overlapping_panels(self, panels: List[Dict]) -> List[Dict]:
                   
        if len(panels) <= 1:
            return panels
        
                                                                    
        sorted_panels = sorted(panels, key=lambda p: p['area'])
        
                                                 
                                                                 
        final_panels = []
        
        for panel in sorted_panels:
            px, py, pw, ph = panel['bbox']
            
                                                                             
                                                                                 
            
                                                                                   
            clipped_bbox = self._clip_panel_against_others(panel['bbox'], final_panels)
            
            if clipped_bbox is None:
                                                           
                continue
            
                                                
            cx, cy, cw, ch = clipped_bbox
            if cw > 30 and ch > 30:                                       
                panel['bbox'] = clipped_bbox
                panel['area'] = cw * ch
                final_panels.append(panel)
        
        return final_panels
    
    def _clip_panel_against_others(self, bbox: List[int], other_panels: List[Dict]) -> Optional[List[int]]:
                   
        x, y, w, h = bbox
        
        for other in other_panels:
            ox, oy, ow, oh = other['bbox']
            
                                          
            if not (x < ox + ow and x + w > ox and y < oy + oh and y + h > oy):
                continue              
            
                                                      
                                      
            overlap_left = max(x, ox)
            overlap_right = min(x + w, ox + ow)
            overlap_top = max(y, oy)
            overlap_bottom = min(y + h, oy + oh)
            
            overlap_w = overlap_right - overlap_left
            overlap_h = overlap_bottom - overlap_top
            
            if overlap_w <= 0 or overlap_h <= 0:
                continue                     
            
                                                                         
                                                                
            
                                                                               
            other_center_x = ox + ow / 2
            other_center_y = oy + oh / 2
            my_center_x = x + w / 2
            my_center_y = y + h / 2
            
            dx = other_center_x - my_center_x
            dy = other_center_y - my_center_y
            
                                                                                 
            if abs(dx) > abs(dy):
                                                               
                if dx > 0:
                                                                       
                    new_w = ox - x
                    if new_w > 30:
                        w = new_w
                else:
                                                                     
                    new_x = ox + ow
                    new_w = (x + w) - new_x
                    if new_w > 30:
                        x = new_x
                        w = new_w
            else:
                                                         
                if dy > 0:
                                                                 
                    new_h = oy - y
                    if new_h > 30:
                        h = new_h
                else:
                                                              
                    new_y = oy + oh
                    new_h = (y + h) - new_y
                    if new_h > 30:
                        y = new_y
                        h = new_h
        
                                            
        if w <= 30 or h <= 30:
            return None
        
        return [x, y, w, h]
    
    def _filter_bubble_like_panels(self, panels: List[Dict], bubbles: List[Dict], image_area: float) -> List[Dict]:
                   
        filtered = []
        
        for panel in panels:
            is_bubble = False
            panel_area = panel['area']
            
            for bubble in bubbles:
                overlap = self._rect_overlap(panel['bbox'], bubble['bbox'])
                reverse_overlap = self._rect_overlap(bubble['bbox'], panel['bbox'])
                
                                                                                       
                if overlap > 0.6 or reverse_overlap > 0.6:
                    is_bubble = True
                    break
                
                                                                                       
                if overlap > 0.3 and abs(panel_area - bubble['area']) / max(panel_area, bubble['area']) < 0.5:
                    is_bubble = True
                    break
            
            if not is_bubble:
                filtered.append(panel)
        
        return filtered
    
    def _remove_nested_small_panels(self, panels: List[Dict], image_area: float) -> List[Dict]:
                   
        if len(panels) <= 1:
            return panels
        
                                                                                                  
        small_threshold = image_area * 0.15
        
        kept_panels = []
        
        for panel in panels:
            is_nested_small = False
            
                                                                         
            if panel['area'] < small_threshold:
                for other in panels:
                    if other is panel:
                        continue
                    
                                                          
                    px, py, pw, ph = panel['bbox']
                    ox, oy, ow, oh = other['bbox']
                    
                                                                                    
                    if (px >= ox and py >= oy and 
                        px + pw <= ox + ow and py + ph <= oy + oh):
                        is_nested_small = True
                        break
            
            if not is_nested_small:
                kept_panels.append(panel)
        
        return kept_panels
    
    def _point_in_rect(self, point: Tuple[int, int], bbox: List[int]) -> bool:
                                                       
        x, y = point
        bx, by, bw, bh = bbox
        return bx <= x <= bx + bw and by <= y <= by + bh
    
    def _rect_overlap(self, bbox1: List[int], bbox2: List[int]) -> float:
                                                                
        x1, y1, w1, h1 = bbox1
        x2, y2, w2, h2 = bbox2
        
                                
        ix1 = max(x1, x2)
        iy1 = max(y1, y2)
        ix2 = min(x1 + w1, x2 + w2)
        iy2 = min(y1 + h1, y2 + h2)
        
        if ix2 <= ix1 or iy2 <= iy1:
            return 0.0
        
        intersection = (ix2 - ix1) * (iy2 - iy1)
        area1 = w1 * h1
        
        return intersection / area1 if area1 > 0 else 0.0
    
    def _get_panel_for_region(self, region_bbox: List[int], panels: List[Dict]) -> Optional[int]:
                                                       
        if not panels:
            return None
        
                                    
        rx, ry, rw, rh = region_bbox
        center_x = rx + rw // 2
        center_y = ry + rh // 2
        
                                          
        for panel in panels:
            if self._point_in_rect((center_x, center_y), panel['bbox']):
                return panel['panel_id']
        
                                                                  
        best_panel = None
        best_overlap = 0
        
        for panel in panels:
            overlap = self._rect_overlap(region_bbox, panel['bbox'])
            if overlap > best_overlap:
                best_overlap = overlap
                best_panel = panel['panel_id']
        
        return best_panel
    
    def _get_bubble_for_region(self, region_bbox: List[int], bubbles: List[Dict]) -> Optional[int]:
                                                        
        if not bubbles:
            return None
        
                                    
        rx, ry, rw, rh = region_bbox
        center_x = rx + rw // 2
        center_y = ry + rh // 2
        
                                           
        for bubble in bubbles:
            if self._point_in_rect((center_x, center_y), bubble['bbox']):
                return bubble['bubble_id']
        
                                                                    
        best_bubble = None
        best_overlap = 0.3                                
        
        for bubble in bubbles:
            overlap = self._rect_overlap(region_bbox, bubble['bbox'])
            if overlap > best_overlap:
                best_overlap = overlap
                best_bubble = bubble['bubble_id']
        
        return best_bubble
    
    def group_text_by_structure(self, ocr_regions: List[Dict], 
                                 bubbles: List[Dict], 
                                 panels: List[Dict],
                                 source_language: str = 'korean',
                                 image_path: str = None,
                                 save_debug: bool = False) -> Dict:
                   
        if not ocr_regions:
            return {
                'regions': [],
                'bubble_groups': [],
                'panel_boundaries': panels
            }
        
        is_japanese = source_language == 'japanese'
        
                                                              
        for region in ocr_regions:
            region['panel_id'] = self._get_panel_for_region(region['bbox'], panels)
            region['bubble_id'] = self._get_bubble_for_region(region['bbox'], bubbles)
        
                                                           
                                   
        regions_by_panel = {}
        for i, region in enumerate(ocr_regions):
            panel_id = region.get('panel_id')
            if panel_id not in regions_by_panel:
                regions_by_panel[panel_id] = []
            regions_by_panel[panel_id].append(i)
        
                                                              
        all_groups = []
        group_id = 0
        
        for panel_id, region_indices in regions_by_panel.items():
                                                    
            panel_groups = self._group_nearby_text_in_panel(
                ocr_regions, region_indices, is_japanese
            )
            
            for group_indices in panel_groups:
                                                        
                min_x = min(ocr_regions[i]['bbox'][0] for i in group_indices)
                min_y = min(ocr_regions[i]['bbox'][1] for i in group_indices)
                max_x = max(ocr_regions[i]['bbox'][0] + ocr_regions[i]['bbox'][2] for i in group_indices)
                max_y = max(ocr_regions[i]['bbox'][1] + ocr_regions[i]['bbox'][3] for i in group_indices)
                
                                                                
                sorted_indices = sorted(group_indices, key=lambda i: (
                    ocr_regions[i]['bbox'][1],                              
                    -ocr_regions[i]['bbox'][0] if is_japanese else ocr_regions[i]['bbox'][0]
                ))
                
                all_groups.append({
                    'bubble_id': group_id,
                    'region_indices': sorted_indices,
                    'panel_id': panel_id,
                    'bbox': [min_x, min_y, max_x - min_x, max_y - min_y],
                    'is_ungrouped': len(group_indices) == 1
                })
                group_id += 1
        
                                                                                   
        all_groups.sort(key=lambda g: (
            g['bbox'][1] if g['bbox'] else 0,
            -g['bbox'][0] if is_japanese and g['bbox'] else (g['bbox'][0] if g['bbox'] else 0)
        ))
        
                                           
        for i, group in enumerate(all_groups):
            group['bubble_id'] = i
        
        return {
            'regions': ocr_regions,
            'bubble_groups': all_groups,
            'panel_boundaries': panels,
            'detected_bubbles': bubbles
        }
    
    def _group_nearby_text_in_panel(self, ocr_regions: List[Dict], 
                                     region_indices: List[int],
                                     is_japanese: bool) -> List[List[int]]:
                   
        if not region_indices:
            return []
        
        if len(region_indices) == 1:
            return [region_indices]
        
                                                                      
                                                                                                    
        HORIZONTAL_THRESHOLD = 80                                         
        VERTICAL_THRESHOLD = 50                                    
        MAX_VERTICAL_DISTANCE = 100                                                 
                                                                          
        SINGLE_CHAR_WIDTH = 50
        SINGLE_CHAR_HEIGHT = 90
        
                                                
        parent = {i: i for i in region_indices}
        
        def find(x):
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]
        
        def union(x, y):
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py
        
                                                  
        for i, idx1 in enumerate(region_indices):
            bbox1 = ocr_regions[idx1]['bbox']
            x1, y1, w1, h1 = bbox1
            center_x1 = x1 + w1 / 2
            center_y1 = y1 + h1 / 2
            bubble1 = ocr_regions[idx1].get('bubble_id')
            
            for idx2 in region_indices[i + 1:]:
                bbox2 = ocr_regions[idx2]['bbox']
                x2, y2, w2, h2 = bbox2
                center_x2 = x2 + w2 / 2
                center_y2 = y2 + h2 / 2
                bubble2 = ocr_regions[idx2].get('bubble_id')
                
                                     
                                                    
                if x1 + w1 < x2:
                    h_dist = x2 - (x1 + w1)
                elif x2 + w2 < x1:
                    h_dist = x1 - (x2 + w2)
                else:
                    h_dist = 0                            
                
                                                  
                if y1 + h1 < y2:
                    v_dist = y2 - (y1 + h1)
                elif y2 + h2 < y1:
                    v_dist = y1 - (y2 + h2)
                else:
                    v_dist = 0                          
                
                                                                       
                if bubble1 is not None and bubble2 is not None and bubble1 != bubble2:
                    continue
                
                                                    
                should_group = False
                
                                                                               
                if h_dist < HORIZONTAL_THRESHOLD and v_dist < MAX_VERTICAL_DISTANCE:
                    horizontal_alignment = abs(center_x1 - center_x2) < max(w1, w2) * 1.5
                    if horizontal_alignment:
                        should_group = True
                
                                                               
                if v_dist < VERTICAL_THRESHOLD and h_dist < HORIZONTAL_THRESHOLD:
                    should_group = True
                
                                                   
                if h_dist < 20 and v_dist < 20:
                    should_group = True
                
                                             
                overlap = self._rect_overlap(bbox1, bbox2)
                reverse_overlap = self._rect_overlap(bbox2, bbox1)
                if overlap > 0.3 or reverse_overlap > 0.3:
                    should_group = True

                                                                          
                if max(w1, w2) <= SINGLE_CHAR_WIDTH and max(h1, h2) <= SINGLE_CHAR_HEIGHT:
                    same_line = v_dist < max(h1, h2) * 0.6
                    close_inline = h_dist < max(w1, w2) * 3
                    if same_line and close_inline:
                        should_group = True
                
                if should_group:
                    union(idx1, idx2)
        
                        
        groups = {}
        for idx in region_indices:
            root = find(idx)
            if root not in groups:
                groups[root] = []
            groups[root].append(idx)
        
        return list(groups.values())
    

                    
bubble_detection_service = BubbleDetectionService()

