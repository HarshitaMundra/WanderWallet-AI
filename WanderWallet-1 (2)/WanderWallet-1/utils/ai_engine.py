import os
import json
import logging
import time
from google import genai
from google.genai import types

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

try:
    if GEMINI_API_KEY:
        client = genai.Client(api_key=GEMINI_API_KEY)
        AI_AVAILABLE = True
        logger.info("Gemini AI client initialized successfully")
    else:
        logger.warning("GEMINI_API_KEY not found in environment")
        client = None
        AI_AVAILABLE = False
except Exception as e:
    logger.warning(f"Gemini AI not available: {e}")
    client = None
    AI_AVAILABLE = False


def retry_with_backoff(func, max_retries=3, initial_delay=2):
    """
    Retry a function with exponential backoff.
    """
    for attempt in range(max_retries):
        try:
            result = func()
            return result
        except Exception as e:
            error_msg = str(e)
            
            if "503" in error_msg or "UNAVAILABLE" in error_msg:
                if attempt < max_retries - 1:
                    delay = initial_delay * (2 ** attempt)
                    logger.info(f"Model overloaded, retrying in {delay}s (attempt {attempt + 1}/{max_retries})...")
                    time.sleep(delay)
                    continue
            
            if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                if attempt < max_retries - 1:
                    delay = initial_delay * (3 ** attempt)
                    logger.info(f"Rate limit hit, waiting {delay}s before retry (attempt {attempt + 1}/{max_retries})...")
                    time.sleep(delay)
                    continue
            
            raise
    
    raise Exception(f"All {max_retries} retry attempts failed")


def select_best_destination_images(destination, image_candidates):
    """
    Use AI to intelligently select the best images for a destination.
    
    Args:
        destination (str): The destination name
        image_candidates (list): List of image objects with descriptions/tags from Unsplash
    
    Returns:
        list: Indices of the best images, ranked by relevance
    """
    if not AI_AVAILABLE or not client or not image_candidates:
        return list(range(len(image_candidates)))
    
    image_descriptions = []
    for idx, img in enumerate(image_candidates):
        desc_parts = []
        if img.get('description'):
            desc_parts.append(f"Description: {img['description']}")
        if img.get('alt_description'):
            desc_parts.append(f"Alt: {img['alt_description']}")
        if img.get('tags'):
            tags = ', '.join([tag.get('title', '') for tag in img['tags'][:5]])
            desc_parts.append(f"Tags: {tags}")
        
        image_descriptions.append({
            'index': idx,
            'info': ' | '.join(desc_parts) if desc_parts else 'No description'
        })
    
    try:
        prompt = f"""You are an expert in selecting the most representative and beautiful images for travel destinations.

Destination: {destination}

I have {len(image_candidates)} images to choose from. Analyze which images would best represent this destination for travelers looking for tourist information, attractions, and landmarks.

Images to evaluate:
{json.dumps(image_descriptions, indent=2)}

Consider:
1. Relevance to the destination's famous landmarks and attractions
2. Visual appeal and quality indicators from descriptions
3. Representation of the destination's character (heritage, nature, urban, etc.)
4. Avoiding generic or people-focused images

Return ONLY valid JSON with the indices ranked from best to worst:
{{
  "ranked_indices": [index1, index2, index3, ...]
}}"""

        models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash-exp"]
        
        for model_name in models_to_try:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.3
                    )
                )
                
                if response.text:
                    result = json.loads(response.text)
                    ranked = result.get('ranked_indices', [])
                    if ranked:
                        logger.info(f"AI ranked {len(ranked)} images for {destination} using {model_name}")
                        return ranked
                        
            except Exception as e:
                logger.warning(f"Image ranking with {model_name} failed: {e}")
                continue
        
        logger.warning("AI image ranking failed, using original order")
        return list(range(len(image_candidates)))
        
    except Exception as e:
        logger.error(f"AI image selection failed: {e}")
        return list(range(len(image_candidates)))


