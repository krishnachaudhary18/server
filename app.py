from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import httpx
import os
import requests
import json
from dotenv import load_dotenv
import google.generativeai as genai
import asyncio
from functools import lru_cache
import time
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Load environment variables
load_dotenv()

app = FastAPI(title="AI Kitchen - Recipe Generator")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Models
class RecipeRequest(BaseModel):
    dish_name: str

class Ingredient(BaseModel):
    name: str
    measure: str

class NutritionInfo(BaseModel):
    calories: int
    protein: str
    carbs: str
    fat: str
    fiber: str
    sugar: Optional[str] = "0g"
    sodium: Optional[str] = "0mg"
    saturated_fat: Optional[str] = "0g"

class Recipe(BaseModel):
    id: str
    name: str
    category: str
    area: str
    instructions: List[str]
    ingredients: List[Ingredient]
    image_url: str
    prep_time: str
    cook_time: str
    servings: int
    nutrition: NutritionInfo
    youtube_url: Optional[str] = None
    related_dishes: List[str] = []
    dietary_type: Optional[str] = "Non-Veg" # Veg, Non-Veg, Vegan

# ... (existing code) ...

@app.post("/generate-recipe", response_model=Recipe)
async def generate_recipe(request: RecipeRequest):
    dish_name = request.dish_name.strip()
    if not dish_name:
        raise HTTPException(status_code=400, detail="Dish name cannot be empty")
    
    # Skip TheMealDB for now to ensure we get dietary info from Gemini, 
    # or we could fetch it and then guess, but generating is safer for this specific feature request.
    # actually, let's keep TheMealDB but default to Non-Veg if unknown, or maybe just use Gemini for everything if we want strict control?
    # The user wants "Veg or NonVeg" section. TheMealDB doesn't provide this.
    # To support this properly, we might prefer Gemini.
    # However, TheMealDB is fast. Let's try to infer it or just rely on Gemini if we want to be sure.
    # For now, let's prioritize Gemini if we want the specific "Veg/Non-Veg" tag accuracy, 
    # OR we can just add a simple heuristic for TheMealDB data (e.g. check ingredients).
    
    # Let's stick to the plan: Update Gemini prompt.
    
    if GEMINI_API_KEY:
        try:
            model = genai.GenerativeModel('gemini-2.0-flash')
            prompt = f"""Generate a detailed, authentic recipe for {dish_name} in JSON format.
            
            Determine if the dish is "Veg", "Non-Veg", or "Vegan".

Use this exact schema:
{{
    \"name\": \"Exact dish name\",
    \"category\": \"Category like Vegetarian, Chicken, Seafood, Dessert\",
    \"area\": \"Cuisine origin like Indian, Italian, Mexican\",
    \"instructions\": [\"Step 1 with details\", \"Step 2 with details\"],
    \"ingredients\": [{{\"name\": \"ingredient name\", \"measure\": \"amount like 2 cups\"}}],
    \"prep_time\": \"15 mins\",
    \"cook_time\": \"30 mins\",
    \"dietary_type\": \"Veg or Non-Veg or Vegan\"
}}

Return ONLY valid JSON, no markdown formatting."""
            response = model.generate_content(prompt)
            text = response.text.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            data = json.loads(text)
            ingredients = [Ingredient(**ing) for ing in data["ingredients"]]
            nutrition = await calculate_recipe_nutrition(ingredients, servings=4)
            image_url = await get_food_image(dish_name)
            return Recipe(
                id=f"gemini-{dish_name.lower().replace(' ', '-')}",
                name=data["name"],
                category=data["category"],
                area=data["area"],
                instructions=data["instructions"],
                ingredients=ingredients,
                image_url=image_url,
                prep_time=data.get("prep_time", "15 mins"),
                cook_time=data.get("cook_time", "30 mins"),
                servings=4,
                nutrition=nutrition,
                youtube_url=f"https://www.youtube.com/results?search_query={dish_name.replace(' ', '+')}+recipe",
                related_dishes=[],
                dietary_type=data.get("dietary_type", "Non-Veg")
            )
        except Exception as e:
            print(f"Gemini Error: {e}")
    
    # Fallback to TheMealDB if Gemini fails (or if we want to keep it as primary for speed, but it lacks dietary_type)
    # If we use TheMealDB, we need to guess dietary_type.
    recipe = await fetch_recipe_from_api(dish_name)
    if recipe:
        # Simple heuristic
        category = recipe.category.lower()
        if category in ["vegetarian", "vegan", "dessert", "pasta", "side", "starter"]:
             recipe.dietary_type = "Veg"
        elif category in ["chicken", "beef", "pork", "lamb", "seafood", "goat"]:
             recipe.dietary_type = "Non-Veg"
        else:
             recipe.dietary_type = "Non-Veg" # Default
        return recipe

    raise HTTPException(status_code=404, detail=f"Could not find or generate recipe for '{dish_name}'. Please try a different dish.")

