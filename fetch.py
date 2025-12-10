import cloudscraper

BASE = "https://data-cdn.gaming.tools/paxdei/data/en"

scraper = cloudscraper.create_scraper(
    browser={
        "browser": "chrome",
        "platform": "linux",
        "mobile": False
    }
)

def fetch_json(filename):
    url = f"{BASE}/{filename}"
    try:
        resp = scraper.get(url)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[ERROR] Failed to fetch {url}: {e}")
        return None

def load_items():
    data = fetch_json("item.json?version=1765296186223")
    return {entry["id"]: entry for entry in data} if data else {}

def load_recipes():
    data = fetch_json("recipe.json?version=1765296186223")
    return {entry["id"]: entry for entry in data} if data else {}

if __name__ == "__main__":
    items = load_items()
    recipes = load_recipes()

    print("ITEMS LOADED:", len(items))
    print("RECIPES LOADED:", len(recipes))

    # Show one recipe
    first_key = next(iter(recipes))
    print("\nSample Recipe:")
    print(recipes[first_key])

craftable_items = {}

for recipe_id, recipe in recipes.items():
    for output in recipe["outputs"]:
        craftable_items[output["entity"]["id"]] = recipe_id

print("CRAFTABLE ITEMS:", len(craftable_items))

def resolve(item_id, items, recipes, visited=None):
    if visited is None:
        visited = set()

    if item_id in visited:
        return {}  # prevent infinite loops (shouldn't happen)
    visited.add(item_id)

    # Is it craftable?
    # Look up if there's a recipe that outputs this item
    recipe = None
    for r in recipes.values():
        for out in r["outputs"]:
            if out["entity"]["id"] == item_id:
                recipe = r
                break
        if recipe:
            break

    # If no recipe: it's a raw material
    if not recipe:
        return {item_id: 1}  # 1 depends on quantity requested

    breakdown = {}

    # For each ingredient, recursively break it down
    for ingredient in recipe["itemIngredients"]:
        ing_id = ingredient["entity"]["id"]
        qty = ingredient["count"]

        sub_tree = resolve(ing_id, items, recipes, visited)
        for k, v in sub_tree.items():
            breakdown[k] = breakdown.get(k, 0) + v * qty

    return breakdown

tree = resolve("activatable_potion_potion_of_protection_medium_61", items, recipes)
print(tree)

