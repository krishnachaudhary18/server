const API_URL = '';

// DOM Elements
const dishInput = document.getElementById('dishInput');
const searchBtn = document.getElementById('searchBtn');
const loading = document.getElementById('loading');
const errorAlert = document.getElementById('errorAlert');
const suggestionsSection = document.getElementById('suggestionsSection');
const suggestionsGrid = document.getElementById('suggestionsGrid');

// State
let currentMode = 'recipe'; // 'recipe' or 'parse'
let currentFilter = 'tasty'; // 'tasty', 'healthy', or 'quick'
let currentRecipe = null;
let originalServings = 4;

// Mode toggle
document.querySelectorAll('.mode-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentMode = btn.dataset.mode;

        const dishInput = document.getElementById('dishInput');
        const sectionTitle = document.querySelector('.section-title');
        const filterOptions = document.getElementById('filterOptions');

        if (currentMode === 'recipe') {
            if (dishInput) {
                dishInput.placeholder = "Enter any dish name... Try 'Vegan Buddha Bowl' or 'Chocolate Mousse'";
            }
            if (filterOptions) filterOptions.style.display = 'none';
            loadSuggestions(); // Reload default suggestions
            if (sectionTitle) {
                sectionTitle.textContent = 'âœ¨ Popular Recipes';
            }
        } else {
            if (dishInput) {
                dishInput.placeholder = "Enter ingredients separated by commas (e.g. chicken, rice, garlic)";
            }
            if (filterOptions) filterOptions.style.display = 'block';
            if (sectionTitle) {
                sectionTitle.textContent = 'ðŸ“ Recipe Suggestions';
            }
            if (suggestionsGrid) {
                suggestionsGrid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--gray-600);">Enter ingredients above to find recipes!</div>';
            }
        }
    });
});

// Filter button toggle
document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentFilter = btn.dataset.filter;
    });
});

// Load suggestions
async function loadSuggestions() {
    try {
        const response = await fetch(`${API_URL}/suggestions`);
        const data = await response.json();

        suggestionsGrid.innerHTML = data.suggestions.map(suggestion => `
            <div class="suggestion-card" onclick="searchRecipe('${suggestion.name}')">
                <div class="suggestion-icon">${suggestion.icon}</div>
                <div class="suggestion-name">${suggestion.name}</div>
            </div>
        `).join('');
    } catch (error) {
        console.error('Failed to load suggestions:', error);
    }
}

// Show error
function showError(message) {
    errorAlert.textContent = message;
    errorAlert.classList.add('show');
    setTimeout(() => errorAlert.classList.remove('show'), 5000);
}

// Hide recipe
function hideRecipe() {
    document.getElementById('recipeDisplay').style.display = 'none';
    suggestionsSection.style.display = 'block';
}