class Suggestion(BaseModel):
    name: str
    icon: str
    category: Optional[str] = None

class SuggestionResponse(BaseModel):
    suggestions: List[Suggestion]

class IngredientSearchRequest(BaseModel):
    ingredients: str  # Comma-separated list of ingredients
    filter_type: Optional[str] = "tasty"  # tasty, healthy, or quick

class RecipeSuggestion(BaseModel):
    id: str
    name: str
    thumbnail: str
    category: Optional[str] = None
    ingredients: Optional[List[str]] = []
    instructions: Optional[str] = None

class RecipeSuggestionsResponse(BaseModel):
    recipes: List[RecipeSuggestion]
    count: int

# Simple in-memory cache
API_CACHE = {}
CACHE_EXPIRY = 3600  # 1 hour

# Expanded nutrition database with common ingredients
NUTRITION_DATABASE = {
    # Proteins
    "chicken breast": {"calories": 165, "protein": 31, "carbs": 0, "fat": 3.6, "fiber": 0, "sugar": 0, "sodium": 74},
    "chicken": {"calories": 165, "protein": 31, "carbs": 0, "fat": 3.6, "fiber": 0, "sugar": 0, "sodium": 74},
    "beef": {"calories": 250, "protein": 26, "carbs": 0, "fat": 15, "fiber": 0, "sugar": 0, "sodium": 72},
    "pork": {"calories": 242, "protein": 27, "carbs": 0, "fat": 14, "fiber": 0, "sugar": 0, "sodium": 62},
    "salmon": {"calories": 208, "protein": 20, "carbs": 0, "fat": 13, "fiber": 0, "sugar": 0, "sodium": 59},
    "tuna": {"calories": 132, "protein": 28, "carbs": 0, "fat": 1.3, "fiber": 0, "sugar": 0, "sodium": 47},
    "egg": {"calories": 155, "protein": 13, "carbs": 1.1, "fat": 11, "fiber": 0, "sugar": 1.1, "sodium": 124},
    "tofu": {"calories": 76, "protein": 8, "carbs": 1.9, "fat": 4.8, "fiber": 0.3, "sugar": 0.7, "sodium": 7},
    # Carbs
    "rice": {"calories": 130, "protein": 2.7, "carbs": 28, "fat": 0.3, "fiber": 0.4, "sugar": 0.1, "sodium": 1},
    "pasta": {"calories": 131, "protein": 5, "carbs": 25, "fat": 1.1, "fiber": 1.8, "sugar": 0.8, "sodium": 1},
    "bread": {"calories": 265, "protein": 9, "carbs": 49, "fat": 3.2, "fiber": 2.7, "sugar": 5, "sodium": 491},
    "potato": {"calories": 77, "protein": 2, "carbs": 17, "fat": 0.1, "fiber": 2.2, "sugar": 0.8, "sodium": 6},
    "sweet potato": {"calories": 86, "protein": 1.6, "carbs": 20, "fat": 0.1, "fiber": 3, "sugar": 4.2, "sodium": 55},
    # Vegetables
    "tomato": {"calories": 18, "protein": 0.9, "carbs": 3.9, "fat": 0.2, "fiber": 1.2, "sugar": 2.6, "sodium": 5},
    "onion": {"calories": 40, "protein": 1.1, "carbs": 9.3, "fat": 0.1, "fiber": 1.7, "sugar": 4.2, "sodium": 4},
    "garlic": {"calories": 149, "protein": 6.4, "carbs": 33, "fat": 0.5, "fiber": 2.1, "sugar": 1, "sodium": 17},
    "carrot": {"calories": 41, "protein": 0.9, "carbs": 9.6, "fat": 0.2, "fiber": 2.8, "sugar": 4.7, "sodium": 69},
    "broccoli": {"calories": 34, "protein": 2.8, "carbs": 6.6, "fat": 0.4, "fiber": 2.6, "sugar": 1.7, "sodium": 33},
    "spinach": {"calories": 23, "protein": 2.9, "carbs": 3.6, "fat": 0.4, "fiber": 2.2, "sugar": 0.4, "sodium": 79},
    "bell pepper": {"calories": 31, "protein": 1, "carbs": 6, "fat": 0.3, "fiber": 2.1, "sugar": 4.2, "sodium": 4},
    "mushroom": {"calories": 22, "protein": 3.1, "carbs": 3.3, "fat": 0.3, "fiber": 1, "sugar": 2, "sodium": 5},
    "lettuce": {"calories": 15, "protein": 1.4, "carbs": 2.9, "fat": 0.2, "fiber": 1.3, "sugar": 0.8, "sodium": 28},
    # Dairy
    "milk": {"calories": 61, "protein": 3.2, "carbs": 4.8, "fat": 3.3, "fiber": 0, "sugar": 5.1, "sodium": 43},
    "cheese": {"calories": 402, "protein": 25, "carbs": 1.3, "fat": 33, "fiber": 0, "sugar": 0.5, "sodium": 621},
    "yogurt": {"calories": 59, "protein": 3.5, "carbs": 3.6, "fat": 3.3, "fiber": 0, "sugar": 3.2, "sodium": 46},
    "butter": {"calories": 717, "protein": 0.9, "carbs": 0.1, "fat": 81, "fiber": 0, "sugar": 0.1, "sodium": 11},
    "cream": {"calories": 340, "protein": 2.1, "carbs": 2.8, "fat": 36, "fiber": 0, "sugar": 2.8, "sodium": 38},
    # Fats & Oils
    "olive oil": {"calories": 884, "protein": 0, "carbs": 0, "fat": 100, "fiber": 0, "sugar": 0, "sodium": 2},
    "coconut oil": {"calories": 862, "protein": 0, "carbs": 0, "fat": 100, "fiber": 0, "sugar": 0, "sodium": 0},
    # Spices & Condiments (minimal nutritional impact, using defaults)
    "salt": {"calories": 0, "protein": 0, "carbs": 0, "fat": 0, "fiber": 0, "sugar": 0, "sodium": 38758},
    "pepper": {"calories": 251, "protein": 10, "carbs": 64, "fat": 3.3, "fiber": 25, "sugar": 0.6, "sodium": 20},
    "sugar": {"calories": 387, "protein": 0, "carbs": 100, "fat": 0, "fiber": 0, "sugar": 100, "sodium": 1},
    "honey": {"calories": 304, "protein": 0.3, "carbs": 82, "fat": 0, "fiber": 0.2, "sugar": 82, "sodium": 4},
    "soy sauce": {"calories": 53, "protein": 8, "carbs": 4.9, "fat": 0.1, "fiber": 0.8, "sugar": 1.7, "sodium": 5637},
    # Fruits
    "apple": {"calories": 52, "protein": 0.3, "carbs": 14, "fat": 0.2, "fiber": 2.4, "sugar": 10, "sodium": 1},
    "banana": {"calories": 89, "protein": 1.1, "carbs": 23, "fat": 0.3, "fiber": 2.6, "sugar": 12, "sodium": 1},
    "orange": {"calories": 47, "protein": 0.9, "carbs": 12, "fat": 0.1, "fiber": 2.4, "sugar": 9, "sodium": 0},
    "lemon": {"calories": 29, "protein": 1.1, "carbs": 9.3, "fat": 0.3, "fiber": 2.8, "sugar": 2.5, "sodium": 2},
    "avocado": {"calories": 160, "protein": 2, "carbs": 8.5, "fat": 15, "fiber": 6.7, "sugar": 0.7, "sodium": 7},
    # Nuts & Seeds
    "almond": {"calories": 579, "protein": 21, "carbs": 22, "fat": 50, "fiber": 12, "sugar": 4.4, "sodium": 1},
    "peanut": {"calories": 567, "protein": 26, "carbs": 16, "fat": 49, "fiber": 8.5, "sugar": 4, "sodium": 18},
    "cashew": {"calories": 553, "protein": 18, "carbs": 30, "fat": 44, "fiber": 3.3, "sugar": 6, "sodium": 12},
}

