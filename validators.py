#!/usr/bin/env python3
"""
Deterministic validation and normalization functions for network inventory data.
"""

import re
import ipaddress
from typing import Tuple, Optional


def validate_and_normalize_ip(ip_str: str) -> Tuple[bool, Optional[str], str, str]:
    """
    Validate and normalize IP address (IPv4 or IPv6).
    
    Returns:
        (is_valid, normalized_ip, ip_version, reason)
    """
    if ip_str is None or ip_str == "" or str(ip_str).strip().upper() == "N/A":
        return (False, None, "", "missing")
    
    s = str(ip_str).strip()
    
    # Try IPv4 first
    if ":" not in s and "%" not in s:
        parts = s.split(".")
        if len(parts) == 4:
            canonical_parts = []
            for p in parts:
                if p == "":
                    return (False, None, "", "empty_octet")
                if not (p.lstrip("+").isdigit() and not p.startswith("-")):
                    return (False, None, "", "non_numeric_or_negative")
                try:
                    v = int(p, 10)
                except ValueError:
                    return (False, None, "", "non_decimal_format")
                if v < 0 or v > 255:
                    return (False, None, "", "octet_out_of_range")
                canonical_parts.append(str(v))
            canonical = ".".join(canonical_parts)
            return (True, canonical, "4", "ok")
        elif len(parts) < 4:
            return (False, None, "", "wrong_part_count")
        else:
            return (False, None, "", "too_many_parts")
    
    # Try IPv6
    if ":" in s:
        # Remove zone identifier if present
        if "%" in s:
            s = s.split("%")[0]
        try:
            ip_obj = ipaddress.IPv6Address(s)
            canonical = ip_obj.compressed.lower()
            return (True, canonical, "6", "ok")
        except (ipaddress.AddressValueError, ValueError):
            return (False, None, "", "invalid_ipv6_format")
    
    return (False, None, "", "unknown_format")


def classify_ipv4_type(ip: str) -> str:
    """Classify IPv4 address type."""
    o = list(map(int, ip.split(".")))
    if o[0] == 10:
        return "private_rfc1918"
    if o[0] == 172 and 16 <= o[1] <= 31:
        return "private_rfc1918"
    if o[0] == 192 and o[1] == 168:
        return "private_rfc1918"
    if o[0] == 169 and o[1] == 254:
        return "link_local_apipa"
    if o[0] == 127:
        return "loopback"
    return "public_or_other"


def derive_subnet_cidr(ip: str, ip_version: str) -> str:
    """Derive subnet CIDR from IP address."""
    if not ip or ip_version != "4":
        return ""
    
    try:
        iptype = classify_ipv4_type(ip)
        if iptype == "private_rfc1918":
            parts = list(map(int, ip.split(".")))
            return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
        elif iptype == "link_local_apipa":
            return "169.254.0.0/16"
        elif iptype == "loopback":
            return "127.0.0.0/8"
        # For public IPs, use /32 (host route)
        return f"{ip}/32"
    except (ValueError, IndexError):
        return ""


def generate_reverse_ptr(ip: str, ip_version: str) -> str:
    """Generate reverse PTR record for IP address."""
    if not ip or ip_version not in ["4", "6"]:
        return ""
    
    try:
        if ip_version == "4":
            parts = ip.split(".")
            return f"{parts[3]}.{parts[2]}.{parts[1]}.{parts[0]}.in-addr.arpa"
        else:  # IPv6
            ip_obj = ipaddress.IPv6Address(ip)
            # Expand to full form and reverse nibbles
            expanded = ip_obj.exploded.replace(":", "")
            reversed_nibbles = ".".join(reversed(expanded))
            return f"{reversed_nibbles}.ip6.arpa"
    except (ValueError, AttributeError):
        return ""


def validate_and_normalize_mac(mac_str: str) -> Tuple[bool, Optional[str], str]:
    """
    Validate and normalize MAC address.
    
    Returns:
        (is_valid, normalized_mac, reason)
    """
    if mac_str is None or mac_str == "":
        return (False, None, "missing")
    
    s = str(mac_str).strip().upper()
    
    # Remove all separators
    clean = re.sub(r'[-:.]', '', s)
    
    # Check if it's valid hex and correct length
    if not re.match(r'^[0-9A-F]{12}$', clean):
        return (False, None, "invalid_format")
    
    # Reconstruct with colon separators
    normalized = ":".join([clean[i:i+2] for i in range(0, 12, 2)])
    return (True, normalized, "ok")


