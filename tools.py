"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform
    """
    listings = load_listings()
    results = []

    # Tokenize description for scoring
    query_tokens = description.lower().split()

    for item in listings:
        # 1. Filter by max_price
        if max_price is not None and item["price"] > max_price:
            continue

        # 2. Filter by size (case-insensitive)
        if size is not None:
            if size.lower() not in item["size"].lower():
                continue

        # 3. Score by keyword overlap
        score = 0
        searchable_text = (
            f"{item['title']} {item['description']} {item['category']} "
            f"{' '.join(item['style_tags'])}"
        ).lower()

        for token in query_tokens:
            if token in searchable_text:
                score += 1

        # 4. Drop any listings with a score of 0
        if score > 0:
            item_with_score = item.copy()
            item_with_score["_score"] = score
            results.append(item_with_score)

    # 5. Sort by score, highest first
    results.sort(key=lambda x: x["_score"], reverse=True)

    # Remove the temporary score field before returning
    for item in results:
        del item["_score"]

    return results


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.
    """
    client = _get_groq_client()
    
    item_details = (
        f"Item: {new_item['title']}\n"
        f"Description: {new_item['description']}\n"
        f"Category: {new_item['category']}\n"
        f"Style Tags: {', '.join(new_item['style_tags'])}\n"
        f"Colors: {', '.join(new_item['colors'])}"
    )

    if not wardrobe.get("items"):
        prompt = (
            f"I'm considering buying this thrifted item:\n{item_details}\n\n"
            "My wardrobe is currently empty. Could you give me 1-2 general styling ideas "
            "for this item? What kinds of pieces would pair well with it, and what vibe does it suit?"
        )
    else:
        wardrobe_list = "\n".join([
            f"- {item['name']} ({item['category']})"
            for item in wardrobe["items"]
        ])
        prompt = (
            f"I'm considering buying this thrifted item:\n{item_details}\n\n"
            f"Here is my current wardrobe:\n{wardrobe_list}\n\n"
            "Could you suggest 1-2 complete outfits using this new item and specific pieces from my wardrobe? "
            "Explain why these pieces work together."
        )

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": "You are a helpful and stylish fashion assistant for FitFindr."},
            {"role": "user", "content": prompt}
        ],
    )

    return response.choices[0].message.content


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.
    """
    if not outfit or not outfit.strip():
        return "Error: No outfit details provided. Please generate an outfit suggestion first."

    client = _get_groq_client()

    item_name = new_item["title"]
    price = new_item["price"]
    platform = new_item["platform"]

    prompt = (
        f"Generate a short, shareable social media caption (2-4 sentences) for this thrifted find and outfit suggestion.\n\n"
        f"Item: {item_name}\n"
        f"Price: ${price}\n"
        f"Platform: {platform}\n"
        f"Outfit Suggestion: {outfit}\n\n"
        "Guidelines:\n"
        "- Feel casual and authentic (like a real OOTD post, not a product description)\n"
        "- Mention the item name, price, and platform naturally (once each)\n"
        "- Capture the outfit vibe in specific terms\n"
        "- Keep it to 2-4 sentences."
    )

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": "You are a creative social media manager for a fashion-forward thrifter."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.9,
    )

    return response.choices[0].message.content