def estimate_ingredient_weight(measure: str) -> float:
    """Convert common measurements to grams (approximate)."""
    measure_lower = measure.lower()
    import re
    number_match = re.search(r"(\d+\.?\d*)", measure_lower)
    quantity = float(number_match.group(1)) if number_match else 1.0
    if "cup" in measure_lower:
        return quantity * 200
    if "tablespoon" in measure_lower or "tbsp" in measure_lower:
        return quantity * 15
    if "teaspoon" in measure_lower or "tsp" in measure_lower:
        return quantity * 5
    if "lb" in measure_lower or "pound" in measure_lower:
        return quantity * 453.592
    if "oz" in measure_lower and "fl" not in measure_lower:
        return quantity * 28.35
    if "kg" in measure_lower:
        return quantity * 1000
    if "g" in measure_lower and "kg" not in measure_lower:
        return quantity
    if "ml" in measure_lower or "fluid" in measure_lower:
        return quantity
    if "clove" in measure_lower:
        return quantity * 3
    if any(size in measure_lower for size in ["medium", "large", "small"]):
        return quantity * 150
    if measure_lower.strip() in ["to taste", "pinch", "dash", ""]:
        return 2
    return quantity * 100

async def fetch_openfood_nutrition(ingredient_name: str) -> Optional[dict]:
    """Fetch nutrition from OpenFood Facts API with caching - DISABLED for speed."""
    # Skip slow API for better performance
    # Return None to use local database instead
    return None

