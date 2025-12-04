# Limitations and Trade-offs

This document outlines the concrete limitations and trade-offs of the inventory normalization approach.

## 1. Model Hallucination Risk

**Limitation:** LLMs can generate plausible but incorrect information when inferring missing or ambiguous data.

**Impact:**

- Device type classification may assign incorrect types based on weak signals
- Owner information parsing might misinterpret ambiguous formats
- Site normalization could standardize to incorrect formats

**Trade-off:** Higher accuracy vs. risk of incorrect inferences. We prioritize conservative inference (low confidence) over confident but potentially wrong answers.

---

## 2. Missing External Context

**Limitation:** The pipeline operates on isolated records without access to:

- Existing IPAM/DNS databases for validation
- Organizational directory (LDAP/Active Directory) for owner verification
- Network topology information for subnet validation
- Historical data for pattern learning

**Impact:**

- Cannot verify if IP addresses are actually in use
- Cannot validate owner emails against corporate directory
- Cannot check if FQDNs resolve correctly
- Subnet CIDR derivation is heuristic-based, not validated against actual network config

**Trade-off:** Standalone processing vs. integration complexity. We chose standalone for reproducibility, accepting that some validations require external systems.

---

## 3. Split-Horizon FQDN Unmodeled

**Limitation:** The pipeline does not model split-horizon DNS scenarios where internal and external FQDNs differ.

**Impact:**

- Single FQDN per record cannot represent both internal and external views
- Reverse PTR generation assumes single DNS view
- Domain inference does not account for split-horizon configurations

**Example:** A server might have:

- Internal FQDN: `server1.internal.corp.example.com`
- External FQDN: `server1.corp.example.com`

**Trade-off:** Simplicity vs. completeness. We prioritize standard single-FQDN model, accepting that split-horizon requires additional fields.

---

## 4. LLM Dependency and Cost

**Limitation:** LLM features require API access and incur costs per request.

**Impact:**

- Pipeline cannot run fully without OpenAI API key
- Cost scales with number of ambiguous records
- API rate limits could slow processing for large datasets
- Network dependency for LLM calls

**Trade-off:** Accuracy vs. cost/availability. We use LLM selectively, only for truly ambiguous cases, minimizing API calls.
