# Validation and Normalization Plan

## Overview
This document outlines the validation and normalization rules for each field in the inventory dataset. The approach prioritizes deterministic rules and uses LLMs only when pattern matching is insufficient.

---

## Field-by-Field Validation & Normalization Rules

### 1. IP Address (`ip`)

#### Validation Rules (Deterministic)
- **IPv4 Validation:**
  - Must contain exactly 4 octets separated by dots
  - Each octet must be numeric (0-255)
  - No leading zeros (except single 0 is allowed)
  - No negative numbers
  - No non-numeric characters
  - Reject if contains ":" (IPv6 indicator)
  - Reject if contains "%" (interface identifier)
  
- **IPv6 Validation:**
  - Must follow RFC 4291 format
  - Support compressed notation (::)
  - Support zone identifiers (%interface) - extract and store separately
  - Validate hex digits and structure
  
- **Special Cases:**
  - `127.0.0.1` → valid but flag as loopback
  - `169.254.x.x` → valid but flag as APIPA/link-local
  - `192.168.1.0` → valid but flag as potential network ID
  - `192.168.1.255` → valid but flag as potential broadcast
  - `N/A`, empty, or missing → invalid

#### Normalization Rules (Deterministic)
- **IPv4:**
  - Remove leading zeros from each octet (e.g., `192.168.010.005` → `192.168.10.5`)
  - Trim whitespace
  - Convert to canonical form (lowercase, no padding)
  
- **IPv6:**
  - Expand compressed notation to canonical form
  - Lowercase hex digits
  - Remove zone identifiers (store separately if needed)
  
- **Output Fields:**
  - `ip`: Normalized IP address
  - `ip_valid`: `true`/`false`
  - `ip_version`: `4`, `6`, or empty
  - `subnet_cidr`: Derived subnet (see subnet rules below)

---

### 2. Subnet CIDR (`subnet_cidr`)

#### Validation Rules (Deterministic)
- Must be valid CIDR notation (e.g., `192.168.1.0/24`)
- Network portion must match IP address class
- Prefix length must be valid (0-32 for IPv4, 0-128 for IPv6)

#### Normalization Rules (Deterministic)
- **Heuristic-based derivation:**
  - RFC 1918 private IPs → `/24` subnet (first 3 octets)
  - Public IPs → leave empty or use `/32` (host route)
  - Link-local (169.254.x.x) → `/16` subnet
  - Loopback (127.x.x.x) → `/8`
  
- **If subnet provided in source:**
  - Validate and normalize CIDR format
  - Ensure IP falls within subnet range

---

### 3. Hostname (`hostname`)

#### Validation Rules (Deterministic + LLM)
- **Deterministic Checks:**
  - Must be non-empty (after trimming)
  - Length: 1-63 characters (RFC 1123)
  - Allowed characters: `a-z`, `0-9`, `-` (hyphen)
  - Cannot start or end with hyphen
  - Cannot be all numeric
  - Case-insensitive validation
  
- **LLM-Assisted Validation:**
  - Flag suspicious patterns (e.g., `badhost`, `neg`, `bcast`)
  - Detect if hostname appears to be an IP address
  - Identify placeholder values

#### Normalization Rules (Deterministic)
- Convert to lowercase
- Trim whitespace
- Remove invalid characters (replace with hyphen or remove)
- Truncate to 63 characters if needed
- **Output Fields:**
  - `hostname`: Normalized hostname
  - `hostname_valid`: `true`/`false`

---

### 4. FQDN (`fqdn`)

#### Validation Rules (Deterministic)
- Must contain at least one dot (separating hostname from domain)
- Each label must follow hostname rules (1-63 chars, valid characters)
- Total length: up to 253 characters
- Must not start or end with dot
- Must not contain consecutive dots

#### Normalization Rules (Deterministic)
- Convert to lowercase
- Trim whitespace
- Remove trailing dots
- **FQDN Construction:**
  - If `fqdn` provided: validate and use
  - If only `hostname` provided: construct FQDN using domain inference (see below)
  - If both provided: validate consistency
  
- **Domain Inference (LLM-assisted if needed):**
  - Extract domain from email addresses in owner field
  - Use site-based domain mapping (e.g., `BLR Campus` → `blr.corp.example.com`)
  - Default domain: `corp.example.com` (configurable)
  
