

import requests
import json
from datetime import datetime, timedelta
from functools import lru_cache
import time
import re

PRICING_CACHE_DURATION = timedelta(hours=24)
_pricing_cache = {
    'data': None,
    'timestamp': None,
    'source': None
}

_keyed_pricing_cache = {}

def fetch_openrouter_pricing():

    try:
        response = requests.get(
            'https://openrouter.ai/api/v1/models',
            headers={
                'Content-Type': 'application/json'
            },
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            
            pricing_data = {}
            
            if 'data' in data:
                for model in data['data']:
                    model_id = model.get('id', '')
                    if not model_id:
                        continue
                    
                    pricing_info = model.get('pricing', {})
                    prompt_price_raw = pricing_info.get('prompt')
                    completion_price_raw = pricing_info.get('completion')
                    prompt_price = float(prompt_price_raw) if prompt_price_raw is not None else None
                    completion_price = float(completion_price_raw) if completion_price_raw is not None else None

                    pricing_data[model_id] = {
                        'pricing': {
                            'prompt': prompt_price,                                    
                            'completion': completion_price                                    
                        },
                        'context_length': model.get('context_length', 0),
                        'architecture': model.get('architecture', {}),
                        'name': model.get('name', model_id),
                        'raw': model
                    }
            
            return pricing_data
        else:
            return None
            
    except requests.exceptions.RequestException as e:
        return None
    except Exception as e:
        return None

def get_cached_openrouter_pricing():

    global _pricing_cache
    
    now = datetime.now()
    
    if (_pricing_cache['data'] is not None and 
        _pricing_cache['timestamp'] is not None and
        _pricing_cache['source'] == 'openrouter' and
        now - _pricing_cache['timestamp'] < PRICING_CACHE_DURATION):
        return _pricing_cache['data']
    
    pricing_data = fetch_openrouter_pricing()
    
    if pricing_data:
        _pricing_cache['data'] = pricing_data
        _pricing_cache['timestamp'] = now
        _pricing_cache['source'] = 'openrouter'
    
    return pricing_data

def get_cached_openrouter_pricing_with_key(api_key):

    global _keyed_pricing_cache

    if not api_key:
        return None

    import hashlib
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]

    now = datetime.now()

    if key_hash in _keyed_pricing_cache:
        cached = _keyed_pricing_cache[key_hash]
        if (cached.get('data') is not None and
            cached.get('timestamp') is not None and
            now - cached['timestamp'] < PRICING_CACHE_DURATION):
            return cached['data']

    pricing_data = fetch_openrouter_pricing_with_key(api_key)

    if pricing_data:
        _keyed_pricing_cache[key_hash] = {
            'data': pricing_data,
            'timestamp': now
        }

    return pricing_data

def normalize_model_name(name):

    if not name:
        return ''
    n = name.lower()
    n = re.sub(r'[-_]v?\d+(?:\.\d+)*$', '', n)
    n = re.sub(r'[-_]\d{1,4}$', '', n)
    return n

def strip_variants(name):

    if not name:
        return name
    n = re.sub(r'[-_]v?\d+(?:\.\d+)*$', '', name)
    n = re.sub(r'[-_](lite|flash|o1|r1|001)$', '', n)
    return n

def find_best_model_match(target_model, pricing_data):

    target = normalize_model_name(target_model)
    candidates = []
    
    for model_id, model_data in pricing_data.items():
        mid = normalize_model_name(model_id)
        
        if target == mid:
            candidates.append((0, model_id, model_data))
            continue

        if target in mid or mid in target:
            candidates.append((1, model_id, model_data))
            continue

        try:
            target_last = target.split('/')[-1]
            mid_last = mid.split('/')[-1]
            if target_last == mid_last or target_last in mid_last or mid_last in target_last:
                candidates.append((2, model_id, model_data))
                continue
        except Exception:
            pass

        try:
            if strip_variants(target) == strip_variants(mid):
                candidates.append((3, model_id, model_data))
                continue
        except Exception:
            pass

    if candidates:
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1], candidates[0][2]
    
    return None, None

def get_model_pricing(provider, model):

    try:
        from database.database import db_session_scope
        from database.db_models import GlobalModelPricing
        
        with db_session_scope() as session:
            global_pricing = session.query(GlobalModelPricing).filter(
                GlobalModelPricing.provider == provider,
                GlobalModelPricing.model_name == model
            ).first()
            
            if global_pricing:
                input_price = float(global_pricing.input_price_per_1m) / 1_000_000.0 if global_pricing.input_price_per_1m else None
                output_price = float(global_pricing.output_price_per_1m) / 1_000_000.0 if global_pricing.output_price_per_1m else None
                
                return {
                    'input_price': input_price,             
                    'output_price': output_price,             
                    'source': 'admin',
                    'available': True,
                    'model_name': model
                }
    except Exception as e:
        pass                                
    
    if provider == 'openrouter':
        pricing_data = get_cached_openrouter_pricing()
        
        if pricing_data:
            if model in pricing_data:
                model_pricing = pricing_data[model]
                return {
                    'input_price': model_pricing['pricing']['prompt'],
                    'output_price': model_pricing['pricing']['completion'],
                    'source': 'openrouter_api',
                    'available': True,
                    'model_name': model_pricing.get('name', model)
                }
            
            best_id, best_data = find_best_model_match(model, pricing_data)
            if best_data:
                return {
                    'input_price': best_data['pricing']['prompt'],
                    'output_price': best_data['pricing']['completion'],
                    'source': 'openrouter_api',
                    'available': True,
                    'model_name': best_data.get('name', best_id)
                }
    
    return {
        'input_price': None,
        'output_price': None,
        'source': None,
        'available': False
    }

