"""
get_data.py - Data fetching and processing functions for SkyCast Weather Forecaster
Uses NASA POWER API and Open-Meteo for weather data
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
import random
from fpdf import FPDF

# ==============================
# NASA POWER API Functions
# ==============================

def get_historical_data_for_event(latitude, longitude, event_start, event_end):
    """
    Fetch historical weather data for the event dates from NASA POWER API.
    Gets 20 years of historical data for the same time period.
    """
    try:
        # Calculate the date range for historical data (last 20 years)
        end_year = datetime.now().year - 1
        start_year = end_year - 19
        
        # Format dates for NASA POWER API
        start_date = f"{start_year}{event_start.strftime('%m%d')}"
        end_date = f"{end_year}{event_end.strftime('%m%d')}"
        
        # NASA POWER API endpoint
        url = "https://power.larc.nasa.gov/api/temporal/daily/point"
        
        params = {
            "parameters": "T2M_MAX,PRECTOTCORR",
            "community": "RE",
            "longitude": longitude,
            "latitude": latitude,
            "start": start_date,
            "end": end_date,
            "format": "JSON"
        }
        
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        if "properties" not in data or "parameter" not in data["properties"]:
            return pd.DataFrame()
        
        # Extract temperature and precipitation data
        temp_data = data["properties"]["parameter"].get("T2M_MAX", {})
        precip_data = data["properties"]["parameter"].get("PRECTOTCORR", {})
        
        # Create DataFrame
        dates = []
        temps = []
        precips = []
        
        for date_str, temp in temp_data.items():
            if temp != -999:  # -999 is missing data indicator
                dates.append(date_str)
                temps.append(temp)
                precip = precip_data.get(date_str, 0)
                precips.append(precip if precip != -999 else 0)
        
        df = pd.DataFrame({
            "date": dates,
            "temperature_2m_max": temps,
            "precipitation_sum": precips
        })
        
        return df
        
    except Exception as e:
        print(f"Error fetching historical data: {e}")
        return pd.DataFrame()


def get_immediate_forecast(latitude, longitude):
    """
    Fetch 16-day weather forecast from Open-Meteo API.
    """
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
            "timezone": "auto",
            "forecast_days": 16
        }
        
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        
        if "daily" not in data:
            return pd.DataFrame()
        
        # Create DataFrame
        df = pd.DataFrame({
            "Date": data["daily"]["time"],
            "Max Temp (°C)": data["daily"]["temperature_2m_max"],
            "Min Temp (°C)": data["daily"]["temperature_2m_min"],
            "Precipitation (mm)": data["daily"]["precipitation_sum"]
        })
        
        return df
        
    except Exception as e:
        print(f"Error fetching immediate forecast: {e}")
        return pd.DataFrame()


def simulate_future_forecast(hist_df, event_start, event_end):
    """
    Simulate a future forecast based on historical data patterns.
    Uses random sampling from historical data with some variation.
    """
    try:
        if hist_df.empty:
            return pd.DataFrame()
        
        # Calculate number of days in event
        num_days = (event_end - event_start).days + 1
        
        # Generate dates
        dates = [event_start + timedelta(days=i) for i in range(num_days)]
        
        # Sample from historical data with variation
        simulated_temps = []
        simulated_precip = []
        
        for _ in range(num_days):
            # Random sample from historical data
            sample = hist_df.sample(n=1)
            
            # Add some random variation (±3°C for temp, ±2mm for precip)
            temp = sample["temperature_2m_max"].values[0] + random.uniform(-3, 3)
            precip = max(0, sample["precipitation_sum"].values[0] + random.uniform(-2, 2))
            
            simulated_temps.append(round(temp, 2))
            simulated_precip.append(round(precip, 2))
        
        # Create DataFrame
        df = pd.DataFrame({
            "Date": dates,
            "Simulated Max Temp (°C)": simulated_temps,
            "Simulated Rainfall (mm)": simulated_precip
        })
        
        return df
        
    except Exception as e:
        print(f"Error simulating forecast: {e}")
        return pd.DataFrame()


def find_best_dates(latitude, longitude, search_start, search_end, hot_thresh, rain_thresh, event_duration):
    """
    Find the best dates within a search window that have lower weather risk.
    """
    try:
        # Limit search window to prevent hanging
        max_search_days = 90  # Don't search more than 90 days
        search_days = (search_end - search_start).days
        if search_days > max_search_days:
            search_end = search_start + timedelta(days=max_search_days)
        
        # Fetch historical data for the search window
        hist_df = get_historical_data_for_event(latitude, longitude, search_start, search_end)
        
        if hist_df.empty:
            return None, None
        
        best_score = float('inf')
        best_start = None
        max_iterations = 50  # Limit iterations to prevent hanging
        iterations = 0
        
        # Try different starting dates
        for start_offset in range(0, min((search_end - search_start).days - event_duration + 1, max_iterations)):
            iterations += 1
            candidate_start = search_start + timedelta(days=start_offset)
            candidate_end = candidate_start + timedelta(days=event_duration - 1)
            
            # Get data for this candidate period
            candidate_df = get_historical_data_for_event(latitude, longitude, candidate_start, candidate_end)
            
            if candidate_df.empty:
                continue
            
            # Calculate risk score
            hot_days = (candidate_df["temperature_2m_max"] > hot_thresh).sum()
            rainy_days = (candidate_df["precipitation_sum"] > rain_thresh).sum()
            
            score = hot_days + rainy_days
            
            if score < best_score:
                best_score = score
                best_start = candidate_start
        
        if best_start:
            best_end = best_start + timedelta(days=event_duration - 1)
            return best_start, best_end
        
        return None, None
        
    except Exception as e:
        print(f"Error finding best dates: {e}")
        return None, None


# ==============================
# PDF Report Generation
# ==============================

def clean_text_for_pdf(text):
    """
    Clean text for PDF generation by removing emojis and replacing special characters.
    """
    # Remove common emojis
    emoji_map = {
        '❄️': '', '🔥': '', '🌧️': '', '✅': '', '⚠️': '', 
        '💡': '', '🌍': '', '📍': '', '🛰️': '', '📡': '',
        '☀️': '', '🌤️': '', '⛅': '', '🌥️': '', '☁️': '',
        '🌦️': '', '🌧️': '', '⛈️': '', '🌩️': '', '🌨️': ''
    }
    
    cleaned = text
    for emoji, replacement in emoji_map.items():
        cleaned = cleaned.replace(emoji, replacement)
    
    # Remove markdown bold markers
    cleaned = cleaned.replace('**', '')
    
    # Replace degree symbol with 'deg'
    cleaned = cleaned.replace('°C', ' deg C')
    cleaned = cleaned.replace('°', ' deg ')
    
    # Remove any remaining non-latin1 characters
    cleaned = cleaned.encode('latin-1', errors='ignore').decode('latin-1')
    
    return cleaned.strip()


def generate_pdf_report(original_results, comparison_results=None):
    """
    Generate a PDF report with weather analysis results.
    """
    try:
        pdf = FPDF()
        pdf.set_margins(left=15, top=15, right=15)
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        
        # Title
        pdf.set_font('Arial', 'B', 20)
        pdf.cell(0, 12, 'SkyCast Weather Report', 0, 1, 'C')
        pdf.ln(5)
        
        # Generated date
        pdf.set_font('Arial', 'I', 9)
        pdf.cell(0, 6, f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", 0, 1, 'C')
        pdf.ln(8)
        
        # Add original location analysis
        add_location_section(pdf, original_results, "Primary Location Analysis")
        
        # Add comparison location if available
        if comparison_results:
            pdf.add_page()
            add_location_section(pdf, comparison_results, "Alternative Location Analysis")
        
        # Output as bytes - convert bytearray to bytes for Streamlit compatibility
        output = pdf.output(dest='S')
        if isinstance(output, bytearray):
            return bytes(output)
        return output
        
    except Exception as e:
        print(f"Error generating PDF: {e}")
        import traceback
        traceback.print_exc()
        raise


def add_location_section(pdf, results, section_title):
    """
    Add a location analysis section to the PDF.
    """
    # Section title
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(0, 10, clean_text_for_pdf(section_title), 0, 1)
    pdf.ln(3)
    
    # Location name
    pdf.set_font('Arial', 'B', 13)
    location_name = clean_text_for_pdf(results['location_input'].title())
    pdf.cell(0, 8, f"Location: {location_name}", 0, 1)
    pdf.ln(2)
    
    # Coordinates
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 6, f"Coordinates: {results['location'].latitude:.4f}, {results['location'].longitude:.4f}", 0, 1)
    pdf.ln(5)
    
    # Risk Analysis Section
    pdf.set_font('Arial', 'B', 13)
    pdf.cell(0, 8, 'Weather Risk Analysis', 0, 1)
    pdf.ln(2)
    
    pdf.set_font('Arial', '', 10)
    
    # Risk metrics - with safe defaults for missing keys
    hot_thresh = results.get('hot_thresh', 32)
    rain_thresh = results.get('rain_thresh', 10)
    cold_thresh = results.get('cold_thresh', 5)
    
    pdf.cell(90, 6, f"Hot Day Risk (>{hot_thresh} deg C):", 0, 0)
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 6, f"{results['hot_prob']:.1f}%", 0, 1)
    
    pdf.set_font('Arial', '', 10)
    pdf.cell(90, 6, f"Rainy Day Risk (>{rain_thresh} mm):", 0, 0)
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 6, f"{results['rain_prob']:.1f}%", 0, 1)
    
    pdf.set_font('Arial', '', 10)
    pdf.cell(90, 6, f"Cold Day Risk (<{cold_thresh} deg C):", 0, 0)
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 6, f"{results['cold_prob']:.1f}%", 0, 1)
    
    pdf.ln(3)
    pdf.set_font('Arial', 'I', 9)
    pdf.multi_cell(0, 5, f"Analysis based on {results['total_days']} days of historical data from NASA POWER Project (past 20 years)", 0, 'L')
    pdf.ln(5)
    
    # Recommendations
    if results.get('advice_points') and len(results['advice_points']) > 0:
        pdf.set_font('Arial', 'B', 13)
        pdf.cell(0, 8, 'Recommendations', 0, 1)
        pdf.ln(2)
        
        pdf.set_font('Arial', '', 10)
        
        for point in results['advice_points']:
            # Clean the text
            cleaned = clean_text_for_pdf(point)
            
            if cleaned:  # Only add non-empty points
                # Use multi_cell for text wrapping
                pdf.multi_cell(0, 5, f"* {cleaned}", 0, 'L')
                pdf.ln(2)
    
    pdf.ln(5)
    
    # Data summary
    pdf.set_font('Arial', 'B', 13)
    pdf.cell(0, 8, 'Historical Data Summary', 0, 1)
    pdf.ln(2)
    
    if not results['hist_df'].empty:
        pdf.set_font('Arial', '', 10)
        
        avg_temp = results['hist_df']['temperature_2m_max'].mean()
        max_temp = results['hist_df']['temperature_2m_max'].max()
        min_temp = results['hist_df']['temperature_2m_max'].min()
        avg_precip = results['hist_df']['precipitation_sum'].mean()
        max_precip = results['hist_df']['precipitation_sum'].max()
        
        pdf.cell(0, 6, f"Average Maximum Temperature: {avg_temp:.1f} deg C", 0, 1)
        pdf.cell(0, 6, f"Highest Temperature: {max_temp:.1f} deg C", 0, 1)
        pdf.cell(0, 6, f"Lowest Temperature: {min_temp:.1f} deg C", 0, 1)
        pdf.cell(0, 6, f"Average Daily Precipitation: {avg_precip:.1f} mm", 0, 1)
        pdf.cell(0, 6, f"Maximum Daily Precipitation: {max_precip:.1f} mm", 0, 1)
    
    pdf.ln(8)
    
    # Footer
    pdf.set_font('Arial', 'I', 8)
    pdf.cell(0, 5, 'Data Sources: NASA POWER Project & Open-Meteo API', 0, 1, 'C')