

import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

DATA_DIR = 'data'
KEY_FILE = os.path.join(DATA_DIR, '.encryption_key')

def _get_or_create_key():

    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, 'rb') as f:
            return f.read()
    
    key = Fernet.generate_key()
    
    with open(KEY_FILE, 'wb') as f:
        f.write(key)
    
    try:
        os.chmod(KEY_FILE, 0o600)
    except:
        pass                                 
    
    return key

def encrypt_value(value):

    if not value:
        return ''
    
    try:
        key = _get_or_create_key()
        f = Fernet(key)
        
        encrypted = f.encrypt(value.encode('utf-8'))
        
        return base64.b64encode(encrypted).decode('utf-8')
    except Exception as e:
        return value                                       

def decrypt_value(encrypted_value):

    if not encrypted_value:
        return ''
    
    try:
        key = _get_or_create_key()
        f = Fernet(key)
        
        encrypted_bytes = base64.b64decode(encrypted_value.encode('utf-8'))
        
        decrypted = f.decrypt(encrypted_bytes)
        
        return decrypted.decode('utf-8')
    except Exception as e:
        return encrypted_value

def is_encrypted(value):

    if not value or len(value) < 50:
        return False
    
    try:
        base64.b64decode(value.encode('utf-8'))
        
        return len(value) > 50
    except:
        return False

def migrate_to_encrypted(plain_dict):

    encrypted_dict = {}
    
    for key, value in plain_dict.items():
        if isinstance(value, str) and value and not is_encrypted(value):
            encrypted_dict[key] = encrypt_value(value)
        else:
            encrypted_dict[key] = value
    
    return encrypted_dict

def decrypt_dict(encrypted_dict):

    decrypted_dict = {}
    
    for key, value in encrypted_dict.items():
        if isinstance(value, str) and value and is_encrypted(value):
            decrypted_dict[key] = decrypt_value(value)
        else:
            decrypted_dict[key] = value
    
    return decrypted_dict