- **Output Fields:**
  - `fqdn`: Full qualified domain name
  - `fqdn_consistent`: `true` if hostname matches FQDN prefix, `false` otherwise

---

### 5. Reverse PTR (`reverse_ptr`)

#### Validation Rules (Deterministic)
- Must be valid reverse DNS format
- IPv4: `x.y.z.w.in-addr.arpa` format
- IPv6: Reverse nibble format in `ip6.arpa`

#### Normalization Rules (Deterministic)
- **IPv4 Reverse PTR:**
  - Reverse octets: `192.168.1.10` → `10.1.168.192.in-addr.arpa`
  - Only generate if IP is valid
  
- **IPv6 Reverse PTR:**
  - Expand IPv6 to full form
  - Reverse nibbles (hex digits)
  - Format: `[reversed-nibbles].ip6.arpa`
  
- **Output:**
  - Generate only for valid IPs
  - Leave empty for invalid IPs

---

### 6. MAC Address (`mac`)

#### Validation Rules (Deterministic)
- Must be 48-bit (6 octets)
- Valid formats:
  - `AA-BB-CC-DD-EE-FF` (hyphen-separated)
  - `AA:BB:CC:DD:EE:FF` (colon-separated)
  - `AABBCCDDEEFF` (no separators)
  - `AA.BB.CC.DD.EE.FF` (dot-separated)
- Each octet must be valid hex (00-FF)
- Case-insensitive

#### Normalization Rules (Deterministic)
- Convert to uppercase
- Use colon separator (standard format): `AA:BB:CC:DD:EE:FF`
- Remove all separators, then re-insert colons
- Validate length (must be exactly 12 hex digits)
- **Output Fields:**
  - `mac`: Normalized MAC address
  - `mac_valid`: `true`/`false`

---

### 7. Owner Information (`owner`)

#### Validation Rules (LLM-assisted)
- **Deterministic Checks:**
  - Non-empty after trimming
  - May contain name, email, team/role in various formats
  
- **LLM-Assisted Parsing:**
  - Extract person name
  - Extract email address (validate format)
  - Extract team/role (e.g., "platform", "ops", "sec")
  - Handle formats like:
    - `priya (platform) priya@corp.example.com`
    - `jane@corp.example.com`
    - `ops`
    - `Facilities`

#### Normalization Rules (LLM-assisted)
- **Structured Extraction:**
  - `owner`: Person's name (normalized: title case)
  - `owner_email`: Validated email address
  - `owner_team`: Team/role (normalized: lowercase, standardized)
  
- **Team Standardization:**
  - Map variations: `platform` → `platform`, `ops` → `operations`, `sec` → `security`
  - Use LLM to infer team from context if ambiguous

---

### 8. Device Type (`device_type`)

#### Validation Rules (LLM-assisted)
- **Deterministic Checks:**
  - Common types: `server`, `switch`, `router`, `printer`, `iot`, `camera`
  
- **LLM-Assisted Classification:**
  - If missing or ambiguous, infer from:
    - Hostname patterns (e.g., `printer-01`, `iot-cam01`)
    - Notes field
    - IP address context
    - Other device characteristics
  
- **Confidence Scoring:**
  - High confidence: Explicitly provided and matches known types
  - Medium confidence: Inferred from strong patterns
  - Low confidence: LLM inference with weak signals

#### Normalization Rules (Deterministic + LLM)
- **Standardize Values:**
  - Map to canonical types: `server`, `switch`, `router`, `printer`, `iot`, `camera`, `firewall`, `load_balancer`, `unknown`
  - Convert to lowercase
  - Handle variations: `edge gw?` → `router` (with LLM help)
  
- **Output Fields:**
  - `device_type`: Normalized device type
  - `device_type_confidence`: `high`, `medium`, `low`

---

### 9. Site (`site`)

#### Validation Rules (LLM-assisted)
- **Deterministic Checks:**
  - Non-empty (after trimming)
  - May contain various formats: `BLR Campus`, `HQ Bldg 1`, `HQ-BUILDING-1`, `Lab-1`

#### Normalization Rules (LLM-assisted)
- **Standardization Strategy:**
  - Extract location components:
    - City/Region: `BLR` (Bangalore), `HQ` (Headquarters)
    - Building/Area: `Campus`, `Bldg 1`, `BUILDING-1`, `Lab-1`
  
