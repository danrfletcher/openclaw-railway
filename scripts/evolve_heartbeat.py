#!/usr/bin/env python3
"""
Heartbeat Evolution Engine
Optimized for Artificial Analysis V2 API Schema with Top 5 Fallback Chain.
"""

import json
import re
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone

# Configuration
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
ARTIFICIAL_ANALYSIS_URL = "https://artificialanalysis.ai/api/v2/data/llms/models"
EXCLUDE_KEYWORDS = ["rerank", "embed", "base", "whisper", "tts", "dall-e", "stable-diffusion", "upscale"]

def log(message):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{timestamp}] {message}")

def fetch_json(url, headers=None):
    if headers is None:
        headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        log(f"Error fetching {url}: {e}")
        return None

def fetch_openrouter_free_models():
    log("Fetching OpenRouter models...")
    data = fetch_json(OPENROUTER_MODELS_URL)
    if not data or "data" not in data:
        return []
    
    free_models = []
    for m in data.get("data", []):
        model_id = m.get("id", "").lower()
        if any(kw in model_id for kw in EXCLUDE_KEYWORDS):
            continue
        pricing = m.get("pricing", {})
        try:
            # Check if prompt cost is 0
            if float(pricing.get("prompt", "1")) == 0.0:
                free_models.append({
                    "id": m.get("id"),
                    "name": m.get("name", ""),
                    "context_length": m.get("context_length", 0)
                })
        except (ValueError, TypeError):
            continue
    log(f"Found {len(free_models)} free models on OpenRouter.")
    return free_models

def fetch_aa_benchmarks(api_key):
    log("Fetching Artificial Analysis benchmarks...")
    headers = {"User-Agent": "Mozilla/5.0", "x-api-key": api_key}
    response = fetch_json(ARTIFICIAL_ANALYSIS_URL, headers=headers)
    
    if response and isinstance(response, dict) and "data" in response:
        log(f"Successfully retrieved {len(response['data'])} benchmarks from AA.")
        return response["data"]
    
    log("CRITICAL: AA API response format unexpected or empty.")
    return []

def normalize(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())

def find_best_match(or_model, aa_models):
    or_id_norm = normalize(or_model["id"])
    or_name_norm = normalize(or_model["name"])
    
    for aa in aa_models:
        aa_name = aa.get("name") or ""
        aa_slug = aa.get("slug") or ""
        aa_name_norm = normalize(aa_name)
        aa_slug_norm = normalize(aa_slug)
        
        if aa_name_norm and (aa_name_norm in or_id_norm or aa_name_norm in or_name_norm or or_name_norm in aa_name_norm):
            return aa
        if aa_slug_norm and (aa_slug_norm in or_id_norm):
            return aa
    return None

def score_model(or_model, aa_entry):
    evals = aa_entry.get("evaluations", {})
    
    try:
        iq = float(evals.get("artificial_analysis_intelligence_index") or 0)
        coding = float(evals.get("artificial_analysis_coding_index") or 0)
    except (ValueError, TypeError):
        iq, coding = 0, 0
    
    base_score = (iq * 0.7) + (coding * 0.3)
    context_bonus = (min(or_model["context_length"], 128000) / 128000) * 5
    
    return round(base_score + context_bonus, 2), iq

def main():
    api_key = os.environ.get("ARTIFICIAL_ANALYSIS_API_KEY")
    if not api_key:
        log("CRITICAL: ARTIFICIAL_ANALYSIS_API_KEY environment variable not set.")
        return

    or_free = fetch_openrouter_free_models()
    aa_benchmarks = fetch_aa_benchmarks(api_key)
    
    if not or_free or not aa_benchmarks:
        log("CRITICAL: Could not retrieve necessary data.")
        return

    scored_list = []
    for model in or_free:
        match = find_best_match(model, aa_benchmarks)
        if match:
            score, iq = score_model(model, match)
            if score > 0:
                scored_list.append({"id": model["id"], "score": score, "iq": iq})
                log(f"  Matched: {model['id']} -> IQ: {iq}, Final Score: {score}")

    if not scored_list:
        log("No benchmark matches found. Defaulting to baseline.")
        print("FINAL_MODEL_LIST: google/gemini-flash-1.5")
        return

    # Sort by score descending
    scored_list.sort(key=lambda x: x["score"], reverse=True)
    
    # Extract Top 5 for the fallback chain
    top_5_models = [item["id"] for item in scored_list[:5]]
    fallback_chain = ",".join(top_5_models)
    
    log(f"WINNER: {top_5_models[0]} (Score: {scored_list[0]['score']})")
    log(f"FALLBACK CHAIN: {fallback_chain}")
    
    # Final output for OpenClaw Agent consumption
    print(f"FINAL_MODEL_LIST: {fallback_chain}")

if __name__ == "__main__":
    main()