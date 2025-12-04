# Approach: Inventory Data Normalization Pipeline

## Overview

This pipeline cleans, normalizes, and enriches network inventory data from `inventory_raw.csv` into a structured dataset suitable for IPAM/DNS/DHCP workflows. The approach prioritizes **deterministic rules** for performance and reliability, using **LLMs only when pattern matching is insufficient**.

## Pipeline Architecture

### Phase 1: Deterministic Validation & Normalization

**Fields processed with deterministic rules:**

1. **IP Address** (`ip`)

   - Validation: IPv4/IPv6 format checking, octet range validation
   - Normalization: Remove leading zeros, canonicalize format
   - Derived fields: `ip_valid`, `ip_version`, `subnet_cidr`, `reverse_ptr`
   - Implementation: `validators.validate_and_normalize_ip()`
2. **MAC Address** (`mac`)

   - Validation: 48-bit hex format checking
   - Normalization: Convert to uppercase colon-separated format (XX:XX:XX:XX:XX:XX)
   - Implementation: `validators.validate_and_normalize_mac()`
3. **Hostname** (`hostname`)

   - Validation: RFC 1123 compliance (length, character set, format)
   - Normalization: Lowercase, trim, remove invalid characters
   - Implementation: `validators.validate_and_normalize_hostname()`
4. **FQDN** (`fqdn`)

   - Validation: Label format, total length, structure
   - Normalization: Lowercase, remove trailing dots, construct if missing
   - Consistency check: Verify hostname matches FQDN prefix
   - Implementation: `validators.validate_and_normalize_fqdn()`
5. **Reverse PTR** (`reverse_ptr`)

   - Generation: Automatic derivation from valid IP addresses
   - IPv4: `x.y.z.w.in-addr.arpa` format
   - IPv6: Reverse nibble format in `ip6.arpa`
   - Implementation: `validators.generate_reverse_ptr()`
6. **Subnet CIDR** (`subnet_cidr`)

   - Derivation: Heuristic-based from IP address type
   - RFC 1918 private IPs → `/24` subnet
   - Link-local (169.254.x.x) → `/16`
   - Loopback (127.x.x.x) → `/8`
   - Implementation: `validators.derive_subnet_cidr()`

### Phase 2: Pattern-Based Normalization

**Fields with deterministic patterns:**

1. **Device Type** (`device_type`)

   - Mapping: Known variations to canonical types (server, switch, router, etc.)
   - Confidence: High for explicit matches, medium for partial matches
   - Implementation: `validators.normalize_device_type()`
2. **Email Extraction** (from `owner` field)

   - Regex-based extraction of email addresses
   - Implementation: `validators.extract_email_from_owner()`

### Phase 3: LLM-Assisted Processing

**Fields requiring LLM for ambiguous cases:**

1. **Owner Information** (`owner`, `owner_email`, `owner_team`)

   - **When LLM is used:** Complex formats like "priya (platform) priya@corp.example.com"
   - **LLM task:** Parse structured components (name, email, team/role)
   - **Fallback:** Regex-based extraction if LLM unavailable
   - **Implementation:** `llm_helper.LLMHelper.parse_owner_info()`
2. **Device Type Classification** (`device_type`, `device_type_confidence`)

   - **When LLM is used:** Missing or ambiguous device type
   - **LLM task:** Infer from hostname patterns, notes, context
   - **Fallback:** Deterministic mapping or "unknown"
   - **Implementation:** `llm_helper.LLMHelper.classify_device_type()`
3. **Site Normalization** (`site_normalized`)

   - **When LLM is used:** Complex variations (e.g., "HQ Bldg 1" vs "HQ-BUILDING-1")
   - **LLM task:** Standardize to format: CITY-BUILDING-AREA
   - **Fallback:** Pattern-based normalization with known mappings
   - **Implementation:** `llm_helper.LLMHelper.normalize_site()`
4. **FQDN Domain Inference**

   - **When LLM is used:** Domain extraction from site/context when email unavailable
   - **LLM task:** Map site names to domain names
   - **Fallback:** Site-based mapping or default domain
   - **Implementation:** `llm_helper.LLMHelper.infer_fqdn_domain()`

## Constraints & Design Decisions

### LLM Configuration

- **Model:** `gpt-4o-mini` (cost-effective, sufficient for structured tasks)
- **Temperature:** `0.2` (low for deterministic outputs)
- **Output Format:** JSON (structured, parseable)
- **Error Handling:** Graceful fallback to deterministic rules if LLM fails

### Anomaly Detection

Anomalies are logged when:

- IP/MAC addresses are invalid or malformed
- Hostname violates RFC rules
- FQDN is inconsistent with hostname
- Required fields are missing
- Data conflicts detected

### Normalization Steps Tracking

Every transformation is logged in `normalization_steps` field:

- Format: Pipe-separated list (`ip_trim|ip_parse|hostname_normalize|...`)
- Enables traceability and debugging
- Helps identify which rules/LLM were applied

## Reproducibility

### Prerequisites

```bash
# Python 3.8+
pip install openai  # Optional, for LLM features
```

### Environment Setup

```bash
# Set OpenAI API key (optional, for LLM features)
export OPENAI_API_KEY="your-api-key-here"
```

### Execution

```bash
# Single entry point
python run.py

# Or directly
python normalize_inventory.py inventory_raw.csv
```

### Output Files

- `inventory_clean.csv` - Normalized inventory data with all target schema fields
- `anomalies.json` - List of data quality issues with recommended actions
- `prompts.md` - Log of all LLM interactions (auto-generated)

## Pipeline Flow

```
inventory_raw.csv
    ↓
[For each record]
    ↓
1. Validate & Normalize IP → ip_valid, ip_version, subnet_cidr, reverse_ptr
    ↓
2. Validate & Normalize Hostname → hostname_valid
    ↓
3. Validate & Normalize FQDN → fqdn_consistent
    ↓
4. Validate & Normalize MAC → mac_valid
    ↓
5. Parse Owner (LLM if complex) → owner, owner_email, owner_team
    ↓
6. Classify Device Type (LLM if ambiguous) → device_type, device_type_confidence
    ↓
7. Normalize Site (LLM if complex) → site_normalized
    ↓
8. Track normalization_steps
    ↓
9. Collect anomalies
    ↓
inventory_clean.csv + anomalies.json
```

## Decision Criteria: Deterministic vs LLM

### Use Deterministic Rules When:

- Format is well-defined (IP, MAC, FQDN syntax)
- Pattern matching is reliable (email extraction, basic hostname validation)
- Transformation is straightforward (case conversion, separator normalization)
- Performance is critical (high-volume processing)

### Use LLM When:

- Multiple formats exist with no clear pattern (owner field variations)
- Context is needed for classification (device type from hostname/notes)
- Ambiguity requires inference (site name variations, missing domain)
- Confidence scoring is valuable (device type classification)

## Testing & Validation

The pipeline handles edge cases:

- Missing fields (N/A, empty strings)
- Invalid formats (malformed IPs, MACs, hostnames)
- Special IP addresses (loopback, APIPA, broadcast, network ID)
- Conflicting data (hostname vs FQDN mismatch)
- Ambiguous classifications (device type, site names)

All edge cases are logged in `anomalies.json` with recommended actions.
