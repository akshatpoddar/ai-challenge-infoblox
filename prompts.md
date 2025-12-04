# LLM Prompts Log

This document logs all LLM prompt templates used during data normalization.
Each entry includes the system prompt, user prompt, and expected response format.

---

## Prompt Template 1: parse_owner_info

### Purpose

Parse owner information to extract structured components (name, email, team) from unstructured or mixed-format text.

### When Used

- Owner field contains email address AND other text (name/team)
- Format is complex (e.g., "priya (platform) priya@corp.example.com")
- Deterministic parsing cannot reliably separate components

### System Prompt

```
You are a data parsing assistant specialized in extracting structured information from unstructured text. You must always return valid JSON that strictly adheres to the specified format. Do not include any explanatory text, markdown code blocks, or formatting outside the JSON object.
```

### User Prompt Template

```
Parse the following owner information and extract structured data into a JSON object.

Input: "{owner_str}"

STRICT REQUIREMENTS:
1. Return ONLY valid JSON, no additional text, explanations, or markdown formatting
2. JSON must contain exactly these three keys: "owner", "owner_email", "owner_team"
3. All values must be strings (use empty string "" if a field is not found)
4. Email addresses must be valid format
5. Team names must be one of: platform, ops, operations, sec, security, facilities, or empty string

Note: Owner names, emails, and team names will be normalized to lowercase by the pipeline after extraction.

Expected JSON structure:
{
  "owner": "person name or empty string",
  "owner_email": "email@domain.com or empty string",
  "owner_team": "team name or empty string"
}

Return JSON only, no other text.
```

### Expected Response Format

**JSON Structure:**
```json
{
  "owner": "string (person name or empty)",
  "owner_email": "string (email address or empty)",
  "owner_team": "string (team name or empty)"
}
```

**Strict Constraints:**
- All three keys must be present
- All values must be strings
- Email must be valid format
- Team must be canonical name or empty
- Owner names, emails, and teams are normalized to lowercase by the pipeline after extraction

### Example Input/Output

**Input:** `"priya (platform) priya@corp.example.com"`

**Expected Output:**
```json
{
  "owner": "priya",
  "owner_email": "priya@corp.example.com",
  "owner_team": "platform"
}
```

**Note:** Owner name is already lowercase in this example. For inputs like "John Doe", the output would be `"owner": "john doe"`.

---

## Prompt Template 2: classify_device_type

### Purpose

Classify network device type based on hostname, provided type, and contextual notes when deterministic classification is insufficient.

### When Used

- Device type field is missing or empty
- Deterministic normalization returns low confidence
- Hostname/notes contain ambiguous indicators requiring semantic understanding

### System Prompt

```
You are a network device classification assistant with expertise in IT infrastructure. Classify devices based on hostname patterns, naming conventions, and contextual clues. You must always return valid JSON that strictly adheres to the specified format. Do not include any explanatory text, markdown code blocks, or formatting outside the JSON object.
```

### User Prompt Template

```
Classify the network device type based on the following context information.

Context: {context_str}

STRICT REQUIREMENTS:
1. Return ONLY valid JSON, no additional text, explanations, or markdown formatting
2. JSON must contain exactly these two keys: "device_type", "device_type_confidence"
3. "device_type" must be exactly one of: server, switch, router, printer, iot, camera, firewall, load_balancer, unknown
4. "device_type_confidence" must be exactly one of: high, medium, low
5. Use "unknown" only when no reasonable inference can be made
6. Use "high" confidence when hostname/notes provide clear device type indicators
7. Use "medium" confidence when inference is reasonable but not definitive
8. Use "low" confidence when inference is speculative

Expected JSON structure:
{
  "device_type": "server|switch|router|printer|iot|camera|firewall|load_balancer|unknown",
  "device_type_confidence": "high|medium|low"
}

Return JSON only, no other text.
```

**Note:** `{context_str}` is dynamically built from:
- `hostname: {hostname}` (if present)
- `provided_type: {device_type}` (if present)
- `notes: {notes}` (if present)

### Expected Response Format

**JSON Structure:**
```json
{
  "device_type": "server|switch|router|printer|iot|camera|firewall|load_balancer|unknown",
  "device_type_confidence": "high|medium|low"
}
```

**Strict Constraints:**
- Both keys must be present
- device_type must be from allowed enum values
- device_type_confidence must be high, medium, or low