def predict_trip_budget(data):
    """
    Predict trip budget and provide cost breakdown with monthly savings plan.
    
    Args:
        data (dict): Contains 'from', 'to', 'days', 'people', 'budget_goal'
    
    Returns:
        dict: Estimated cost, breakdown, monthly savings, and suggestions
    """
    from_city = data.get('from', 'Unknown')
    to_city = data.get('to', 'Unknown')
    days = data.get('days', 3)
    people = data.get('people', 2)
    budget_goal = data.get('budget_goal', 10000)
    
    if AI_AVAILABLE and client:
        try:
            prompt = f"""You are a travel budget expert for Indian destinations. 
Predict the trip cost for the following trip:
- From: {from_city}
- To: {to_city}
- Duration: {days} days
- Number of people: {people}
- Budget goal: ₹{budget_goal}

Provide a detailed budget breakdown including:
1. Transportation (flights/trains/buses)
2. Accommodation per night
3. Food per day
4. Sightseeing and activities
5. Miscellaneous expenses

Also calculate:
- Total estimated cost
- Monthly savings needed (divide by 3 months)
- 3 practical suggestions to stay within budget

Return ONLY valid JSON in this exact format:
{{
  "estimated_cost": number,
  "breakdown": {{
    "transportation": number,
    "accommodation": number,
    "food": number,
    "sightseeing": number,
    "miscellaneous": number
  }},
  "monthly_saving": number,
  "suggestions": ["suggestion1", "suggestion2", "suggestion3"]
}}"""

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.7
                )
            )
            
            if response.text:
                try:
                    result = json.loads(response.text)
                    logger.info("AI trip budget prediction successful")
                    return result
                except (json.JSONDecodeError, ValueError, KeyError) as parse_err:
                    logger.error(f"Failed to parse AI response: {parse_err}, using fallback")
            else:
                logger.warning("Empty response from AI, using fallback")
                
        except Exception as e:
            logger.error(f"AI prediction failed: {e}, using fallback")
    
    base_cost_per_day = 2000 * people
    transport_cost = 1500 * people
    estimated_cost = (base_cost_per_day * days) + transport_cost
    
    return {
        "estimated_cost": estimated_cost,
        "breakdown": {
            "transportation": transport_cost,
            "accommodation": days * 1200 * people,
            "food": days * 600 * people,
            "sightseeing": days * 400 * people,
            "miscellaneous": days * 300 * people
        },
        "monthly_saving": round(estimated_cost / 3, 2),
        "suggestions": [
            f"Book accommodation 2 months in advance to save 20-30%",
            f"Travel during off-season to {to_city} for better rates",
            f"Use public transport instead of taxis to save ₹{days * 200} per day"
        ]
    }


def generate_budget_advice(data):
    """
    Generate AI-powered budget advice based on income, expenses, and savings goal.
    
    Args:
        data (dict): Contains 'income', 'expenses', 'savings_goal'
    
    Returns:
        str: AI-generated budget advice
    """
    income = data.get('income', 0)
    expenses = data.get('expenses', 0)
    savings_goal = data.get('savings_goal', 0)
    
    current_savings = income - expenses
    shortfall = savings_goal - current_savings
    
    if AI_AVAILABLE and client:
        try:
            prompt = f"""You are a personal finance advisor in India. 
Provide practical budget advice for this situation:
- Monthly Income: ₹{income}
- Current Expenses: ₹{expenses}
- Current Savings: ₹{current_savings}
- Savings Goal: ₹{savings_goal}
- Shortfall: ₹{shortfall}

Give 2-3 specific, actionable recommendations to help reach the savings goal.
Keep it concise (3-4 sentences max) and practical for Indian context.
Mention specific categories to reduce if needed (entertainment, dining out, subscriptions, etc.)."""

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.8
                )
            )
            
            if response.text:
                logger.info("AI budget advice generated successfully")
                return response.text.strip()
            else:
                logger.warning("Empty response from AI, using fallback")
                
        except Exception as e:
            logger.error(f"AI advice generation failed: {e}, using fallback")
    
    if shortfall <= 0:
        return f"Great job! You're already saving ₹{current_savings} per month, which exceeds your goal of ₹{savings_goal}. Consider investing the extra savings for long-term growth."
    
    savings_rate = (current_savings / income * 100) if income > 0 else 0
    months_to_goal = round(shortfall / 1000) if shortfall > 0 else 1
    
    advice = f"To reach your savings goal of ₹{savings_goal}, you need to save an additional ₹{shortfall} per month. "
    
    if savings_rate < 20:
        advice += f"Your current savings rate is {savings_rate:.1f}%, which is below the recommended 20%. "
        advice += f"Try reducing discretionary expenses like dining out, entertainment, or subscriptions by ₹{min(shortfall, expenses * 0.2):.0f} per month. "
    else:
        advice += f"You're doing well with a {savings_rate:.1f}% savings rate. "
    
    advice += f"Small changes like cooking at home more often or using public transport could help you reach your goal in {months_to_goal} months."
    
    return advice