def safe_float(val) -> float:
    """Safely convert value to float, handling strings with units."""
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        import re
        match = re.search(r"(\d+\.?\d*)", val)
        if match:
            return float(match.group(1))
    return 0.0

async def get_ingredient_nutrition(ingredient_name: str, measure: str) -> dict:
    """Get nutrition info for an ingredient based on measure."""
    ingredient_lower = ingredient_name.lower().strip()
    nutrition_per_100g = None
    for key, value in NUTRITION_DATABASE.items():
        if key in ingredient_lower or ingredient_lower in key:
            nutrition_per_100g = value
            break
    if not nutrition_per_100g:
        openfood = await fetch_openfood_nutrition(ingredient_name)
        nutrition_per_100g = openfood if openfood else {"calories": 50, "protein": 2, "carbs": 10, "fat": 1, "fiber": 1, "sugar": 1, "sodium": 50}
    
    weight = estimate_ingredient_weight(measure)
    multiplier = weight / 100.0
    
    return {
        "calories": int(safe_float(nutrition_per_100g.get("calories", 0)) * multiplier),
        "protein": round(safe_float(nutrition_per_100g.get("protein", 0)) * multiplier, 1),
        "carbs": round(safe_float(nutrition_per_100g.get("carbs", 0)) * multiplier, 1),
        "fat": round(safe_float(nutrition_per_100g.get("fat", 0)) * multiplier, 1),
        "fiber": round(safe_float(nutrition_per_100g.get("fiber", 0)) * multiplier, 1),
        "sugar": round(safe_float(nutrition_per_100g.get("sugar", 0)) * multiplier, 1),
        "sodium": int(safe_float(nutrition_per_100g.get("sodium", 0)) * multiplier),
    }

async def calculate_recipe_nutrition(ingredients: List[Ingredient], servings: int = 4) -> NutritionInfo:
    total = {"calories": 0, "protein": 0.0, "carbs": 0.0, "fat": 0.0, "fiber": 0.0, "sugar": 0.0, "sodium": 0}
    tasks = [get_ingredient_nutrition(ing.name, ing.measure) for ing in ingredients]
    results = await asyncio.gather(*tasks)
    for r in results:
        for k in total:
            total[k] += r.get(k, 0)
    per = {k: total[k] / servings for k in total}
    return NutritionInfo(
        calories=int(per["calories"]),
        protein=f"{per['protein']:.1f}g",
        carbs=f"{per['carbs']:.1f}g",
        fat=f"{per['fat']:.1f}g",
        fiber=f"{per['fiber']:.1f}g",
        sugar=f"{per['sugar']:.1f}g",
        sodium=f"{int(per['sodium'])}mg",
        saturated_fat=f"{per['fat'] * 0.3:.1f}g",
    )

