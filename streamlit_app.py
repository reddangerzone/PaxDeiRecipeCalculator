import streamlit as st
import pandas as pd
import json
import os
from functools import lru_cache

# --------------------------------------------------------------------
# LOCAL DATA LOADER
# --------------------------------------------------------------------

def load_local_json(filename):
    """Load a JSON file from the local /data folder."""
    path = os.path.join("data", filename)
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Error loading {filename}: {e}")
        return None


@lru_cache(maxsize=None)
def load_items():
    """Load items + wearables + consumables into a single dict."""
    items = {}

    # Base items
    base_items = load_local_json("item.json")
    if base_items:
        for entry in base_items:
            items[entry["id"]] = entry

    # Wearables
    wearables = load_local_json("wearable.json")
    if wearables:
        for w in wearables:
            items[w["id"]] = w

    # Consumables
    consumables = load_local_json("consumable.json")
    if consumables:
        for c in consumables:
            items[c["id"]] = c

    return items


@lru_cache(maxsize=None)
def load_recipes():
    data = load_local_json("recipe.json")
    return {entry["id"]: entry for entry in data} if data else {}


# --------------------------------------------------------------------
# CRAFTABLE INDEX
# --------------------------------------------------------------------
@lru_cache(maxsize=None)
def craftable_index():
    """Map output_item_id → recipe_id"""
    index = {}
    for recipe_id, recipe in load_recipes().items():
        for out in recipe.get("outputs", []):
            index[out["entity"]["id"]] = recipe_id
    return index


# --------------------------------------------------------------------
# SPECIAL CASE: Sand → do NOT recurse into Limestone
# --------------------------------------------------------------------
def is_sand_item(item_id, items):
    return "sand" in items.get(item_id, {}).get("name", "").lower()

def is_charcoal_item(item_id, items):
    return "charcoal" in items.get(item_id, {}).get("name", "").lower()

# --------------------------------------------------------------------
# RAW MATERIAL RESOLVER
# --------------------------------------------------------------------
def resolve(item_id, items, recipes, visited=None, needed=1):
    """Return raw materials for item_id, guaranteed to return a dict."""
    if visited is None:
        visited = set()

    # Prevent loops
    if item_id in visited:
        return {}
    visited.add(item_id)

    # Terminal materials (stop recursion entirely)
    if is_sand_item(item_id, items) or is_charcoal_item(item_id, items):
        return {item_id: needed}

    craft_index = craftable_index()

    # Not craftable → raw item
    if item_id not in craft_index:
        return {item_id: needed}

    recipe = recipes.get(craft_index[item_id])
    if not recipe:
        # SAFETY: bad or missing recipe
        return {item_id: needed}

    outputs = recipe.get("outputs", [])
    if not outputs:
        # SAFETY: corrupt recipe with no outputs
        return {item_id: needed}

    output_stack = outputs[0].get("count", 1)
    crafts_needed = (needed + output_stack - 1) // output_stack

    breakdown = {}

    for ing in recipe.get("itemIngredients", []):
        ing_id = ing["entity"]["id"]
        qty_per_craft = ing["count"]
        sub_needed = qty_per_craft * crafts_needed

        sub_tree = resolve(
            ing_id, items, recipes,
            visited=visited.copy(),
            needed=sub_needed
        )

        # ——— SAFETY: enforce dict ———
        if not isinstance(sub_tree, dict):
            sub_tree = {}
        # ————————————————

        for mat, qty in sub_tree.items():
            breakdown[mat] = breakdown.get(mat, 0) + qty

    return breakdown