def generate_personalized_budget_insights(income, needs, wants, savings):
    """
    Generate AI-powered personalized budget insights and suggestions.
    
    Args:
        income (float): Monthly income
        needs (float): Monthly necessary expenses
        wants (float): Monthly discretionary expenses  
        savings (float): Monthly savings amount
    
    Returns:
        dict: Contains 'summary' and 'tips' list with AI-generated suggestions
    """
    total_expenses = needs + wants
    savings_rate = (savings / income * 100) if income > 0 else 0
    
    if not AI_AVAILABLE or not client or income <= 0:
        return None
    
    try:
        prompt = f"""You are an expert personal finance coach in India.

Budget data:
- Income: ₹{income:,.0f}
- Needs: ₹{needs:,.0f} ({(needs/income*100):.1f}%)
- Wants: ₹{wants:,.0f} ({(wants/income*100):.1f}%)
- Savings: ₹{savings:,.0f} ({savings_rate:.1f}%)

Based on 50/30/20 rule, provide:
1. ONE short summary sentence (max 10 words)
2. 3-4 brief tips (each max 12 words). Include ₹ amounts where relevant.

Keep tips VERY concise and actionable.

JSON format:
{{
  "summary": "Short encouraging sentence",
  "tips": [
    "Brief tip with ₹ amount",
    "Another brief tip",
    "Third brief tip"
  ]
}}"""

        def generate_ai_insights():
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.4
                )
            )
            
            if not response.text:
                raise ValueError("Empty response from AI")
            
            result = json.loads(response.text)
            
            if not isinstance(result.get('summary'), str) or not isinstance(result.get('tips'), list):
                raise ValueError("Invalid response format")
            
            if len(result.get('tips', [])) == 0:
                raise ValueError("No tips provided")
            
            return {
                'summary': result['summary'],
                'tips': [tip for tip in result['tips'] if tip and isinstance(tip, str)][:5]
            }
        
        insights = retry_with_backoff(generate_ai_insights, max_retries=2, initial_delay=1)
        logger.info("AI budget insights generated successfully")
        return insights
        
    except Exception as e:
        logger.error(f"AI budget insights generation failed: {e}")
        return None


def create_travel_plan(data):
    """
    Create a detailed AI-powered travel itinerary with day-by-day activities.
    
    Args:
        data (dict): Contains 'from', 'to', 'days'
    
    Returns:
        dict: Itinerary with daily activities, summary, and budget tips
    """
    from_city = data.get('from', 'Unknown')
    to_city = data.get('to', 'Unknown')
    days = data.get('days', 3)
    
    if AI_AVAILABLE and client:
        try:
            prompt = f"""You are a travel expert specializing in Indian destinations.
Create a detailed {days}-day itinerary for a trip:
- From: {from_city}
- To: {to_city}
- Duration: {days} days

For each day, suggest 3-4 activities including:
- Morning, afternoon, and evening activities
- Popular tourist spots
- Local experiences and food recommendations
- Estimated time for each activity

Also provide:
- A brief summary of why {to_city} is worth visiting
- One budget-saving tip specific to this destination

Return ONLY valid JSON in this exact format:
{{
  "itinerary": [
    {{
      "day": 1,
      "activities": [
        "Morning: Visit famous landmark",
        "Afternoon: Explore local market",
        "Evening: Sunset at viewpoint"
      ]
    }}
  ],
  "summary": "Brief description of destination highlights",
  "budget_tip": "Specific money-saving tip for this destination"
}}"""

            response = client.models.generate_content(
                model="gemini-2.0-flash-exp",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.8
                )
            )
            
            if response.text:
                try:
                    result = json.loads(response.text)
                    logger.info("AI travel plan created successfully")
                    return result
                except (json.JSONDecodeError, ValueError, KeyError) as parse_err:
                    logger.error(f"Failed to parse AI response: {parse_err}, using fallback")
            else:
                logger.warning("Empty response from AI, using fallback")
                
        except Exception as e:
            logger.error(f"AI travel plan failed: {e}, using fallback")
    
    itinerary = []
    activities_templates = [
        ["Morning: Check-in and freshen up", "Afternoon: Visit main city attraction", "Evening: Explore local markets and try street food"],
        ["Morning: Heritage site tour", "Afternoon: Museum visit and lunch at famous restaurant", "Evening: Sunset viewpoint and photography"],
        ["Morning: Adventure activity or nature walk", "Afternoon: Shopping for local handicrafts", "Evening: Cultural show and departure preparation"]
    ]
    
    for day_num in range(1, min(days + 1, 4)):
        itinerary.append({
            "day": day_num,
            "activities": activities_templates[day_num - 1] if day_num <= 3 else activities_templates[2]
        })
    
    if days > 3:
        for day_num in range(4, days + 1):
            itinerary.append({
                "day": day_num,
                "activities": [
                    "Morning: Leisure time and local exploration",
                    "Afternoon: Visit nearby attractions",
                    "Evening: Relaxation and local cuisine"
                ]
            })
    
    return {
        "itinerary": itinerary,
        "summary": f"{to_city} offers a perfect blend of culture, history, and natural beauty. Experience local traditions, visit historic landmarks, and enjoy authentic cuisine during your {days}-day journey.",
        "budget_tip": f"Book train tickets 60 days in advance for best prices, and eat at local eateries instead of tourist restaurants to save 40-50% on food costs."
    }