### Example Input/Output

**Input Context:** `"hostname: printer-01, notes: Canon in room 204"`

**Expected Output:**
```json
{
  "device_type": "printer",
  "device_type_confidence": "high"
}
```

**Input Context:** `"hostname: host-02, notes: edge gw?"`

**Expected Output:**
```json
{
  "device_type": "router",
  "device_type_confidence": "medium"
}
```

---

## Prompt Template 3: normalize_site

### Purpose

Normalize site/location names to a standardized CITY-BUILDING-AREA format when deterministic mappings don't exist.

### When Used

- Site name doesn't match known deterministic mappings
- Contains abbreviations, inconsistent capitalization, or varied separators
- Missing components need to be inferred

### System Prompt

```
You are a location normalization assistant specialized in standardizing site and building names for IT infrastructure management. You must always return valid JSON that strictly adheres to the specified format. Do not include any explanatory text, markdown code blocks, or formatting outside the JSON object.
```

### User Prompt Template

```
Normalize the following site/location name to a standard format following the pattern: CITY-BUILDING-AREA

Input: "{site_str}"

STRICT REQUIREMENTS:
1. Return ONLY valid JSON, no additional text, explanations, or markdown formatting
2. JSON must contain exactly one key: "site_normalized"
3. The normalized value must follow format: CITY-BUILDING-AREA (e.g., "BLR-Campus", "HQ-Building-1", "DC-1")
4. Use uppercase for city abbreviations (BLR, HQ, DC, etc.)
5. Use title case for building/area names (Campus, Building-1, Lab-1, etc.)
6. Separate components with single hyphens
7. If city cannot be determined, use "HQ" as default
8. Expand common abbreviations: "Bldg" → "Building", "Lab" → "Lab"

Examples:
- "BLR Campus" → "BLR-Campus"
- "HQ Bldg 1" → "HQ-Building-1"
- "Lab-1" → "HQ-Lab-1" (infer HQ if missing)
- "DC-1" → "DC-1"

Expected JSON structure:
{
  "site_normalized": "CITY-BUILDING-AREA"
}

Return JSON only, no other text.
```

### Expected Response Format

**JSON Structure:**
```json
{
  "site_normalized": "CITY-BUILDING-AREA"
}
```

**Strict Constraints:**
- Single key 'site_normalized' must be present
- Value must follow CITY-BUILDING-AREA format
- Use uppercase for city abbreviations
- Use title case for building/area names

### Example Input/Output

**Input:** `"BLR Campus"`

**Expected Output:**
```json
{
  "site_normalized": "BLR-Campus"
}
```

**Input:** `"HQ Bldg 1"`

**Expected Output:**
```json
{
  "site_normalized": "HQ-Building-1"
}
```

**Input:** `"Lab-1"`

**Expected Output:**
```json
{
  "site_normalized": "HQ-Lab-1"
}
```

---

## LLM Configuration

### Model
- **Model:** `gpt-4o-mini`
- **Rationale:** Cost-effective while sufficient for structured extraction tasks

### Parameters
- **Temperature:** `0.2`
- **Rationale:** Low temperature for more deterministic, consistent outputs
- **Response Format:** JSON object (enforced via `response_format={"type": "json_object"}`)

### Error Handling
- All LLM calls have try-catch blocks
- Graceful fallback to deterministic parsing if LLM fails or is unavailable
- Returns `None` if API key not set or network errors occur

---

## Design Decisions

### Why System Prompts?

System prompts establish the LLM's role and output constraints:
1. **Role Definition:** Establishes expertise context (data parsing, device classification, location normalization)
2. **Format Enforcement:** Explicitly requires JSON-only output without markdown or explanations
3. **Consistency:** Ensures uniform behavior across all invocations

### Why Structured Prompts?

User prompts include:
1. **Numbered Requirements:** Clear, unambiguous constraints
2. **Expected Structure:** Shows exact JSON format inline
3. **Examples:** Demonstrates desired normalization patterns (for site names)
4. **Explicit Constraints:** Specifies allowed values (device types, confidence levels, team names)

### Why Low Temperature?

Temperature of 0.2 balances:
- **Determinism:** Consistent outputs for same inputs
- **Flexibility:** Some creativity for handling edge cases
- **Reliability:** Minimizes hallucination risk in production DDI environment