async def fetch_recipe_from_api(dish_name: str) -> Optional[Recipe]:
    """Fetch recipe from TheMealDB API with caching."""
    # Check cache first
    cache_key = f"recipe_{dish_name.lower()}"
    if cache_key in API_CACHE:
        cached_recipe, cached_time = API_CACHE[cache_key]
        if time.time() - cached_time < CACHE_EXPIRY:
            return cached_recipe
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"https://www.themealdb.com/api/json/v1/1/search.php?s={dish_name}", timeout=1.5)  # Reduced from 5.0s
            if response.status_code == 200:
                data = response.json()
                meals = data.get("meals")
                if meals:
                    meal = meals[0]
                    
                    # Extract ingredients
                    ingredients = []
                    for i in range(1, 21):
                        ing_name = meal.get(f"strIngredient{i}")
                        measure = meal.get(f"strMeasure{i}")
                        if ing_name and ing_name.strip():
                            ingredients.append(Ingredient(name=ing_name.strip(), measure=measure.strip() if measure else "to taste"))
                    
                    # Calculate nutrition and get image in parallel
                    nutrition_task = calculate_recipe_nutrition(ingredients, servings=4)
                    image_task = get_food_image(meal.get("strMeal"), meal.get("strMealThumb"))
                    
                    nutrition, image_url = await asyncio.gather(nutrition_task, image_task)
                    
                    # Split instructions
                    instructions = [step.strip() for step in meal.get("strInstructions", "").split("\r\n") if step.strip()]
                    
                    recipe = Recipe(
                        id=f"themealdb-{meal.get('idMeal')}",
                        name=meal.get("strMeal"),
                        category=meal.get("strCategory"),
                        area=meal.get("strArea"),
                        instructions=instructions,
                        ingredients=ingredients,
                        image_url=image_url,
                        prep_time="20 mins",
                        cook_time="30 mins",
                        servings=4,
                        nutrition=nutrition,
                        youtube_url=meal.get("strYoutube"),
                        related_dishes=[]
                    )
                    # Cache the result
                    API_CACHE[cache_key] = (recipe, time.time())
                    return recipe
    except Exception as e:
        print(f"TheMealDB Error: {e}")
    return None

async def search_recipes_by_ingredients(ingredients: List[str]):
    """Placeholder – returns empty list."""
    return []

async def get_food_image(dish_name: str, meal_thumb: Optional[str] = None) -> str:
    """Fetch image - prioritize TheMealDB, then use improved Pollinations AI for food only."""
    # Check cache first
    cache_key = f"image_{dish_name.lower()}"
    if cache_key in API_CACHE:
        cached_image, cached_time = API_CACHE[cache_key]
        if time.time() - cached_time < CACHE_EXPIRY:
            return cached_image
    
    # If we have TheMealDB image, use it (fastest, most reliable)
    if meal_thumb and meal_thumb.strip():
        API_CACHE[cache_key] = (meal_thumb, time.time())
        return meal_thumb
    
    # Use Pollinations AI with improved food-specific prompt
    formatted_name = dish_name.replace(" ", "%20")
    # Enhanced prompt for better food dish images
    prompt = f"professional%20food%20photography%20plated%20{formatted_name}%20dish%20on%20white%20plate%20garnished%20restaurant%20style%20high%20resolution%20appetizing%20detailed%204k%20culinary%20art"
    # Use enhance parameter for better quality
    image_url = f"https://image.pollinations.ai/prompt/{prompt}?width=800&height=600&nologo=true&enhance=true"
    
    API_CACHE[cache_key] = (image_url, time.time())
    return image_url

class ImageResponse(BaseModel):
    image_url: str

class IngredientReplacement(BaseModel):
    ingredient: str
    recipe_name: str

class ReplacementSuggestion(BaseModel):
    original: str
    alternatives: List[str]
    notes: str