- **Normalization Rules:**
  - Convert to standard format: `{city}-{building}-{area}`
  - Examples:
    - `BLR Campus` → `BLR-Campus`
    - `HQ Bldg 1` → `HQ-Building-1`
    - `HQ-BUILDING-1` → `HQ-Building-1`
    - `Lab-1` → `HQ-Lab-1` (infer HQ if missing)
  
- **LLM-Assisted:**
  - Resolve abbreviations (BLR → Bangalore)
  - Infer missing components (e.g., `Lab-1` → infer building/city)
  - Handle variations and typos
  
- **Output Fields:**
  - `site`: Original site value
  - `site_normalized`: Standardized site identifier

---

### 10. Source Row ID (`source_row_id`)

#### Validation Rules (Deterministic)
- Must be present and unique
- Numeric or alphanumeric identifier

#### Normalization Rules (Deterministic)
- Preserve as-is (no transformation needed)
- Use for tracking and anomaly reporting

---

### 11. Normalization Steps (`normalization_steps`)

#### Rules (Deterministic)
- Track all transformations applied to each record
- Format: Pipe-separated list of step identifiers
- Examples:
  - `ip_trim|ip_parse|ip_normalize|hostname_lowercase|mac_format_colon`
  - `ip_invalid_wrong_part_count|hostname_llm_inferred|device_type_llm_classified`

---

## Implementation Strategy

### Phase 1: Deterministic Rules (Priority)
1. IP validation and normalization (already implemented)
2. MAC address validation and normalization
3. Hostname basic validation
4. FQDN construction and validation
5. Reverse PTR generation
6. Subnet CIDR derivation

### Phase 2: Pattern-Based Normalization
1. Site name pattern matching (common variations)
2. Device type mapping (known types)
3. Owner email extraction (regex-based)

### Phase 3: LLM-Assisted Processing
1. Owner information parsing (name, email, team extraction)
2. Device type classification (when missing/ambiguous)
3. Site normalization (complex variations)
4. FQDN domain inference
5. Anomaly detection and flagging

---

## Decision Criteria: Deterministic vs LLM

### Use Deterministic Rules When:
- ✅ Format is well-defined (IP, MAC, FQDN syntax)
- ✅ Pattern matching is reliable (email extraction, basic hostname validation)
- ✅ Transformation is straightforward (case conversion, separator normalization)
- ✅ Performance is critical (high-volume processing)

### Use LLM When:
- ⚠️ Multiple formats exist with no clear pattern (owner field variations)
- ⚠️ Context is needed for classification (device type from hostname/notes)
- ⚠️ Ambiguity requires inference (site name variations, missing domain)
- ⚠️ Confidence scoring is valuable (device type classification)

---

## Edge Cases to Handle

1. **Missing Fields:**
   - IP missing → mark invalid, skip IP-dependent fields
   - Hostname missing → attempt to infer from FQDN or generate placeholder
   - Owner missing → leave empty, flag in anomalies

2. **Conflicting Data:**
   - Hostname vs FQDN mismatch → flag `fqdn_consistent=false`
   - IP vs subnet mismatch → flag in anomalies
   - Multiple emails in owner field → extract first valid email

3. **Special IP Addresses:**
   - Loopback (127.x.x.x) → valid but flag context
   - APIPA (169.254.x.x) → valid but flag as temporary
   - Network ID / Broadcast → valid but flag as non-host addresses

4. **Ambiguous Classifications:**
   - Device type unclear → use LLM with low confidence
   - Site abbreviation → use LLM to expand/resolve

---

## Anomaly Detection Rules

An anomaly should be logged when:
- IP address is invalid or malformed
- MAC address is invalid or malformed
- Hostname violates RFC rules
- FQDN is inconsistent with hostname
- Owner information cannot be parsed
- Device type cannot be determined
- Site cannot be normalized
- Required fields are missing
- Data conflicts detected (e.g., IP not in subnet)

---

## Next Steps

1. Implement deterministic validators for IP, MAC, hostname, FQDN
2. Implement normalization functions for each field
3. Create LLM prompt templates for owner parsing, device classification, site normalization
4. Build orchestration pipeline in `run.py`
5. Generate comprehensive test cases for edge cases
6. Document all LLM interactions in `prompts.md`