# --------------------------------------------------------------------
# INTERMEDIATE CRAFTABLE RESOLVER
# --------------------------------------------------------------------
def resolve_craftables(item_id, items, recipes, visited=None, needed=1, is_root=True):
    """Return craftable intermediates for item_id. Guaranteed safe return of dict."""
    if visited is None:
        visited = set()

    # Prevent recursion loops
    if item_id in visited:
        return {}
    visited.add(item_id)

    # Terminal materials: do not recurse
    if is_sand_item(item_id, items) or is_charcoal_item(item_id, items):
        return {}

    craft_index = craftable_index()

    # Raw materials never produce intermediates
    if item_id not in craft_index:
        return {}

    # How many crafts needed?
    recipe_id = craft_index.get(item_id)
    recipe = recipes.get(recipe_id)
    if not recipe:
        return {}

    outputs = recipe.get("outputs", [])
    if not outputs:
        return {}

    output_stack = outputs[0].get("count", 1)
    crafts_needed = (needed + output_stack - 1) // output_stack

    # If craftable and not root, this item *is* an intermediate
    if not is_root:
        return {item_id: crafts_needed}

    breakdown = {}

    # Process ingredient list safely
    for ing in recipe.get("itemIngredients", []):
        entity = ing.get("entity", {})
        ing_id = entity.get("id")
        qty_per_craft = ing.get("count", 1)

        # Safety: missing ID
        if not ing_id:
            continue

        sub_needed = qty_per_craft * crafts_needed

        sub_tree = resolve_craftables(
            ing_id, items, recipes,
            visited=visited.copy(),
            needed=sub_needed,
            is_root=False
        )

        # ——— SAFETY PATCH ———
        if not isinstance(sub_tree, dict):
            sub_tree = {}
        # ————————————————

        for mat, qty in sub_tree.items():
            breakdown[mat] = breakdown.get(mat, 0) + qty

    return breakdown



# --------------------------------------------------------------------
# TREE RENDER
# --------------------------------------------------------------------
def render_tree(item_id, recipes, indent=0):
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
    "flowers": "🌸", "herbs": "🌿", "plants": "🌱", "trees": "🌲",
    "wood": "🪵", "minerals": "🪨", "gemstones": "💎",
    "alchemy": "🧪", "glass": "🧴", "metal": "⚒️",
    "weaving": "🧵", "cooking": "🍳",
    "potion": "⚗️", "consumable": "🧴",
    "spelltype": "✨", "enchanting": "🔮",
    "housing": "🏠", "furniture": "🪑",
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
        pretty[f"{get_item_emoji(item)} {item['name']}"] = qty
    return dict(sorted(pretty.items()))


def get_item_by_name(name, items):
    for i in items.values():
        if i["name"] == name:
            return i
    return None


def get_icon_url(item):
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

def get_output_count(item_id, recipes):
    craft_index = craftable_index()
    recipe_id = craft_index.get(item_id)
    if not recipe_id:
        return 1  # raw material, no output stack
    recipe = recipes[recipe_id]
    return recipe["outputs"][0].get("count", 1)



# --------------------------------------------------------------------
# STREAMLIT UI
# --------------------------------------------------------------------
st.title("🧪 Pax Dei Crafting Calculator")

items = load_items()
recipes = load_recipes()

if not items or not recipes:
    st.error("Failed to load local data files.")
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
    placeholder="Type to search..."
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

number_to_craft = st.slider("How many to craft?", 1, 100, 1)

if choice:
    # Find internal ID
    target_id = None
    for r in recipes.values():
        for out in r["outputs"]:
            if out["entity"]["name"] == choice:
                target_id = out["entity"]["id"]

    # Raw materials
    raw = resolve(target_id, items, recipes, needed=number_to_craft)
    raw_pretty = prettify_breakdown(raw, items)

    st.subheader("🪨 Raw Materials Needed")
    df_raw = pd.DataFrame([
        {"Item": name, "Quantity": qty * number_to_craft}
        for name, qty in raw_pretty.items()
    ])
    st.dataframe(df_raw, hide_index=True)

    # Craftable components
    craftables = resolve_craftables(target_id, items, recipes, needed=number_to_craft)
    craft_rows = []
    for item_id, qty in craftables.items():
        info = get_recipe_crafting_info(item_id, recipes)
        display_name = f"{get_item_emoji(items[item_id])} {items[item_id]['name']}"

        craft_rows.append({
            "Item": display_name,
            "Quantity": qty * number_to_craft,
            "Skill": info["skill"],
            "Required Level": info["level"]
        })

    st.subheader("⚒️ Intermediate Crafting")
    df_craft = pd.DataFrame(craft_rows)
    st.dataframe(df_craft, hide_index=True)

    st.subheader("🌳 Crafting Tree")
    st.code(render_tree(target_id, recipes))