@app.get("/suggestions", response_model=SuggestionResponse)
async def get_suggestions():
    suggestions = [
        # Indian
        Suggestion(name="Butter Chicken", icon="🥘", category="Indian"),
        Suggestion(name="Biryani", icon="🍚", category="Indian"),
        Suggestion(name="Masala Dosa", icon="🥞", category="Indian"),
        Suggestion(name="Palak Paneer", icon="🥬", category="Indian"),
        Suggestion(name="Chole Bhature", icon="🍛", category="Indian"),
        Suggestion(name="Samosa", icon="🥟", category="Indian"),
        Suggestion(name="Tandoori Chicken", icon="🍗", category="Indian"),
        Suggestion(name="Dal Makhani", icon="🥣", category="Indian"),
        Suggestion(name="Rogan Josh", icon="🍖", category="Indian"),
        Suggestion(name="Vada Pav", icon="🍔", category="Indian"),

        # Italian
        Suggestion(name="Pasta Carbonara", icon="🍝", category="Italian"),
        Suggestion(name="Pizza Margherita", icon="🍕", category="Italian"),
        Suggestion(name="Lasagna", icon="🧀", category="Italian"),
        Suggestion(name="Risotto", icon="🍚", category="Italian"),
        Suggestion(name="Tiramisu", icon="🍰", category="Italian"),
        Suggestion(name="Ravioli", icon="🥟", category="Italian"),
        Suggestion(name="Focaccia", icon="🍞", category="Italian"),
        Suggestion(name="Gnocchi", icon="🥔", category="Italian"),

        # Mexican
        Suggestion(name="Tacos", icon="🌮", category="Mexican"),
        Suggestion(name="Burrito", icon="🌯", category="Mexican"),
        Suggestion(name="Guacamole", icon="🥑", category="Mexican"),
        Suggestion(name="Quesadilla", icon="🧀", category="Mexican"),
        Suggestion(name="Enchiladas", icon="🌶️", category="Mexican"),
        Suggestion(name="Nachos", icon="🌽", category="Mexican"),

        # American
        Suggestion(name="Burger", icon="🍔", category="American"),
        Suggestion(name="Mac and Cheese", icon="🧀", category="American"),
        Suggestion(name="Hot Dog", icon="🌭", category="American"),
        Suggestion(name="BBQ Ribs", icon="🍖", category="American"),
        Suggestion(name="Fried Chicken", icon="🍗", category="American"),
        Suggestion(name="Apple Pie", icon="🥧", category="American"),
        Suggestion(name="Pancakes", icon="🥞", category="American"),

        # Asian (Thai, Japanese, Chinese)
        Suggestion(name="Pad Thai", icon="🍜", category="Thai"),
        Suggestion(name="Tom Yum Soup", icon="🍲", category="Thai"),
        Suggestion(name="Green Curry", icon="🍛", category="Thai"),
        Suggestion(name="Sushi Roll", icon="🍣", category="Japanese"),
        Suggestion(name="Ramen", icon="🍜", category="Japanese"),
        Suggestion(name="Tempura", icon="🍤", category="Japanese"),
        Suggestion(name="Kung Pao Chicken", icon="🍗", category="Chinese"),
        Suggestion(name="Dim Sum", icon="🥟", category="Chinese"),
        Suggestion(name="Spring Rolls", icon="🌯", category="Chinese"),
        Suggestion(name="Peking Duck", icon="🦆", category="Chinese"),

        # European (French, Spanish, etc)
        Suggestion(name="Croissant", icon="🥐", category="French"),
        Suggestion(name="Ratatouille", icon="🍆", category="French"),
        Suggestion(name="Paella", icon="🥘", category="Spanish"),
        Suggestion(name="Fish and Chips", icon="🐟", category="British"),
        Suggestion(name="Beef Wellington", icon="🥩", category="British"),
        Suggestion(name="Goulash", icon="🍲", category="Hungarian"),
        Suggestion(name="Schnitzel", icon="🥩", category="German"),

        # Middle Eastern & Others
        Suggestion(name="Falafel", icon="🧆", category="Middle Eastern"),
        Suggestion(name="Hummus", icon="🥣", category="Middle Eastern"),
        Suggestion(name="Shakshuka", icon="🍳", category="Middle Eastern"),
        Suggestion(name="Kebab", icon="🍢", category="Middle Eastern"),
    ]
    return SuggestionResponse(suggestions=suggestions)

@app.post("/get-dish-image", response_model=ImageResponse)
async def get_dish_image_endpoint(request: RecipeRequest):
    image_url = await get_food_image(request.dish_name)
    return ImageResponse(image_url=image_url)