def validate_and_normalize_hostname(hostname_str: str) -> Tuple[bool, Optional[str], str]:
    """
    Validate and normalize hostname according to RFC 1123.
    
    Returns:
        (is_valid, normalized_hostname, reason)
    """
    if hostname_str is None or hostname_str == "":
        return (False, None, "missing")
    
    s = str(hostname_str).strip()
    
    # Basic length check
    if len(s) == 0:
        return (False, None, "empty")
    if len(s) > 63:
        return (False, None, "too_long")
    
    # Convert to lowercase
    normalized = s.lower()
    
    # Check for valid characters (RFC 1123: a-z, 0-9, -)
    if not re.match(r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?$', normalized):
        # Try to clean invalid characters
        cleaned = re.sub(r'[^a-z0-9-]', '-', normalized)
        cleaned = re.sub(r'-+', '-', cleaned)  # Collapse multiple hyphens
        cleaned = cleaned.strip('-')  # Remove leading/trailing hyphens
        
        if len(cleaned) == 0:
            return (False, None, "invalid_characters")
        if len(cleaned) > 63:
            cleaned = cleaned[:63].rstrip('-')
        normalized = cleaned
    
    # Cannot be all numeric
    if normalized.isdigit():
        return (False, normalized, "all_numeric")
    
    # Final validation
    if not re.match(r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?$', normalized):
        return (False, normalized, "invalid_format")
    
    return (True, normalized, "ok")


def validate_and_normalize_fqdn(fqdn_str: str, hostname: Optional[str] = None) -> Tuple[bool, Optional[str], bool, str]:
    """
    Validate and normalize FQDN.
    
    Returns:
        (is_valid, normalized_fqdn, is_consistent_with_hostname, reason)
    """
    if fqdn_str is None or fqdn_str == "":
        # Try to construct from hostname
        if hostname:
            # Default domain inference (can be enhanced with LLM)
            constructed = f"{hostname}.corp.example.com"
            return (True, constructed, False, "constructed_from_hostname")
        return (False, None, False, "missing")
    
    s = str(fqdn_str).strip().lower()
    
    # Remove trailing dot if present
    s = s.rstrip('.')
    
    # Basic validation
    if len(s) == 0:
        return (False, None, False, "empty")
    if len(s) > 253:
        return (False, None, False, "too_long")
    
    # Split into labels
    labels = s.split('.')
    
    # Validate each label
    for label in labels:
        if len(label) == 0:
            return (False, None, False, "empty_label")
        if len(label) > 63:
            return (False, None, False, "label_too_long")
        if not re.match(r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?$', label):
            return (False, None, False, "invalid_label_format")
    
    # Check consistency with hostname
    is_consistent = False
    if hostname:
        # FQDN should start with hostname
        if s.startswith(hostname + '.'):
            is_consistent = True
        elif s == hostname:
            is_consistent = True
    
    return (True, s, is_consistent, "ok")


def extract_email_from_owner(owner_str: str) -> Optional[str]:
    """Extract email address from owner field using regex."""
    if not owner_str:
        return None
    
    # Simple email regex
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    matches = re.findall(email_pattern, owner_str)
    if matches:
        return matches[0].lower()
    return None


def normalize_device_type(device_type_str: str) -> Tuple[str, str]:
    """
    Normalize device type to canonical form.
    
    Returns:
        (normalized_type, confidence)
    """
    if not device_type_str or device_type_str.strip() == "":
        return ("", "low")
    
    s = str(device_type_str).strip().lower()
    
    # Mapping of known variations
    type_mapping = {
        "server": "server",
        "srv": "server",
        "switch": "switch",
        "router": "router",
        "gw": "router",
        "gateway": "router",
        "printer": "printer",
        "iot": "iot",
        "camera": "camera",
        "cam": "camera",
        "firewall": "firewall",
        "fw": "firewall",
        "load_balancer": "load_balancer",
        "lb": "load_balancer",
    }
    
    # Direct match
    if s in type_mapping:
        return (type_mapping[s], "high")
    
    # Partial match
    for key, value in type_mapping.items():
        if key in s or s in key:
            return (value, "medium")
    
    # Return original if no match
    return (s, "low")