// Display recipe in the beautiful new UI
function displayRecipe(recipe) {
    currentRecipe = recipe;
    originalServings = recipe.servings || 1;

    // Show the recipe display section
    document.getElementById('recipeDisplay').style.display = 'block';

    // Hide suggestions
    suggestionsSection.style.display = 'none';

    // Scroll to top
    window.scrollTo({ top: 0, behavior: 'smooth' });

    // Set recipe title
    const recipeTitleNew = document.querySelector('#recipeDisplay #recipeTitle');
    recipeTitleNew.textContent = recipe.name || 'Delicious Recipe';

    // Set recipe image
    const recipeImageNew = document.querySelector('#recipeDisplay #recipeImage');
    recipeImageNew.src = recipe.image_url || 'https://via.placeholder.com/900x400?text=Recipe+Image';
    recipeImageNew.alt = recipe.name || 'Recipe';

    // Improved error handling with multiple fallbacks
    recipeImageNew.onerror = function () {
        this.onerror = null;
        // Try a high-quality Unsplash source as first fallback
        if (!this.dataset.triedUnsplash) {
            this.dataset.triedUnsplash = 'true';
            this.src = `https://source.unsplash.com/1600x900/?${encodeURIComponent(recipe.name)},food`;
        } else if (!this.dataset.triedLorem) {
            // Try LoremFlickr as second fallback
            this.dataset.triedLorem = 'true';
            this.src = `https://loremflickr.com/800/600/${encodeURIComponent(recipe.name)},food/all`;
        } else {
            // Final fallback
            this.src = 'https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=1200&q=80';
        }
    };

    // // Set meta information
    document.getElementById('prepTime').textContent = recipe.prep_time || 'N/A';
    document.getElementById('cookTime').textContent = recipe.cook_time || 'N/A';
    document.getElementById('servingsCount').textContent = originalServings;
    document.getElementById('difficulty').textContent = recipe.category || 'Medium';

    // Set description (using area and category)
    const descElement = document.getElementById('recipeDescription');
    if (recipe.area) {
        descElement.textContent = `A ${recipe.category || 'delicious'} dish from ${recipe.area}`;
        descElement.parentElement.style.display = 'block';
    } else {
        descElement.parentElement.style.display = 'none';
    }

    // Set dietary badge
    const badge = document.getElementById('dietaryBadge');
    if (recipe.dietary_type) {
        badge.textContent = recipe.dietary_type;
        badge.className = 'badge'; // Reset classes
        if (recipe.dietary_type.toLowerCase() === 'veg' || recipe.dietary_type.toLowerCase() === 'vegan') {
            badge.classList.add('badge-veg');
        } else {
            badge.classList.add('badge-non-veg');
        }
        badge.style.display = 'inline-block';
    } else {
        badge.style.display = 'none';
    }

    // Set ingredients
    updateIngredientListWithReplacements();

    // Set instructions
    const instructionsListNew = document.querySelector('#recipeDisplay #instructionsList');
    instructionsListNew.innerHTML = '';
    if (recipe.instructions && recipe.instructions.length > 0) {
        recipe.instructions.forEach(instruction => {
            const li = document.createElement('li');
            li.textContent = instruction;
            instructionsListNew.appendChild(li);
        });
    }

    // Set nutrition (if available)
    if (recipe.nutrition) {
        document.getElementById('nutritionSection').style.display = 'block';
        const nutritionInfo = document.getElementById('nutritionInfo');
        nutritionInfo.innerHTML = '';

        // Create nutrition items from the nutrition object
        const nutrition = recipe.nutrition;
        const nutritionItems = [
            { label: 'Calories', value: nutrition.calories + ' kcal' },
            { label: 'Protein', value: nutrition.protein },
            { label: 'Carbs', value: nutrition.carbs },
            { label: 'Fat', value: nutrition.fat },
            { label: 'Saturated Fat', value: nutrition.saturated_fat || '0g' },
            { label: 'Fiber', value: nutrition.fiber },
            { label: 'Sugar', value: nutrition.sugar || '0g' },
            { label: 'Sodium', value: nutrition.sodium || '0mg' }
        ];

        nutritionItems.forEach(item => {
            const div = document.createElement('div');
            div.className = 'nutrition-item';
            div.innerHTML = `
                <span class="nutrition-label">${item.label}</span>
                <span class="nutrition-value">${item.value}</span>
            `;
            nutritionInfo.appendChild(div);
        });
    } else {
        document.getElementById('nutritionSection').style.display = 'none';
    }

    // Set YouTube link
    if (recipe.youtube_url) {
        document.getElementById('youtubeSection').style.display = 'block';
        const youtubeLink = document.getElementById('youtubeLink');
        youtubeLink.href = recipe.youtube_url;
    } else {
        document.getElementById('youtubeSection').style.display = 'none';
    }

}

function updateIngredientListOld() {
    const ingredientsListNew = document.querySelector('#recipeDisplay #ingredientsList');
    ingredientsListNew.innerHTML = '';

    if (currentRecipe.ingredients && currentRecipe.ingredients.length > 0) {
        const currentServings = parseInt(document.getElementById('servingsCount').textContent);
        const ratio = currentServings / originalServings;

        currentRecipe.ingredients.forEach(ing => {
            const li = document.createElement('li');

            // Try to parse and scale the measure
            let scaledMeasure = ing.measure;
            const match = ing.measure.match(/^([\d\.\/\s]+)(.*)$/);

            if (match) {
                const numberPart = match[1].trim();
                const textPart = match[2];

                // Simple fraction parser
                let value = 0;
                if (numberPart.includes('/')) {
                    const [num, den] = numberPart.split('/').map(Number);
                    value = num / den;
                } else if (numberPart.includes(' ')) {
                    const parts = numberPart.split(' ');
                    if (parts.length === 2 && parts[1].includes('/')) {
                        const [num, den] = parts[1].split('/').map(Number);
                        value = Number(parts[0]) + (num / den);
                    } else {
                        value = Number(numberPart);
                    }
                } else {
                    value = Number(numberPart);
                }

                if (!isNaN(value)) {
                    const newValue = value * ratio;
                    // Format nicely (e.g. 1.5 -> 1 1/2) - for now just 1 decimal place if needed
                    scaledMeasure = (Number.isInteger(newValue) ? newValue : newValue.toFixed(1).replace('.0', '')) + textPart;
                }
            }

            li.textContent = `${scaledMeasure} ${ing.name}`;
            ingredientsListNew.appendChild(li);
        });
    }
}

