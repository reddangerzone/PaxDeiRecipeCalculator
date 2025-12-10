import streamlit as st
import cloudscraper
from functools import lru_cache
import pandas as pd

# --------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------

BASE = "https://data-cdn.gaming.tools/paxdei/data/en"
VERSION = "1765296186223"

scraper = cloudscraper.create_scraper(
    browser={
        "browser": "chrome",
        "platform": "linux",
        "mobile": False,
    }
)

# --------------------------------------------------------------------
# FETCH HELPERS
# --------------------------------------------------------------------

@lru_cache(maxsize=None)
def fetch_json(filename):
    """Fetch a JSON file from the Pax Dei CDN."""
    url = f"{BASE}/{filename}?version={VERSION}"
    try:
        resp = scraper.get(url)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"Failed to fetch {filename}: {e}")
        return None


@lru_cache(maxsize=None)
def load_items():
    data = fetch_json("item.json")
    items = {entry["id"]: entry for entry in data} if data else {}

    # Add wearables if available
    wearables = fetch_json("wearable.json")
    if wearables:
        for w in wearables:
            items[w["id"]] = w

    # Add consumables if needed
    consumables = fetch_json("consumable.json")
    if consumables:
        for c in consumables:
            items[c["id"]] = c

    return items


@lru_cache(maxsize=None)
def load_recipes():
    data = fetch_json("recipe.json")
    return {entry["id"]: entry for entry in data} if data else {}


# Map: output item_id → recipe_id
@lru_cache(maxsize=None)
def craftable_index():
    recipes = load_recipes()
    index = {}
    for recipe_id, recipe in recipes.items():
        for out in recipe.get("outputs", []):
            index[out["entity"]["id"]] = recipe_id
    return index

# --------------------------------------------------------------------
# DEPENDENCY RESOLVERS
# --------------------------------------------------------------------
def is_sand_item(item_id, items):
    item = items.get(item_id, {})
    return "sand" in item.get("name", "").lower()


def resolve(item_id, items, recipes, visited=None):
    """
    Return a flat dict of RAW materials for this item.
    Correctly handles quantities and avoids double-multiplying.
    """
    if visited is None:
        visited = set()

    # Special case: Sand should be treated as raw
    if is_sand_item(item_id, items):
        return {item_id: 1}

    if item_id in visited:
        return {}
    visited.add(item_id)

    craft_index = craftable_index()

    # Not craftable -> raw
    if item_id not in craft_index:
        return {item_id: 1}

    recipe = recipes[craft_index[item_id]]
    breakdown = {}

    for ing in recipe["itemIngredients"]:
        ing_id = ing["entity"]["id"]
        qty = ing["count"]

        sub_tree = resolve(ing_id, items, recipes, visited.copy())

        for material, sub_qty in sub_tree.items():
            breakdown[material] = breakdown.get(material, 0) + sub_qty * qty

    return breakdown


def resolve_craftables(item_id, items, recipes, visited=None, is_root=True):
    """
    Return intermediate craftable items.
    Stops recursion at the first craftable ingredient.
    """
    if visited is None:
        visited = set()

    # SPECIAL CASE — sand is NOT craftable
    if is_sand_item(item_id, items):
        return {}

    if item_id == "item_raw_material_mineral_sand":
        return {}

    if item_id in visited:
        return {}
    visited.add(item_id)

    craft_index = craftable_index()

    # If craftable and not the root → count it exactly once
    if not is_root and item_id in craft_index:
        return {item_id: 1}

    # Raw materials → no craftables
    if item_id not in craft_index:
        return {}

    recipe = recipes[craft_index[item_id]]
    breakdown = {}

    for ing in recipe["itemIngredients"]:
        ing_id = ing["entity"]["id"]
        qty = ing["count"]

        sub_tree = resolve_craftables(
            ing_id, items, recipes, visited.copy(), is_root=False
        )

        for craft_item, sub_qty in sub_tree.items():
            breakdown[craft_item] = breakdown.get(craft_item, 0) + sub_qty * qty

    return breakdown


def render_tree(item_id, recipes, indent=0):
    """ASCII craft tree for display."""
    craft_index = craftable_index()
    spacer = "  " * indent

    if item_id not in craft_index:
        return f"{spacer}- {item_id} (raw)\n"

    recipe = recipes[craft_index[item_id]]
    s = f"{spacer}- {recipe['name']}\n"

    for ing in recipe["itemIngredients"]:
        name = ing["entity"]["name"]
        qty = ing["count"]
        sub_id = ing["entity"]["id"]
        s += f"{spacer}  {name} x{qty}\n"
        s += render_tree(sub_id, recipes, indent + 2)

    return s


# --------------------------------------------------------------------
# UTILITIES
# --------------------------------------------------------------------