def get_city_accommodations(destination):
    """
    Get AI-powered accommodation recommendations for a specific city.
    
    Args:
        destination (str): City name
    
    Returns:
        list: Accommodation options with name, price, rating, and type
    """
    if AI_AVAILABLE and client:
        prompt = f"""You are a travel expert for India. Provide 5 real hotel/accommodation recommendations for {destination}.

Include a mix of:
- 1-2 budget options (₹500-1000/night)
- 2 mid-range options (₹1200-2500/night)
- 1-2 luxury/heritage options (₹2500+/night)

Return ONLY valid JSON in this exact format:
{{
  "accommodations": [
    {{
      "name": "Actual hotel name",
      "price": price_per_night_in_rupees,
      "rating": rating_out_of_5,
      "type": "Budget/Mid-Range/Luxury/Heritage/Business"
    }}
  ]
}}"""

        def make_api_call():
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.7
                )
            )
            
            if response.text:
                result = json.loads(response.text)
                logger.info(f"AI accommodations for {destination} generated successfully")
                return result.get('accommodations', [])
            else:
                raise Exception("Empty response from API")
        
        try:
            return retry_with_backoff(make_api_call, max_retries=3, initial_delay=3)
        except Exception as e:
            logger.error(f"All retries failed for accommodations: {e}, using fallback")
    
    return [
        {'name': f'{destination} Budget Inn', 'price': 800, 'rating': 3.5, 'type': 'Budget'},
        {'name': f'{destination} Comfort Hotel', 'price': 1500, 'rating': 4.0, 'type': 'Mid-Range'},
        {'name': f'{destination} Luxury Resort', 'price': 3500, 'rating': 4.8, 'type': 'Luxury'},
        {'name': f'{destination} Heritage Palace', 'price': 2200, 'rating': 4.5, 'type': 'Heritage'},
        {'name': f'{destination} Business Hotel', 'price': 1800, 'rating': 4.2, 'type': 'Business'}
    ]


def get_city_tourist_spots(destination):
    """
    Get AI-powered tourist attraction recommendations for a specific city.
    
    Args:
        destination (str): City name
    
    Returns:
        list: Tourist spots with name, description, and entry fee
    """
    if AI_AVAILABLE and client:
        prompt = f"""You are a travel expert for India. List 5-7 real tourist attractions and places to visit in {destination}.

Include popular landmarks, temples, forts, museums, gardens, markets, etc.

Return ONLY valid JSON in this exact format:
{{
  "tourist_spots": [
    {{
      "name": "Actual place name",
      "description": "Brief description (1-2 sentences)",
      "entry_fee": fee_in_rupees_or_0_if_free
    }}
  ]
}}"""

        def make_api_call():
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.7
                )
            )
            
            if response.text:
                result = json.loads(response.text)
                logger.info(f"AI tourist spots for {destination} generated successfully")
                return result.get('tourist_spots', [])
            else:
                raise Exception("Empty response from API")
        
        try:
            return retry_with_backoff(make_api_call, max_retries=3, initial_delay=3)
        except Exception as e:
            logger.error(f"All retries failed for tourist spots: {e}, using fallback")
    
    return [
        {'name': f'{destination} Fort', 'description': 'Historic fort with panoramic views of the city', 'entry_fee': 50},
        {'name': f'{destination} Museum', 'description': 'Rich collection of local art and artifacts', 'entry_fee': 100},
        {'name': f'{destination} Lake/Garden', 'description': 'Scenic spot with natural beauty and relaxation', 'entry_fee': 30},
        {'name': f'{destination} Temple', 'description': 'Ancient temple with intricate architecture', 'entry_fee': 0},
        {'name': f'Local Market', 'description': 'Traditional market with local handicrafts and food', 'entry_fee': 0}
    ]


