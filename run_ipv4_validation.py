#!/usr/bin/env python3
import csv
import json
import sys
from pathlib import Path

def ipv4_validate_and_normalize(ip_str):
    if ip_str is None:
        return (False, None, "missing")
    s = str(ip_str).strip()
    # quick reject obvious IPv6 / non-dot forms
    if ":" in s:
        return (False, None, "ipv6_or_non_ipv4")
    parts = s.split(".")
    if len(parts) != 4:
        return (False, None, "wrong_part_count")
    canonical_parts = []
    for p in parts:
        if p == "":
            return (False, None, "empty_octet")
        # negative or non-digit
        if not (p.lstrip("+").isdigit() and not p.startswith("-")):
            return (False, None, "non_numeric_or_negative")
        try:
            v = int(p, 10)
        except ValueError:
            return (False, None, "non_decimal_format")
        if v < 0 or v > 255:
            return (False, None, "octet_out_of_range")
        canonical_parts.append(str(v))
    canonical = ".".join(canonical_parts)
    return (True, canonical, "ok")

def classify_ipv4_type(ip):
    # Simple classification for context; not required for validity
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
    
def default_subnet(ip):
    # Heuristic: /24 for RFC1918, else None (you can adapt this)
    iptype = classify_ipv4_type(ip)
    if iptype == "private_rfc1918":
        parts = list(map(int, ip.split(".")))
        return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
    return ""

def process(input_csv, out_csv, anomalies_json):
    anomalies = []
    with open(input_csv, newline="") as f, open(out_csv, "w", newline="") as g:
        reader = csv.DictReader(f)
        fieldnames = [
            "ip","ip_valid","ip_version","subnet_cidr","normalization_steps","source_row_id"
        ] + [c for c in reader.fieldnames if c not in ("ip","source_row_id")]
        writer = csv.DictWriter(g, fieldnames=fieldnames)
        writer.writeheader()
        for row in reader:
            raw_ip = row.get("ip","")
            valid, canonical, reason = ipv4_validate_and_normalize(raw_ip)
            steps = []
            steps.append("ip_trim")
            if reason == "ok":
                steps.append("ip_parse")
                steps.append("ip_normalize")
                ip_out = canonical
                ip_valid = "true"
                ip_version = "4"
                subnet = default_subnet(ip_out)
            else:
                # keep original as-is, flag invalid
                ip_out = str(raw_ip).strip()
                ip_valid = "false"
                ip_version = ""
                subnet = ""
                anomalies.append({
                    "source_row_id": row.get("source_row_id"),
                    "issues": [{"field":"ip","type": reason, "value": raw_ip}],
                    "recommended_actions": ["Correct IP or mark record for review"]
                })
                # add a specific step for the reason
                steps.append(f"ip_invalid_{reason}")
            out_row = {
                "ip": ip_out,
                "ip_valid": ip_valid,
                "ip_version": ip_version,
                "subnet_cidr": subnet,
                "normalization_steps": "|".join(steps),
                "source_row_id": row.get("source_row_id")
            }
            # pass-through other fields
            for k,v in row.items():
                if k not in ("ip","source_row_id"):
                    out_row[k] = v
            writer.writerow(out_row)
    with open(anomalies_json, "w") as h:
        json.dump(anomalies, h, indent=2)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        in_csv = "inventory_raw.csv"
    else:
        in_csv = sys.argv[1]
    out_csv = "inventory_clean.csv"
    anomalies_json = "anomalies.json"
    process(in_csv, out_csv, anomalies_json)
    print(f"Wrote {out_csv} and {anomalies_json}")
