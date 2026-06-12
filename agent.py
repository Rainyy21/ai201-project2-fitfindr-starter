"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import json
import re
from tools import search_listings, suggest_outfit, create_fit_card, _get_groq_client


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.
    """
    # Step 1: Initialize the session
    session = _new_session(query, wardrobe)

    # Step 2: Parse the user's query using the LLM for robustness
    client = _get_groq_client()
    parse_prompt = (
        "Extract the search parameters from this user query for secondhand clothes.\n"
        "Return a JSON object with keys 'description' (str), 'size' (str or null), and 'max_price' (float or null).\n"
        f"Query: \"{query}\"\n"
        "JSON:"
    )
    
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "You are a specialized parser that outputs only raw JSON."},
                {"role": "user", "content": parse_prompt}
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        parsed_data = json.loads(response.choices[0].message.content)
        session["parsed"] = parsed_data
    except Exception as e:
        # Fallback to simple regex if LLM fails
        price_match = re.search(r"\$(\d+)", query)
        session["parsed"] = {
            "description": query,
            "size": None,
            "max_price": float(price_match.group(1)) if price_match else None
        }

    # Step 3: Call search_listings()
    results = search_listings(
        description=session["parsed"].get("description", query),
        size=session["parsed"].get("size"),
        max_price=session["parsed"].get("max_price")
    )
    session["search_results"] = results

    if not results:
        session["error"] = (
            f"I couldn't find any items matching '{session['parsed'].get('description')}'. "
            "Try broadening your search or adjusting your price/size filters."
        )
        return session

    # Step 4: Select the top result
    session["selected_item"] = results[0]

    # Step 5: Call suggest_outfit()
    try:
        session["outfit_suggestion"] = suggest_outfit(session["selected_item"], wardrobe)
    except Exception as e:
        session["error"] = f"Error generating outfit suggestion: {e}"
        return session

    # Step 6: Call create_fit_card()
    try:
        session["fit_card"] = create_fit_card(session["outfit_suggestion"], session["selected_item"])
    except Exception as e:
        session["error"] = f"Error generating fit card: {e}"
        return session

    # Step 7: Return the session
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