def get_ai_travel_options(start_city, destination, days, month):
    """
    Get AI-powered real travel options for train, bus, and car routes.
    
    Args:
        start_city (str): Starting city
        destination (str): Destination city
        days (int): Number of travel days
        month (str): Month of travel
    
    Returns:
        dict: Travel options with train, bus, car details and budget breakdown
    """
    if AI_AVAILABLE and client:
        prompt = f"""You are a travel expert for India with real-time knowledge of transportation options.
Provide realistic travel options from {start_city} to {destination} for a {days}-day trip in {month}.

Research and provide ACTUAL transportation options including:

1. **Train Options** (provide 2-3 real trains on this route):
   - Real train names and numbers if available
   - Realistic ticket prices based on distance and class
   - Actual travel duration
   - Class of travel (3A, 2A, Sleeper, etc.)

2. **Bus Options** (provide 2-3 real bus services):
   - Real bus operators (RedBus, VRL, etc.)
   - Realistic ticket prices
   - Actual travel duration
   - Bus type (AC Sleeper, Volvo, etc.)

3. **Car/Road Trip** (driving route):
   - Approximate distance in kilometers
   - Estimated fuel cost (assume 15 km/liter, ₹100/liter)
   - Travel duration by car
   - Estimated toll charges

4. **Trip Breakdown** (for {days} days):
   - Hotel cost (per night realistic for destination)
   - Food cost per day
   - Sightseeing/activities cost per day

Calculate total budget and monthly savings (divide by 3 months).

Return ONLY valid JSON in this exact format:
{{
  "train_options": [
    {{
      "name": "Train name/number",
      "price": price_in_rupees,
      "duration": "Xh Ym",
      "class": "class_type"
    }}
  ],
  "bus_options": [
    {{
      "name": "Bus type",
      "price": price_in_rupees,
      "duration": "Xh Ym",
      "operator": "operator_name"
    }}
  ],
  "car_route": {{
    "distance": "X km",
    "fuel_cost": cost_in_rupees,
    "duration": "Xh Ym",
    "toll": toll_in_rupees
  }},
  "total_budget": total_amount,
  "monthly_savings": monthly_amount,
  "breakdown": {{
    "travel": cheapest_travel_cost,
    "hotel": total_hotel_cost,
    "food": total_food_cost,
    "sightseeing": total_sightseeing_cost
  }}
}}"""

        def make_api_call():
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.7
                )
            )
            
            if response.text:
                result = json.loads(response.text)
                logger.info(f"AI travel options from {start_city} to {destination} generated successfully")
                return result
            else:
                raise Exception("Empty response from API")
        
        try:
            return retry_with_backoff(make_api_call, max_retries=3, initial_delay=3)
        except Exception as e:
            logger.error(f"All retries failed for travel options: {e}, using fallback")
    
    train_cost = 1500 + (days * 200)
    bus_cost = 1000 + (days * 150)
    car_cost = 2500 + (days * 400)
    
    hotel_cost = days * 1500
    food_cost = days * 800
    sightseeing_cost = days * 600
    
    total_budget = min(train_cost, bus_cost, car_cost) + hotel_cost + food_cost + sightseeing_cost
    monthly_savings = total_budget / 3
    
    return {
        'train_options': [
            {'name': 'Rajdhani Express', 'price': train_cost, 'duration': '8h 30m', 'class': '3A'},
            {'name': 'Shatabdi Express', 'price': train_cost + 500, 'duration': '7h 45m', 'class': '2A'}
        ],
        'bus_options': [
            {'name': 'AC Sleeper', 'price': bus_cost, 'duration': '10h 15m', 'operator': 'RedBus Premium'},
            {'name': 'Volvo Multi-Axle', 'price': bus_cost + 300, 'duration': '9h 30m', 'operator': 'VRL Travels'}
        ],
        'car_route': {
            'distance': '450 km',
            'fuel_cost': car_cost,
            'duration': '7h 30m',
            'toll': 400
        },
        'total_budget': total_budget,
        'monthly_savings': monthly_savings,
        'breakdown': {
            'travel': min(train_cost, bus_cost, car_cost),
            'hotel': hotel_cost,
            'food': food_cost,
            'sightseeing': sightseeing_cost
        }
    }
