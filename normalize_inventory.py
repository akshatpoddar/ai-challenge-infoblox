#!/usr/bin/env python3
"""
Main inventory normalization pipeline.
Processes raw inventory data and produces cleaned output with anomaly reporting.
"""

import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

from validators import (
    validate_and_normalize_ip,
    derive_subnet_cidr,
    generate_reverse_ptr,
    validate_and_normalize_mac,
    validate_and_normalize_hostname,
    validate_and_normalize_fqdn,
    normalize_device_type
)
from llm_helper import LLMHelper


def process_record(row: Dict, llm: LLMHelper) -> Tuple[Dict, List[Dict]]:
    """
    Process a single inventory record.
    
    Returns:
        (normalized_record, list_of_anomalies)
    """
    anomalies = []
    steps = []
    out_row = {}
    
    # Source row ID
    source_row_id = row.get("source_row_id", "")
    out_row["source_row_id"] = source_row_id
    
    # 1. IP Address Validation and Normalization
    raw_ip = row.get("ip", "")
    ip_valid, normalized_ip, ip_version, ip_reason = validate_and_normalize_ip(raw_ip)
    steps.append("ip_trim")
    
    if ip_valid:
        steps.append("ip_parse")
        steps.append("ip_normalize")
        out_row["ip"] = normalized_ip
        out_row["ip_valid"] = "true"
        out_row["ip_version"] = ip_version
        
        # Derive subnet and reverse PTR
        subnet_cidr = derive_subnet_cidr(normalized_ip, ip_version)
        out_row["subnet_cidr"] = subnet_cidr
        if subnet_cidr:
            steps.append("subnet_derived")
        
        reverse_ptr = generate_reverse_ptr(normalized_ip, ip_version)
        out_row["reverse_ptr"] = reverse_ptr
        if reverse_ptr:
            steps.append("reverse_ptr_generated")
    else:
        out_row["ip"] = str(raw_ip).strip()
        out_row["ip_valid"] = "false"
        out_row["ip_version"] = ""
        out_row["subnet_cidr"] = ""
        out_row["reverse_ptr"] = ""
        steps.append(f"ip_invalid_{ip_reason}")
        anomalies.append({
            "source_row_id": source_row_id,
            "issues": [{"field": "ip", "type": ip_reason, "value": raw_ip}],
            "recommended_actions": ["Correct IP address or mark record for review"]
        })
    
    # 2. Hostname Validation and Normalization
    raw_hostname = row.get("hostname", "")
    hostname_valid, normalized_hostname, hostname_reason = validate_and_normalize_hostname(raw_hostname)
    
    if hostname_valid:
        steps.append("hostname_normalize")
        out_row["hostname"] = normalized_hostname
        out_row["hostname_valid"] = "true"
    else:
        out_row["hostname"] = str(raw_hostname).strip()
        out_row["hostname_valid"] = "false"
        steps.append(f"hostname_invalid_{hostname_reason}")
        if hostname_reason != "missing":
            anomalies.append({
                "source_row_id": source_row_id,
                "issues": [{"field": "hostname", "type": hostname_reason, "value": raw_hostname}],
                "recommended_actions": ["Correct hostname format per RFC 1123"]
            })
    
    # 3. FQDN Validation and Normalization
    raw_fqdn = row.get("fqdn", "")
    fqdn_valid, normalized_fqdn, fqdn_consistent, fqdn_reason = validate_and_normalize_fqdn(
        raw_fqdn, normalized_hostname if hostname_valid else None
    )
    
    # If FQDN was constructed, try to infer domain from context
    if fqdn_reason == "constructed_from_hostname" and normalized_hostname:
        owner_email = ""  # Will be set later
        site = row.get("site", "")
        inferred_domain = llm.infer_fqdn_domain(normalized_hostname, site, owner_email)
        normalized_fqdn = f"{normalized_hostname}.{inferred_domain}"
        steps.append("fqdn_domain_inferred")
    
    if fqdn_valid:
        steps.append("fqdn_normalize")
        out_row["fqdn"] = normalized_fqdn
        out_row["fqdn_consistent"] = "true" if fqdn_consistent else "false"
        if not fqdn_consistent:
            steps.append("fqdn_inconsistent")
            anomalies.append({
                "source_row_id": source_row_id,
                "issues": [{"field": "fqdn", "type": "inconsistent_with_hostname", "value": normalized_fqdn}],
                "recommended_actions": ["Verify FQDN matches hostname"]
            })
    else:
        out_row["fqdn"] = normalized_fqdn or ""
        out_row["fqdn_consistent"] = "false"
        steps.append(f"fqdn_invalid_{fqdn_reason}")
        if fqdn_reason not in ["missing", "constructed_from_hostname"]:
            anomalies.append({
                "source_row_id": source_row_id,
                "issues": [{"field": "fqdn", "type": fqdn_reason, "value": raw_fqdn}],
                "recommended_actions": ["Correct FQDN format"]
            })
    
    # 4. MAC Address Validation and Normalization
    raw_mac = row.get("mac", "")
    mac_valid, normalized_mac, mac_reason = validate_and_normalize_mac(raw_mac)
    
    if mac_valid:
        steps.append("mac_normalize")
        out_row["mac"] = normalized_mac
        out_row["mac_valid"] = "true"
    else:
        out_row["mac"] = str(raw_mac).strip()
        out_row["mac_valid"] = "false"
        steps.append(f"mac_invalid_{mac_reason}")
        if mac_reason != "missing":
            anomalies.append({
                "source_row_id": source_row_id,
                "issues": [{"field": "mac", "type": mac_reason, "value": raw_mac}],
                "recommended_actions": ["Correct MAC address format (XX:XX:XX:XX:XX:XX)"]
            })
    
    # 5. Owner Information Parsing (LLM-assisted)
    raw_owner = row.get("owner", "")
    owner_info = llm.parse_owner_info(raw_owner, context={"hostname": normalized_hostname, "site": row.get("site", "")})
    out_row["owner"] = owner_info.get("owner", "")
    out_row["owner_email"] = owner_info.get("owner_email", "")
    out_row["owner_team"] = owner_info.get("owner_team", "")
    if owner_info.get("owner") or owner_info.get("owner_email") or owner_info.get("owner_team"):
        steps.append("owner_parsed")
    
    # 6. Device Type Classification (LLM-assisted if needed)
    raw_device_type = row.get("device_type", "")
    raw_notes = row.get("notes", "")
    
    # Try deterministic first
    normalized_dt, confidence = normalize_device_type(raw_device_type)
    
    # Use LLM if confidence is low or missing
    if confidence == "low" or not normalized_dt:
        device_info = llm.classify_device_type(
            normalized_hostname if hostname_valid else raw_hostname,
            raw_device_type,
            raw_notes
        )
        out_row["device_type"] = device_info.get("device_type", normalized_dt or "unknown")
        out_row["device_type_confidence"] = device_info.get("device_type_confidence", "low")
        steps.append("device_type_llm_classified")
    else:
        out_row["device_type"] = normalized_dt
        out_row["device_type_confidence"] = confidence
        steps.append("device_type_normalized")
    
    # 7. Site Normalization (LLM-assisted)
    raw_site = row.get("site", "")
    normalized_site = llm.normalize_site(raw_site, context={"hostname": normalized_hostname})
    out_row["site"] = raw_site  # Keep original
    out_row["site_normalized"] = normalized_site
    if normalized_site:
        steps.append("site_normalized")
    
    # Normalization steps
    out_row["normalization_steps"] = "|".join(steps)
    
    return out_row, anomalies


