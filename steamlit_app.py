import streamlit as st
import cloudscraper
from functools import lru_cache
import pandas as pd
import json

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
def fetch_json(filename: str):
    """Fetch a JSON file from the Pax Dei CDN with versioning."""
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
    """Base Item entities (materials, components, etc.)."""
    data = fetch_json("item.json")
    return {entry["id"]: entry for entry in data} if data else {}


@lru_cache(maxsize=None)
def load_consumables():
    """Consumable entities (potions, food, etc.)."""
    data = fetch_json("consumable.json")
    return {entry["id"]: entry for entry in data} if data else {}


@lru_cache(maxsize=None)
def load_wearables():
    """Wearable entities (gear like Pilgrim pieces, jewelry, hats, etc.)."""
    data = fetch_json("wearable.json")
    return {entry["id"]: entry for entry in data} if data else {}


@lru_cache(maxsize=None)
def load_recipes():
    """All recipes (including for gear & consumables)."""
    data = fetch_json("recipe.json")
    return {entry["id"]: entry for entry in data} if data else {}


@lru_cache(maxsize=None)
def load_entities():
    """
    Unified entity dict:
    - Items
    - Consumables
    - Wearables
    So we can show names/icons/tier for anything.
    """
    entities = {}
    entities.update(load_items())
    entities.update(load_consumables())
    entities.update(load_wearables())
    return entities


# Map: output item_id → recipe_id
@lru_cache(maxsize=None)
def craftable_index():
    recipes = load_recipes()
    index = {}
    for recipe_id, recipe in recipes.items():
        for output in recipe.get("outputs", []):
            index[output["entity"]["id"]] = recipe_id
    return index


# --------------------------------------------------------------------
# DEPENDENCY RESOLVER
# --------------------------------------------------------------------


def resolve(item_id, recipes, visited=None):
    """
    Return flat dict of raw-ish materials required for item_id.
    "Raw" here means "not further craftable" in this dataset.
    """
    if visited is None:
        visited = set()

    if item_id in visited:
        return {}
    visited.add(item_id)

    craft_index = craftable_index()

    # If not craftable, treat as a base material
    if item_id not in craft_index:
        return {item_id: 1}

    recipe = recipes[craft_index[item_id]]
    breakdown = {}

    for ing in recipe.get("itemIngredients", []):
        ing_id = ing["entity"]["id"]
        qty = ing["count"]

        sub_tree = resolve(ing_id, recipes, visited)
        for k, v in sub_tree.items():
            breakdown[k] = breakdown.get(k, 0) + v * qty

    return breakdown


def resolve_craftables(item_id, recipes, visited=None, is_root=True):
    """
    Return all intermediate craftable items and how many are needed.
    - Root item is not counted as an intermediate.
    - Any craftable ingredient is counted once per chain.
    """
    if visited is None:
        visited = set()

    if item_id in visited:
        return {}
    visited.add(item_id)

    craft_index = craftable_index()
    breakdown = {}

    # If item is craftable and not the root, count it and stop.
    if item_id in craft_index and not is_root:
        return {item_id: 1}

    # If item is NOT craftable → no intermediate craft needed
    if item_id not in craft_index:
        return {}

    recipe = recipes[craft_index[item_id]]

    for ing in recipe.get("itemIngredients", []):
        ing_id = ing["entity"]["id"]
        qty = ing["count"]

        sub_tree = resolve_craftables(ing_id, recipes, visited, is_root=False)
        for k, v in sub_tree.items():
            breakdown[k] = breakdown.get(k, 0) + v * qty

    return breakdown


def render_tree(item_id, recipes, entities, indent=0):
    """ASCII crafting tree using names where possible."""
    craft_index = craftable_index()
    spacer = "  " * indent

    ent = entities.get(item_id, {})
    base_name = ent.get("name", item_id)

    if item_id not in craft_index:
        return f"{spacer}- {base_name} (raw)\n"

    recipe = recipes[craft_index[item_id]]
    output_name = recipe.get("name", base_name)

    s = f"{spacer}- {output_name}\n"
    for ing in recipe.get("itemIngredients", []):
        name = ing["entity"]["name"]
        count = ing["count"]
        sub_id = ing["entity"]["id"]
        s += f"{spacer}  {name} x{count}\n"
        s += render_tree(sub_id, recipes, entities, indent + 2)

    return s


# --------------------------------------------------------------------
# PRETTY HELPERS
# --------------------------------------------------------------------

def get_recipe_crafting_info(item_id, recipes):
    """Return crafting skill, required level, and workstation if determinable."""
    craft_index = craftable_index()
    recipe_id = craft_index.get(item_id)
    if not recipe_id:
        return None

    recipe = recipes[recipe_id]

    skill = recipe.get("skillRequired", {}).get("name", "Unknown skill")
    level = recipe.get("skillDifficulty", "N/A")


    return {
        "skill": skill,
        "level": level
    }


def get_item_name(item_id, entities):
    """Safe name lookup with fallback."""
    return entities.get(item_id, {}).get("name", item_id)