def fetch_openrouter_pricing_with_key(api_key):

    if not api_key:
        return None

    try:
        response = requests.get(
            'https://openrouter.ai/api/v1/models',
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}'
            },
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            pricing_data = {}
            if 'data' in data:
                for model in data['data']:
                    model_id = model.get('id', '')
                    if not model_id:
                        continue
                    pricing_info = model.get('pricing', {})
                    prompt_price_raw = pricing_info.get('prompt')
                    completion_price_raw = pricing_info.get('completion')
                    prompt_price = float(prompt_price_raw) if prompt_price_raw is not None else None
                    completion_price = float(completion_price_raw) if completion_price_raw is not None else None
                    pricing_data[model_id] = {
                        'pricing': {
                            'prompt': prompt_price,            
                            'completion': completion_price            
                        },
                        'context_length': model.get('context_length', 0),
                        'architecture': model.get('architecture', {}),
                        'name': model.get('name', model_id),
                        'raw': model
                    }
            return pricing_data
        else:
            return None
    except requests.exceptions.RequestException as e:
        return None
    except Exception as e:
        return None

def fetch_openrouter_raw_with_key(api_key):

    if not api_key:
        return None

    try:
        response = requests.get(
            'https://openrouter.ai/api/v1/models',
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}'
            },
            timeout=10
        )

        try:
            data = response.json()
        except Exception:
            data = {'_raw_text': response.text}

        return {'status_code': response.status_code, 'json': data}
    except requests.exceptions.RequestException as e:
        return None
    except Exception as e:
        return None

def get_model_pricing_with_key(provider, model, api_key):

    if provider != 'openrouter' or not api_key:
        return {
            'input_price': None,
            'output_price': None,
            'source': None,
            'available': False
        }

    pricing_data = get_cached_openrouter_pricing_with_key(api_key)
    if not pricing_data:
        return {
            'input_price': None,
            'output_price': None,
            'source': None,
            'available': False
        }

    if model in pricing_data:
        model_pricing = pricing_data[model]
        return {
            'input_price': model_pricing['pricing']['prompt'],
            'output_price': model_pricing['pricing']['completion'],
            'source': 'openrouter_api',
            'available': True,
            'model_name': model_pricing.get('name', model)
        }
    
    best_id, best_data = find_best_model_match(model, pricing_data)
    if best_data:
        return {
            'input_price': best_data['pricing']['prompt'],
            'output_price': best_data['pricing']['completion'],
            'source': 'openrouter_api',
            'available': True,
            'model_name': best_data.get('name', best_id)
        }

    return {
        'input_price': None,
        'output_price': None,
        'source': None,
        'available': False
    }

def calculate_cost(input_tokens, output_tokens, provider, model):

    pricing = get_model_pricing(provider, model)
    
    if pricing and pricing.get('available'):
        input_price = pricing.get('input_price')
        output_price = pricing.get('output_price')
        
        if input_price is not None and output_price is not None:
            input_cost = input_tokens * float(input_price)
            output_cost = output_tokens * float(output_price)
            total_cost = input_cost + output_cost
            
            return {
                'input_cost': input_cost,
                'output_cost': output_cost,
                'total_cost': total_cost,
                'currency': 'USD',
                'pricing_available': True,
                'source': pricing.get('source', 'unknown')
            }
    
    return {
        'input_cost': None,
        'output_cost': None,
        'total_cost': None,
        'currency': 'USD',
        'pricing_available': False,
        'source': None
    }

def format_cost(cost_dict):

    if not cost_dict or not cost_dict.get('pricing_available'):
        return None
    
    total_cost = cost_dict.get('total_cost')
    if total_cost is None:
        return None
    
    currency = cost_dict.get('currency', 'USD')
    
    if total_cost < 0.01:
        return f"${total_cost:.4f}"
    elif total_cost < 1:
        return f"${total_cost:.3f}"
    else:
        return f"${total_cost:.2f}"

def refresh_pricing_cache():

    global _pricing_cache
    _pricing_cache['data'] = None
    _pricing_cache['timestamp'] = None
    _pricing_cache['source'] = None
    
    return get_cached_openrouter_pricing()