emoji_map = {
    "flowers": "🌸",
    "herbs": "🌿",
    "plants": "🌱",
    "trees": "🌲",
    "wood": "🪵",
    "minerals": "🪨",
    "gemstones": "💎",

    "alchemy": "🧪",
    "glass": "🧴",
    "metal": "⚒️",
    "smithing": "⚒️",
    "weaving": "🧵",
    "cooking": "🍳",
    "craftingcomponents": "⚙️",

    "potion": "⚗️",
    "consumable": "🧴",

    "spelltype": "✨",
    "enchanting": "🔮",

    "furniture": "🪑",
    "housing": "🏠",

    "default": "📦"
}

def get_item_emoji(item):
    for cat in item.get("categoryIds", []):
        if cat in emoji_map:
            return emoji_map[cat]
    return "📦"


def prettify_breakdown(breakdown, items):
    pretty = {}
    for item_id, qty in breakdown.items():
        item = items[item_id]
        name = item["name"]
        pretty[f"{get_item_emoji(item)} {name}"] = qty
    return dict(sorted(pretty.items(), key=lambda x: x[0]))


def prettify_craftable_breakdown(breakdown, items):
    pretty = {}
    for item_id, qty in breakdown.items():
        item = items[item_id]
        name = item["name"]
        pretty[f"{get_item_emoji(item)} {name}"] = qty
    return dict(sorted(pretty.items(), key=lambda x: x[0]))


def get_item_by_name(name, items):
    for item in items.values():
        if item["name"] == name:
            return item
    return None


def get_icon_url(item):
    if "iconPath" not in item:
        return None
    return "https://paxdei.gaming.tools" + item["iconPath"].replace("{height}", "128")


def get_recipe_crafting_info(item_id, recipes):
    craft_index = craftable_index()
    recipe_id = craft_index.get(item_id)
    if not recipe_id:
        return None

    recipe = recipes[recipe_id]
    skill = recipe.get("skillRequired", {}).get("name", "Unknown")
    level = recipe.get("skillDifficulty", "N/A")

    return {"skill": skill, "level": level}


# --------------------------------------------------------------------
# STREAMLIT UI
# --------------------------------------------------------------------

st.title("🧪 Pax Dei Crafting Calculator")

items = load_items()
recipes = load_recipes()

if not items or not recipes:
    st.error("Could not load data.")
    st.stop()

# Build craftable list
craftable_items = sorted({
    out["entity"]["name"]
    for r in recipes.values()
    for out in r.get("outputs", [])
})

choice = st.selectbox(
    "Choose an item to craft:",
    craftable_items,
    index=None,
    placeholder="Type to search for an item..."
)

if choice:
    item_data = get_item_by_name(choice, items)

    if item_data:
        with st.container(border=True):
            cols = st.columns([1, 3])
            icon = get_icon_url(item_data)
            if icon:
                cols[0].image(icon, width=72)

            cols[1].markdown(
                f"""
                ### {item_data['name']}
                **Tier:** {item_data.get('tier', 'N/A')}  
                **Item Level:** {item_data.get('itemLevel', 'N/A')}  
                **Categories:** {", ".join(item_data.get("categoryIds", []))}
                """
            )

number_to_craft = st.slider("Choose how many items to craft:", 1, 100, 1)

if choice:
    # Find ID
    target_id = None
    target_name = None
    for recipe in recipes.values():
        for out in recipe.get("outputs", []):
            if out["entity"]["name"] == choice:
                target_id = out["entity"]["id"]
                target_name = choice

    raw = resolve(target_id, items, recipes)
    raw_pretty = prettify_breakdown(raw, items)

    st.subheader("🪨 Raw Materials")
    df_raw = pd.DataFrame([
        {"Item": name, "Quantity": qty * number_to_craft}
        for name, qty in raw_pretty.items()
    ])
    st.dataframe(df_raw, hide_index=True)

    craftables = resolve_craftables(target_id, items, recipes)
    craft_pretty = prettify_craftable_breakdown(craftables, items)

    st.subheader("⚒️ Craftable Components")
    craft_rows = []

    for pretty_name, qty in craft_pretty.items():
        # find underlying ID
        for item_id, entity in items.items():
            if entity["name"] in pretty_name:
                info = get_recipe_crafting_info(item_id, recipes)
                if info:
                    craft_rows.append({
                        "Item": pretty_name,
                        "Quantity to Craft": qty * number_to_craft,
                        "Skill": info["skill"],
                        "Required Level": info["level"],
                    })
                break

    df_craft = pd.DataFrame(craft_rows)
    st.dataframe(df_craft, hide_index=True)

    st.subheader("🌳 Crafting Tree")
    st.code(render_tree(target_id, recipes))