def process(input_csv: str, out_csv: str, anomalies_json: str):
    """
    Main processing function.
    """
    llm = LLMHelper(temperature=0.2)
    all_anomalies = []
    
    # Target schema fieldnames
    target_fieldnames = [
        "source_row_id",
        "ip", "ip_valid", "ip_version", "subnet_cidr",
        "hostname", "hostname_valid", "fqdn", "fqdn_consistent", "reverse_ptr",
        "mac", "mac_valid",
        "owner", "owner_email", "owner_team",
        "device_type", "device_type_confidence",
        "site", "site_normalized",
        "normalization_steps"
    ]
    
    with open(input_csv, newline="", encoding="utf-8") as f, \
         open(out_csv, "w", newline="", encoding="utf-8") as g:
        
        reader = csv.DictReader(f)
        writer = csv.DictWriter(g, fieldnames=target_fieldnames)
        writer.writeheader()
        
        for row in reader:
            normalized_row, record_anomalies = process_record(row, llm)
            all_anomalies.extend(record_anomalies)
            
            # Ensure all target fields are present
            for field in target_fieldnames:
                if field not in normalized_row:
                    normalized_row[field] = ""
            
            writer.writerow(normalized_row)
    
    # Write anomalies
    with open(anomalies_json, "w", encoding="utf-8") as h:
        json.dump(all_anomalies, h, indent=2)
    
    print(f"Processed inventory data:")
    print(f"  - Output: {out_csv}")
    print(f"  - Anomalies: {anomalies_json} ({len(all_anomalies)} issues found)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        in_csv = "inventory_raw.csv"
    else:
        in_csv = sys.argv[1]
    
    out_csv = "inventory_clean.csv"
    anomalies_json = "anomalies.json"
    
    process(in_csv, out_csv, anomalies_json)