@app.post("/search-by-ingredients", response_model=RecipeSuggestionsResponse)
async def search_by_ingredients(request: IngredientSearchRequest):
    if not request.ingredients.strip():
        raise HTTPException(status_code=400, detail="Ingredients cannot be empty")
    ingredients = [i.strip() for i in request.ingredients.split(",") if i.strip()]
    if not ingredients:
        raise HTTPException(status_code=400, detail="Please provide at least one ingredient")
    recipes = await search_recipes_by_ingredients(ingredients)
    return RecipeSuggestionsResponse(recipes=recipes, count=len(recipes))

@app.post("/generate-recipe", response_model=Recipe)
async def generate_recipe(request: RecipeRequest):
    """Generate recipe with parallel API calls for speed."""
    dish_name = request.dish_name.strip()
    if not dish_name:
        raise HTTPException(status_code=400, detail="Dish name cannot be empty")
    
    # Try TheMealDB first (fast and has images)
    recipe = await fetch_recipe_from_api(dish_name)
    if recipe:
        return recipe
    
    # Fallback to Gemini if TheMealDB doesn't have it
    if GEMINI_API_KEY:
        try:
            model = genai.GenerativeModel('gemini-2.0-flash')
            prompt = f"""Generate a detailed, authentic recipe for {dish_name} in JSON format.

Use this exact schema:
{{
    \"name\": \"Exact dish name\",
    \"category\": \"Category like Vegetarian, Chicken, Seafood, Dessert\",
    \"area\": \"Cuisine origin like Indian, Italian, Mexican\",
    \"instructions\": [\"Step 1 with details\", \"Step 2 with details\"],
    \"ingredients\": [{{\"name\": \"ingredient name\", \"measure\": \"amount like 2 cups\"}}],
    \"prep_time\": \"15 mins\",
    \"cook_time\": \"30 mins\"
}}

Return ONLY valid JSON, no markdown formatting."""
            
            # Fetch Gemini data and image in parallel
            gemini_task = asyncio.create_task(asyncio.to_thread(model.generate_content, prompt))
            image_task = asyncio.create_task(get_food_image(dish_name))
            
            response, image_url = await asyncio.gather(gemini_task, image_task)
            
            text = response.text.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            data = json.loads(text)
            ingredients = [Ingredient(**ing) for ing in data["ingredients"]]
            
            # Calculate nutrition (fast with local DB)
            nutrition = await calculate_recipe_nutrition(ingredients, servings=4)
            
            return Recipe(
                id=f"gemini-{dish_name.lower().replace(' ', '-')}",
                name=data["name"],
                category=data["category"],
                area=data["area"],
                instructions=data["instructions"],
                ingredients=ingredients,
                image_url=image_url,
                prep_time=data.get("prep_time", "15 mins"),
                cook_time=data.get("cook_time", "30 mins"),
                servings=4,
                nutrition=nutrition,
                youtube_url=f"https://www.youtube.com/results?search_query={dish_name.replace(' ', '+')}+recipe",
                related_dishes=[],
            )
        except Exception as e:
            print(f"Gemini Error: {e}")
    
    raise HTTPException(status_code=404, detail=f"Could not find or generate recipe for '{dish_name}'. Please try a different dish.")