function adjustServings(change) {
    const servingsElement = document.getElementById('servingsCount');
    let currentServings = parseInt(servingsElement.textContent);

    const newServings = currentServings + change;
    if (newServings < 1) return;

    servingsElement.textContent = newServings;
    updateIngredientListWithReplacements();
}

// Close recipe display
function closeRecipeDisplay() {
    document.getElementById('recipeDisplay').style.display = 'none';
    suggestionsSection.style.display = 'block';
}

// Search by ingredients
async function searchByIngredients(ingredients) {
    loading.classList.add('show');
    errorAlert.classList.remove('show');

    try {
        const response = await fetch(`${API_URL}/search-by-ingredients`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ ingredients: ingredients })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to search recipes');
        }

        const data = await response.json();

        if (data.recipes.length === 0) {
            showError('No recipes found with these ingredients. Try different ones!');
            return;
        }

        // Update suggestions grid with results
        document.querySelector('.section-title').textContent = `ðŸ³ Found ${data.count} Recipes`;
        suggestionsGrid.innerHTML = data.recipes.map(recipe => `
            <div class="suggestion-card" onclick="searchRecipe('${recipe.name}')" style="text-align: left; padding: 1.5rem;">
                <div style="display: flex; align-items: center; gap: 1rem; margin-bottom: 1rem;">
                    <div class="suggestion-icon" style="margin: 0;">
                        <img src="${recipe.thumbnail}" alt="${recipe.name}" style="width: 70px; height: 70px; border-radius: 50%; object-fit: cover; border: 3px solid var(--primary);" onerror="this.onerror=null;this.src='https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=1200&q=80';">
                    </div>
                    <div>
                        <div class="suggestion-name" style="font-size: 1.1rem; margin-bottom: 0.25rem;">${recipe.name}</div>
                        ${recipe.category ? `<div style="font-size: 0.85rem; color: var(--primary); font-weight: 600;">${recipe.category}</div>` : ''}
                    </div>
                </div>
                
                ${recipe.ingredients && recipe.ingredients.length > 0 ? `
                    <div style="font-size: 0.85rem; color: var(--gray-700); margin-bottom: 0.75rem; background: var(--gray-50); padding: 0.5rem; border-radius: 0.5rem;">
                        <strong style="color: var(--gray-900);">Includes:</strong> ${recipe.ingredients.join(', ')}
                    </div>
                ` : ''}
                
                ${recipe.instructions ? `
                    <div style="font-size: 0.8rem; color: var(--gray-600); line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;">
                        ${recipe.instructions}
                    </div>
                ` : ''}
            </div>
        `).join('');

        // Ensure suggestions are visible
        suggestionsSection.style.display = 'block';
        document.getElementById('recipeDisplay').style.display = 'none';

        // Scroll to results
        suggestionsSection.scrollIntoView({ behavior: 'smooth' });

    } catch (error) {
        showError(error.message);
    } finally {
        loading.classList.remove('show');
    }
}

// Search recipe
async function searchRecipe(dishName) {
    const query = dishName || dishInput.value.trim();

    if (!query) {
        showError(currentMode === 'recipe' ? 'Please enter a dish name' : 'Please enter ingredients');
        return;
    }

    // If in parse mode and searching from input (not clicking a suggestion), use ingredient search
    if (currentMode === 'parse' && !dishName) {
        await generateRecipeFromIngredients(query, currentFilter);
        return;
    }

    // Otherwise (recipe mode OR clicking a suggestion), fetch the full recipe
    loading.classList.add('show');
    hideRecipe();
    errorAlert.classList.remove('show');

    try {
        const response = await fetch(`${API_URL}/generate-recipe`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ dish_name: query })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to generate recipe');
        }

        const recipe = await response.json();
        displayRecipe(recipe);
        if (!dishName) dishInput.value = ''; // Clear input only if manual search
    } catch (error) {
        showError(error.message);
        suggestionsSection.style.display = 'block';
    } finally {
        loading.classList.remove('show');
    }
}

// Event listeners
searchBtn.addEventListener('click', () => searchRecipe());
dishInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') searchRecipe();
});

