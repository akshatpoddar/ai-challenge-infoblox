#!/usr/bin/env python3
"""
LLM integration module for resolving ambiguous cases in data normalization.
"""

import json
import os
import re
from typing import Dict, Optional
import openai


def extract_name_from_email(email: str) -> str:
    """
    Extract name from email address in lowercase.
    
    Examples:
        jane@corp.example.com -> jane
        john.doe@corp.example.com -> john doe
        j.smith@corp.example.com -> j smith
    """
    if not email or "@" not in email:
        return ""
    
    # Get the local part (before @)
    local_part = email.split("@")[0]
    
    # Split by common separators (., _, -)
    name_parts = re.split(r'[._-]', local_part)
    
    # Keep lowercase and filter empty parts
    lowercase_parts = [part.lower() for part in name_parts if part]
    
    # Join with space
    return " ".join(lowercase_parts)



class LLMHelper:
    """Helper class for LLM interactions with prompt logging."""
    
    def __init__(self, temperature: float = 0.2):
        self.temperature = temperature
        
        # Initialize OpenAI client if available
        self.client = None
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            self.client = openai.OpenAI(api_key=api_key)
        else:
            print("Warning: OPENAI_API_KEY not set. LLM features will be disabled.")
    
    def _call_llm(self, prompt: str, system_prompt: str = None) -> Optional[str]:
        """Call LLM with structured output."""
        if not self.client:
            return None
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",  # Using cost-effective model
                messages=messages,
                temperature=self.temperature,
                response_format={"type": "json_object"} if "JSON" in prompt.upper() else None
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error calling LLM: {e}")
            return None
    
    def parse_owner_info(self, owner_str: str, context: Dict = None) -> Dict[str, str]:
        """
        Parse owner information to extract name, email, and team.
        Uses LLM for complex parsing cases.
        """
        if not owner_str or owner_str.strip() == "":
            return {"owner": "", "owner_email": "", "owner_team": ""}
        
        # Try deterministic extraction first
        from validators import extract_email_from_owner
        email = extract_email_from_owner(owner_str)
        
        # Simple cases: just email
        if owner_str.strip() == email:
            # Extract name from email
            owner_name = extract_name_from_email(email) if email else ""
            return {"owner": owner_name, "owner_email": email or "", "owner_team": ""}
        
        # Simple cases: just name or team
        if "@" not in owner_str:
            # Check if it's a team name
            team_keywords = ["platform", "ops", "operations", "sec", "security", "facilities"]
            owner_lower = owner_str.lower()
            for keyword in team_keywords:
                if keyword in owner_lower:
                    return {"owner": "", "owner_email": "", "owner_team": keyword}
            return {"owner": owner_str.strip().lower(), "owner_email": "", "owner_team": ""}
        
        # Complex case: use LLM
        # Using prompt from prompts.md (Prompt 1: parse_owner_info)
        prompt = f"""Parse the following owner information and extract structured data into a JSON object.

        Input: "{owner_str}"

STRICT REQUIREMENTS:
1. Return ONLY valid JSON, no additional text, explanations, or markdown formatting
2. JSON must contain exactly these three keys: "owner", "owner_email", "owner_team"
3. All values must be strings (use empty string "" if a field is not found)
4. Email addresses must be valid format
5. Team names must be one of: platform, ops, operations, sec, security, facilities, or empty string

        Expected JSON structure:
        {{
        "owner": "person name or empty string",
        "owner_email": "email@domain.com or empty string",
        "owner_team": "team name or empty string"
        }}

        Return JSON only, no other text."""
        
        system_prompt = "You are a data parsing assistant specialized in extracting structured information from unstructured text. You must always return valid JSON that strictly adheres to the specified format. Do not include any explanatory text, markdown code blocks, or formatting outside the JSON object."
        
        response = self._call_llm(prompt, system_prompt)
        
        if response:
            try:
                parsed = json.loads(response)
                return {
                    "owner": parsed.get("owner", "").strip().lower(),
                    "owner_email": parsed.get("owner_email", "").strip().lower(),
                    "owner_team": parsed.get("owner_team", "").strip().lower()
                }
            except json.JSONDecodeError:
                pass
        
        # Fallback: basic extraction
        parts = owner_str.split()
        owner_name = ""
        owner_team = ""
        for part in parts:
            if "@" in part:
                email = part.strip("()")
            elif part.strip("()").lower() in ["platform", "ops", "sec", "security", "facilities"]:
                owner_team = part.strip("()").lower()
            else:
                if not owner_name:
                    owner_name = part.strip("()").lower()
        
        return {
            "owner": owner_name,
            "owner_email": email or "",
            "owner_team": owner_team
        }
    
    def classify_device_type(self, hostname: str, device_type: str, notes: str = "") -> Dict[str, str]:
        """
        Classify device type using LLM when ambiguous or missing.
        """
        # If device type is already provided and confident, use it
        from validators import normalize_device_type
        normalized, confidence = normalize_device_type(device_type)
        if confidence == "high":
            return {"device_type": normalized, "device_type_confidence": confidence}
        
        # Build context
        context_parts = []
        if hostname:
            context_parts.append(f"hostname: {hostname}")
        if device_type:
            context_parts.append(f"provided_type: {device_type}")
        if notes:
            context_parts.append(f"notes: {notes}")
        
        context_str = ", ".join(context_parts)
        
        # Using prompt from prompts.md (Prompt 3: classify_device_type)
        prompt = f"""Classify the network device type based on the following context information.

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
        {{
        "device_type": "server|switch|router|printer|iot|camera|firewall|load_balancer|unknown",
        "device_type_confidence": "high|medium|low"
        }}

        Return JSON only, no other text."""
        
        system_prompt = "You are a network device classification assistant with expertise in IT infrastructure. Classify devices based on hostname patterns, naming conventions, and contextual clues. You must always return valid JSON that strictly adheres to the specified format. Do not include any explanatory text, markdown code blocks, or formatting outside the JSON object."
        
        response = self._call_llm(prompt, system_prompt)
        
        if response:
            try:
                parsed = json.loads(response)
                return {
                    "device_type": parsed.get("device_type", "unknown"),
                    "device_type_confidence": parsed.get("device_type_confidence", "low")
                }
            except json.JSONDecodeError:
                pass
        
        # Fallback
        return {"device_type": normalized or "unknown", "device_type_confidence": "low"}
    
    def normalize_site(self, site_str: str, context: Dict = None) -> str:
        """
        Normalize site name using LLM for complex variations.
        """
        if not site_str or site_str.strip().upper() == "N/A":
            return ""
        
        s = str(site_str).strip()
        
        # Simple deterministic normalization
        # Common patterns
        normalized = s.replace(" ", "-").replace("_", "-")
        normalized = re.sub(r'-+', '-', normalized)  # Collapse multiple hyphens
        
        # Known mappings
        site_mappings = {
            "blr campus": "BLR-Campus",
            "blr": "BLR-Campus",
            "hq bldg 1": "HQ-Building-1",
            "hq-building-1": "HQ-Building-1",
            "hq": "HQ-Building-1",
            "lab-1": "HQ-Lab-1",
            "dc-1": "DC-1"
        }
        
        if normalized.lower() in site_mappings:
            return site_mappings[normalized.lower()]
        
        # Use LLM for complex cases
        # Using prompt from prompts.md (Prompt 2: normalize_site)
        prompt = f"""Normalize the following site/location name to a standard format following the pattern: CITY-BUILDING-AREA

        Input: "{s}"

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
        {{
        "site_normalized": "CITY-BUILDING-AREA"
        }}

        Return JSON only, no other text."""
        
        system_prompt = "You are a location normalization assistant specialized in standardizing site and building names for IT infrastructure management. You must always return valid JSON that strictly adheres to the specified format. Do not include any explanatory text, markdown code blocks, or formatting outside the JSON object."
        
        response = self._call_llm(prompt, system_prompt)
        
        if response:
            try:
                parsed = json.loads(response)
                return parsed.get("site_normalized", normalized)
            except json.JSONDecodeError:
                pass
        
        return normalized
    
    def infer_fqdn_domain(self, hostname: str, site: str, owner_email: str = "") -> str:
        """
        Infer FQDN domain from context.
        """
        # Try to extract domain from email
        if owner_email and "@" in owner_email:
            domain = owner_email.split("@")[1]
            return domain
        
        # Site-based mapping
        site_lower = site.lower() if site else ""
        if "blr" in site_lower or "bangalore" in site_lower:
            return "blr.corp.example.com"
        elif "hq" in site_lower or "headquarters" in site_lower:
            return "hq.corp.example.com"
        elif "dc" in site_lower or "datacenter" in site_lower:
            return "dc.corp.example.com"
        
        # Default
        return "corp.example.com"
    