@app.post("/generate-recipe-from-ingredients", response_model=Recipe)
async def generate_recipe_from_ingredients(request: IngredientSearchRequest):
    """Generate a complete recipe from ingredients with filter preference."""
    ingredients_text = request.ingredients.strip()
    filter_type = request.filter_type or "tasty"
    
    if not ingredients_text:
        raise HTTPException(status_code=400, detail="Ingredients cannot be empty")
    
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini API not configured")
    
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Customize prompt based on filter
        filter_instructions = {
            "tasty": "Focus on FLAVOR and INDULGENCE. Prioritize delicious, comforting, rich flavors. Include butter, cream, cheese, or flavorful spices. No dietary restrictions.",
            "healthy": "Focus on HEALTH and NUTRITION. Prioritize low-calorie, high-protein, nutrient-dense ingredients. Minimize oil/butter. Include vegetables, lean proteins, whole grains.",
            "quick": "Focus on SPEED and SIMPLICITY. Total time (prep + cook) must be under 20 minutes. Use minimal ingredients (5-7 max). Simple cooking methods. No complex techniques."
        }
        
        filter_instruction = filter_instructions.get(filter_type, filter_instructions["tasty"])
        
        prompt = f"""Create a realistic {filter_type} recipe using these ingredients: {ingredients_text}

{filter_instruction}

IMPORTANT: Return ONLY valid JSON with this exact schema. Be REALISTIC with cooking times:
{{
    "name": "Creative dish name based on ingredients",
    "category": "Category like Chicken, Vegetarian, Seafood, etc",
    "area": "Cuisine type like American, Italian, Asian",
    "instructions": ["Detailed step 1", "Detailed step 2", "..."],
    "ingredients": [{{"name": "ingredient name", "measure": "realistic amount like 2 cups or 200g"}}],
    "prep_time": "Actual prep time in mins (e.g., 10 mins, 15 mins)",
    "cook_time": "Actual cooking time in mins (e.g., 15 mins, 30 mins)",
    "dietary_type": "Veg or Non-Veg or Vegan"
}}

Return ONLY the JSON, no markdown formatting, no explanations."""
        
        # Generate recipe and fetch image in parallel
        gemini_task = asyncio.create_task(asyncio.to_thread(model.generate_content, prompt))
        
        response = await gemini_task
        text = response.text.strip()
        
        # Parse JSON response
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        
        data = json.loads(text)
        
        # Create ingredient objects
        ingredients = [Ingredient(**ing) for ing in data["ingredients"]]
        
        # Fetch image in parallel with nutrition calculation
        dish_name = data["name"]
        nutrition_task = calculate_recipe_nutrition(ingredients, servings=4)
        image_task = get_food_image(dish_name)
        
        nutrition, image_url = await asyncio.gather(nutrition_task, image_task)
        
        return Recipe(
            id=f"gemini-ingredient-{dish_name.lower().replace(' ', '-')}",
            name=dish_name,
            category=data.get("category", "Main Course"),
            area=data.get("area", "Fusion"),
            instructions=data["instructions"],
            ingredients=ingredients,
            image_url=image_url,
            prep_time=data.get("prep_time", "15 mins"),
            cook_time=data.get("cook_time", "25 mins"),
            servings=4,
            nutrition=nutrition,
            youtube_url=f"https://www.youtube.com/results?search_query={dish_name.replace(' ', '+')}+recipe",
            related_dishes=[],
            dietary_type=data.get("dietary_type", "Non-Veg")
        )
    except json.JSONDecodeError as e:
        print(f"JSON Parse Error: {e}")
        print(f"Response text: {text[:500]}")
        raise HTTPException(status_code=500, detail="Failed to parse recipe data from AI")
    except Exception as e:
        print(f"Error generating recipe: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate recipe: {str(e)}")

@app.post("/suggest-ingredient-replacement", response_model=ReplacementSuggestion)
async def suggest_ingredient_replacement(request: IngredientReplacement):
    """Suggest alternatives for an ingredient in a recipe context."""
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini API not configured")
    
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        prompt = f"""Suggest 4-5 practical alternatives for the ingredient "{request.ingredient}" in the recipe "{request.recipe_name}".

Consider:
- Similar flavor profile
- Similar texture/function in cooking
- Common availability
- Dietary alternatives (if applicable)

Return ONLY valid JSON with this exact schema:
{{
    "original": "{request.ingredient}",
    "alternatives": ["alternative 1", "alternative 2", "alternative 3", "alternative 4"],
    "notes": "Brief note about when to use these alternatives"
}}

Return ONLY the JSON, no markdown formatting."""
        
        response = await asyncio.to_thread(model.generate_content, prompt)
        text = response.text.strip()
        
        # Parse JSON response
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        
        data = json.loads(text)
        
        return ReplacementSuggestion(
            original=data["original"],
            alternatives=data["alternatives"],
            notes=data.get("notes", "These are common substitutes.")
        )
    except Exception as e:
        print(f"Error suggesting replacement: {e}")
        # Fallback to simple alternatives
        return ReplacementSuggestion(
            original=request.ingredient,
            alternatives=["Check recipe for alternatives"],
            notes="Unable to generate suggestions at this time."
        )

# ... (existing API endpoints above) ...

# Mount the static directory to serve HTML, CSS, JS
app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve index.html at the root URL
@app.get("/")
async def read_index():
    return FileResponse('static/index.html')
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