// Initialize
loadSuggestions();

// Navigation Functions
function showMainView() {
    const mainView = document.getElementById('mainView');
    const normalizerView = document.getElementById('unitNormalizerView');
    const recipeDisplay = document.getElementById('recipeDisplay');
    const navLinks = document.querySelectorAll('.nav-link');

    // Show main view
    mainView.style.display = 'block';
    normalizerView.style.display = 'none';
    recipeDisplay.style.display = 'none';

    // Update active nav link
    navLinks[0].classList.add('active');
    navLinks[1].classList.remove('active');

    // Scroll to top
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function showUnitNormalizer() {
    const mainView = document.getElementById('mainView');
    const normalizerView = document.getElementById('unitNormalizerView');
    const recipeDisplay = document.getElementById('recipeDisplay');
    const navLinks = document.querySelectorAll('.nav-link');

    // Show unit normalizer view
    mainView.style.display = 'none';
    normalizerView.style.display = 'block';
    recipeDisplay.style.display = 'none';

    // Update active nav link
    navLinks[0].classList.remove('active');
    navLinks[1].classList.add('active');

    // Scroll to top
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

// Legacy function for compatibility
function switchView(viewName) {
    if (viewName === 'main') {
        showMainView();
    } else if (viewName === 'normalizer') {
        showUnitNormalizer();
    }
}

// Unit Normalizer
function convertUnits() {
    const value = parseFloat(document.getElementById('convertValue').value);
    const fromUnit = document.getElementById('convertFrom').value;
    const toUnit = document.getElementById('convertTo').value;
    const resultElement = document.getElementById('convertResult');

    if (isNaN(value) || value < 0) {
        resultElement.textContent = 'Invalid Input';
        resultElement.style.background = 'linear-gradient(135deg, #ef4444, #dc2626)';
        return;
    }

    // Comprehensive conversion factors for recipe units
    // Volume units converted to ml, Weight units converted to grams
    const volumeUnits = {
        ml: 1,
        l: 1000,
        cup: 240,
        tbsp: 15,
        tsp: 5,
        'fl-oz': 29.5735,
        pint: 473.176,
        quart: 946.353,
        gallon: 3785.41
    };

    const weightUnits = {
        g: 1,
        kg: 1000,
        oz: 28.3495,
        lb: 453.592
    };

    // Determine if conversion is valid (can't convert volume to weight or vice versa)
    const fromIsVolume = fromUnit in volumeUnits;
    const toIsVolume = toUnit in volumeUnits;
    const fromIsWeight = fromUnit in weightUnits;
    const toIsWeight = toUnit in weightUnits;

    if ((fromIsVolume && toIsWeight) || (fromIsWeight && toIsVolume)) {
        resultElement.textContent = 'âš ï¸ Cannot convert';
        resultElement.style.background = 'linear-gradient(135deg, #f59e0b, #d97706)';
        return;
    }

    let result;
    if (fromIsVolume && toIsVolume) {
        // Volume to volume conversion
        const baseValue = value * volumeUnits[fromUnit];
        result = baseValue / volumeUnits[toUnit];
    } else if (fromIsWeight && toIsWeight) {
        // Weight to weight conversion
        const baseValue = value * weightUnits[fromUnit];
        result = baseValue / weightUnits[toUnit];
    } else {
        resultElement.textContent = 'Error';
        return;
    }

    // Format result with appropriate precision
    let formattedResult;
    if (result >= 1000) {
        formattedResult = result.toFixed(0);
    } else if (result >= 10) {
        formattedResult = result.toFixed(1);
    } else if (result >= 1) {
        formattedResult = result.toFixed(2);
    } else {
        formattedResult = result.toFixed(3);
    }

    // Get unit display names
    const unitNames = {
        ml: 'ml', l: 'L', cup: 'cups', tbsp: 'tbsp', tsp: 'tsp',
        'fl-oz': 'fl oz', pint: 'pints', quart: 'quarts', gallon: 'gallons',
        g: 'g', kg: 'kg', oz: 'oz', lb: 'lbs'
    };

    resultElement.textContent = `${formattedResult} ${unitNames[toUnit]}`;
    resultElement.style.background = 'linear-gradient(135deg, var(--primary-light), var(--primary))';
}
// New function to generate recipe from ingredients with filter
async function generateRecipeFromIngredients(ingredientsText, filter) {
    loading.classList.add('show');
    hideRecipe();
    errorAlert.classList.remove('show');

    try {
        const response = await fetch(`${API_URL}/generate-recipe-from-ingredients`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                ingredients: ingredientsText,
                filter_type: filter
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to generate recipe');
        }

        const recipe = await response.json();
        displayRecipe(recipe);
        dishInput.value = ''; // Clear input
    } catch (error) {
        showError(error.message);
        suggestionsSection.style.display = 'block';
    } finally {
        loading.classList.remove('show');
    }
}
// Ingredient Replacement Feature
async function showIngredientAlternatives(ingredientName) {
    // Show loading state
    const overlay = document.createElement('div');
    overlay.className = 'alternatives-overlay show';
    document.body.appendChild(overlay);

    const popup = document.createElement('div');
    popup.className = 'alternatives-popup show';
    popup.innerHTML = `
        <div class="popup-header">
            <h3 class="popup-title">Finding alternatives...</h3>
            <button class="popup-close" onclick="closeAlternativesPopup()">âœ•</button>
        </div>
        <div class="loading" style="display: flex; margin: 2rem 0;">
            <div class="spinner"></div>
        </div>
    `;
    document.body.appendChild(popup);

    try {
        const response = await fetch(`${API_URL}/suggest-ingredient-replacement`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                ingredient: ingredientName,
                recipe_name: currentRecipe.name
            })
        });

        if (!response.ok) {
            throw new Error('Failed to get alternatives');
        }

        const data = await response.json();

        // Update popup with results
        popup.innerHTML = `
            <div class="popup-header">
                <h3 class="popup-title">Alternatives for "${data.original}"</h3>
                <button class="popup-close" onclick="closeAlternativesPopup()">âœ•</button>
            </div>
            <p style="color: var(--gray-600); margin-bottom: 1.5rem; font-size: 0.9rem;">${data.notes}</p>
            <ul class="alternatives-list">
                ${data.alternatives.map(alt => `
                    <li class="alternative-item">
                        <span style="font-weight: 600;">âœ“ ${alt}</span>
                    </li>
                `).join('')}
            </ul>
        `;
    } catch (error) {
        popup.innerHTML = `
            <div class="popup-header">
                <h3 class="popup-title">Error</h3>
                <button class="popup-close" onclick="closeAlternativesPopup()">âœ•</button>
            </div>
            <p style="color: var(--gray-600);">Could not fetch alternatives. Please try again.</p>
        `;
    }
}

