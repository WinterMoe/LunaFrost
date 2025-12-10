import ipaddress
from urllib.parse import urlparse
import socket

ALLOWED_DOMAINS = [
    'novelpia.com',
    'images.novelpia.com',
    'www.novelpia.com'
]

BLOCKED_IP_RANGES = [
    ipaddress.ip_network('127.0.0.0/8'),
    ipaddress.ip_network('10.0.0.0/8'),
    ipaddress.ip_network('172.16.0.0/12'),
    ipaddress.ip_network('192.168.0.0/16'),
    ipaddress.ip_network('169.254.0.0/16'),
    ipaddress.ip_network('::1/128'),
    ipaddress.ip_network('fe80::/10'),
]

def is_safe_url(url):
    try:
        parsed = urlparse(url)
        
        if not parsed.scheme in ['http', 'https']:
            return False, "Only HTTP and HTTPS protocols are allowed"
        
        hostname = parsed.hostname
        if not hostname:
            return False, "Invalid URL: missing hostname"
        
        if hostname not in ALLOWED_DOMAINS:
            return False, f"Domain {hostname} is not in the whitelist"
        
        try:
            ip = socket.gethostbyname(hostname)
            ip_addr = ipaddress.ip_address(ip)
            
            for blocked_range in BLOCKED_IP_RANGES:
                if ip_addr in blocked_range:
                    return False, f"IP address {ip} is in blocked range"
        except socket.gaierror:
            return False, "Could not resolve hostname"
        except ValueError:
            return False, "Invalid IP address"
        
        return True, "URL is safe"
    
    except Exception as e:
        return False, f"URL validation error: {str(e)}"