emoji_map = {
    # Natural resources
    "flowers": "🌸",
    "herbs": "🌿",
    "plants": "🌱",
    "trees": "🌲",
    "wood": "🪵",
    "minerals": "🪨",
    "gemstones": "💎",

    # Crafting categories
    "alchemy": "🧪",
    "glass": "🧴",
    "metal": "⚒️",
    "smithing": "⚒️",
    "weaving": "🧵",
    "cooking": "🍳",
    "craftingcomponents": "⚙️",

    # Potions / Consumables
    "potion": "⚗️",
    "consumable": "🧴",
    "food": "🍲",

    # Magic & enchanting
    "spelltype": "✨",
    "enchanting": "🔮",

    # Furniture / Housing
    "furniture": "🪑",
    "containers": "🗃️",
    "housing": "🏠",

    # Generic fallback
    "default": "📦",
}


def get_item_emoji(entity):
    for cat in entity.get("categoryIds", []):
        if cat in emoji_map:
            return emoji_map[cat]
    return emoji_map["default"]


def prettify_breakdown(breakdown, entities):
    """
    Turn {id: qty} into {"🧪 Soapwort Extract": qty} using unified entities.
    """
    pretty = {}
    for item_id, qty in breakdown.items():
        entity = entities.get(item_id)
        if not entity:
            name = item_id
            icon = emoji_map["default"]
        else:
            name = entity["name"]
            icon = get_item_emoji(entity)
        pretty[f"{icon} {name}"] = qty

    return dict(sorted(pretty.items(), key=lambda x: x[0]))


def prettify_craftable_breakdown(breakdown, entities):
    """
    Same as prettify_breakdown but semantically for craftable intermediates.
    """
    return prettify_breakdown(breakdown, entities)


def get_entity_by_name(name, entities):
    """Find any entity (item, wearable, consumable) by name."""
    for ent in entities.values():
        if ent["name"] == name:
            return ent
    return None


def get_icon_url(entity):
    if not entity or "iconPath" not in entity:
        return None
    return "https://paxdei.gaming.tools" + entity["iconPath"].replace("{height}", "128")


# --------------------------------------------------------------------
# STREAMLIT UI
# --------------------------------------------------------------------

st.title("🧪 Pax Dei Crafting Calculator")

items = load_items()
recipes = load_recipes()
entities = load_entities()

if not items or not recipes:
    st.error("Could not load data.")
    st.stop()

# Build list of craftable item names (from recipe outputs)
craftable_names = []
for recipe in recipes.values():
    for out in recipe.get("outputs", []):
        craftable_names.append(out["entity"]["name"])

craftable_names = sorted(set(craftable_names))

# Search box + filtered dropdown (Option B from earlier)
search = st.text_input("Search for an item to craft:")
if search:
    filtered_names = [n for n in craftable_names if search.lower() in n.lower()]
else:
    filtered_names = craftable_names

if not filtered_names:
    st.warning("No items match your search.")
    st.stop()

choice = st.selectbox(
    "Choose an item to craft:",
    filtered_names,
    index=0,
)

# Item info card
if choice:
    entity = get_entity_by_name(choice, entities)

    if entity:
        with st.container(border=True):
            cols = st.columns([1, 3])

            # Icon
            icon_url = get_icon_url(entity)
            if icon_url:
                cols[0].image(icon_url, width=72)

            # Text info
            cols[1].markdown(
                f"""
                ### {entity['name']}
                **Tier:** {entity.get('tier', 'N/A')}  
                **Item Level:** {entity.get('itemLevel', 'N/A')}  
                **Categories:** {", ".join(entity.get("categoryIds", []))}
                """
            )

# How many to craft?
number_to_craft = st.slider("Choose how many items to craft (up to 100):", 1, 100, 1)

if choice:
    # Find ID of the chosen item (from recipe outputs)
    target_id = None
    target_name = None
    for recipe in recipes.values():
        for out in recipe.get("outputs", []):
            if out["entity"]["name"] == choice:
                target_id = out["entity"]["id"]
                target_name = out["entity"]["name"]
                break
        if target_id:
            break

    if not target_id:
        st.error("Could not resolve the selected item to an ID.")
        st.stop()

    # Raw materials (non-craftable in this dataset)
    raw = resolve(target_id, recipes)
    pretty_raw = prettify_breakdown(raw, entities)

    st.subheader("🪨 Raw Materials")

    df_raw = pd.DataFrame(
        [
            {"Item": name, "Quantity": qty * number_to_craft}
            for name, qty in pretty_raw.items()
        ]
    )
    st.dataframe(df_raw, hide_index=True)

    # Craftable intermediate components
    craftables = resolve_craftables(target_id, recipes)
    pretty_craft = prettify_craftable_breakdown(craftables, entities)

    st.subheader("⚒️ Craftable Components")

    craft_rows = []

    for pretty_name, qty in pretty_craft.items():
        # We need the underlying item ID:
        # Reverse lookup based on pretty label
        for item_id, entity in entities.items():
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

    # Tree
    st.subheader("🌳 Crafting Tree")
    tree_text = render_tree(target_id, recipes, entities)
    st.code(tree_text)