function closeAlternativesPopup() {
    const overlay = document.querySelector('.alternatives-overlay');
    const popup = document.querySelector('.alternatives-popup');

    if (overlay) overlay.remove();
    if (popup) popup.remove();
}

// Update the ingredient list display to include replacement buttons
function updateIngredientListWithReplacements() {
    const ingredientsListNew = document.querySelector('#recipeDisplay #ingredientsList');
    ingredientsListNew.innerHTML = '';

    if (currentRecipe.ingredients && currentRecipe.ingredients.length > 0) {
        const currentServings = parseInt(document.getElementById('servingsCount').textContent);
        const ratio = currentServings / originalServings;

        currentRecipe.ingredients.forEach(ing => {
            const li = document.createElement('li');

            // Try to parse and scale the measure
            let scaledMeasure = ing.measure;
            const match = ing.measure.match(/^([\d\.\/\s]+)(.*)$/);

            if (match) {
                const numberPart = match[1].trim();
                const textPart = match[2];

                // Simple fraction parser
                let value = 0;
                if (numberPart.includes('/')) {
                    const [num, den] = numberPart.split('/').map(Number);
                    value = num / den;
                } else if (numberPart.includes(' ')) {
                    const parts = numberPart.split(' ');
                    if (parts.length === 2 && parts[1].includes('/')) {
                        const [num, den] = parts[1].split('/').map(Number);
                        value = Number(parts[0]) + (num / den);
                    } else {
                        value = Number(numberPart);
                    }
                } else {
                    value = Number(numberPart);
                }

                if (!isNaN(value)) {
                    const newValue = value * ratio;
                    scaledMeasure = (Number.isInteger(newValue) ? newValue : newValue.toFixed(1).replace('.0', '')) + textPart;
                }
            }

            li.innerHTML = `
                <span>${scaledMeasure} ${ing.name}</span>
                <button class="ingredient-replace-btn" onclick="showIngredientAlternatives('${ing.name.replace(/'/g, "\\'")}')">
                    Replace
                </button>
            `;
            ingredientsListNew.appendChild(li);
        });
    }
}
