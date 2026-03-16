import streamlit as st
from datetime import date, timedelta
import pandas as pd
import plotly.express as px
from get_data import get_historical_data_for_event, simulate_future_forecast, get_immediate_forecast, generate_pdf_report, find_best_dates
from geopy.geocoders import Nominatim
import random
import traceback

# ==============================
# Main Analysis & Callback Logic
# ==============================
def run_analysis(location_name):
    """A centralized function to run the full analysis for a given location name."""
    with st.spinner(f"Analyzing {location_name}..."):
        geolocator = Nominatim(user_agent="skycast_app_v1")
        location = None
        try:
            location = geolocator.geocode(location_name, timeout=10)
        except Exception as e:
            st.error(f"Geocoding service failed. Please check your connection. Error: {e}")
            st.session_state.analysis_done = False
            return

        if not location:
            st.error(f"Location not found: {location_name}. Please try a different name or be more specific.")
            st.session_state.analysis_done = False
            return

        # Fetch all data from get_data.py
        hist_df = get_historical_data_for_event(location.latitude, location.longitude, st.session_state.event_start, st.session_state.event_end)
        sim_df = simulate_future_forecast(hist_df, st.session_state.event_start, st.session_state.event_end)
        imm_df = get_immediate_forecast(location.latitude, location.longitude)

        # Calculate risk probabilities
        hot_prob, rain_prob, cold_prob, total_days, advice_points = 0, 0, 0, 0, []
        if not hist_df.empty:
            total_days = len(hist_df)
            hot_days = (hist_df["temperature_2m_max"] > st.session_state.hot_thresh).sum()
            rainy_days = (hist_df["precipitation_sum"] > st.session_state.rain_thresh).sum()
            cold_days = (hist_df["temperature_2m_max"] < st.session_state.cold_thresh).sum()
            hot_prob = (hot_days / total_days) * 100 if total_days > 0 else 0
            rain_prob = (rainy_days / total_days) * 100 if total_days > 0 else 0
            cold_prob = (cold_days / total_days) * 100 if total_days > 0 else 0

        # Store results in a dictionary
        results = {
            "location_input": location_name,
            "location": location,
            "hist_df": hist_df, "sim_df": sim_df, "imm_df": imm_df,
            "hot_prob": hot_prob, "rain_prob": rain_prob, "cold_prob": cold_prob, "total_days": total_days,
            "hot_thresh": st.session_state.hot_thresh, "rain_thresh": st.session_state.rain_thresh, "cold_thresh": st.session_state.cold_thresh,
            "advice_points": advice_points
        }
        return results

def analyze_new_location_callback(new_loc_name):
    """Callback for the suggestion button. Runs analysis and stores results as current."""
    # Clear the analysis flag to trigger a fresh analysis
    st.session_state.analysis_done = False
    st.session_state.location_input = new_loc_name
    st.session_state.original_results = None
    st.session_state.current_results = None
    st.session_state.comparison_results = None

# ==============================
# Main App UI
# ==============================
st.set_page_config(page_title="SkyCast Weather Forecaster", layout="wide")

# --- Initialize Session State ---
if "analysis_done" not in st.session_state: st.session_state.analysis_done = False
if "location_input" not in st.session_state: st.session_state.location_input = ""
if "original_results" not in st.session_state: st.session_state.original_results = None
if "comparison_results" not in st.session_state: st.session_state.comparison_results = None
if "current_results" not in st.session_state: st.session_state.current_results = None

# --- HEADER ---
st.title("⛅ SkyCast Weather Forecaster")
st.markdown("Analyze historical weather risk, get forecasts, and find the best dates for your event using NASA data.")

# --- INPUT FORM ---
with st.container(border=True):
    st.header("1. Describe Your Future Event")
    
    # Location input - full width
    location_input = st.text_input("Enter Event Location (e.g., Kothamangalam, Paris, Tokyo):", key="location_input")
    
    # Date inputs - side by side
    col1, col2 = st.columns(2)
    with col1:
        event_start = st.date_input("Event Start Date:", date.today() + timedelta(days=90))
    with col2:
        event_end = st.date_input("Event End Date:", date.today() + timedelta(days=92))

    if st.button("Analyze Event Weather", type="primary"):
        if not st.session_state.location_input:
            st.warning("Please enter a location.")
        elif event_start > event_end:
            st.error("Error: The event start date must be before the end date.")
        else:
            st.session_state.hot_thresh = 32
            st.session_state.rain_thresh = 10
            st.session_state.cold_thresh = 5
            st.session_state.event_start = event_start
            st.session_state.event_end = event_end
            results = run_analysis(st.session_state.location_input)
            if results:
                st.session_state.original_results = results
                st.session_state.current_results = results
                st.session_state.comparison_results = None
                st.session_state.analysis_done = True
                st.success("Analysis Complete!")

# Auto-trigger analysis if location was set by callback
if (st.session_state.location_input and 
    not st.session_state.analysis_done and 
    'event_start' in st.session_state):
    results = run_analysis(st.session_state.location_input)
    if results:
        st.session_state.original_results = results
        st.session_state.current_results = results
        st.session_state.comparison_results = None
        st.session_state.analysis_done = True

# --- RESULTS DASHBOARD ---
if st.session_state.analysis_done and st.session_state.current_results:
    res = st.session_state.current_results
    
    country = res['location'].address.split(',')[-1].strip()
    display_name = res['location_input'].title()
    clean_header = f"Weather Insights for: {display_name} ({country})"
    st.header(clean_header)

    # --- MAP DISPLAY ---
    map_data = pd.DataFrame({'lat': [res['location'].latitude], 'lon': [res['location'].longitude]})
    st.map(map_data, zoom=8)
    
    # --- NASA WORLDVIEW INTEGRATION ---
    st.subheader("Recent Satellite View from NASA Worldview")
    lat, lon = res['location'].latitude, res['location'].longitude
    worldview_url = f"https://worldview.earthdata.nasa.gov/?p=geographic&l=VIIRS_SNPP_CorrectedReflectance_TrueColor,MODIS_Aqua_CorrectedReflectance_TrueColor,MODIS_Terra_CorrectedReflectance_TrueColor,Reference_Labels,Reference_Features,Coastlines&t={(date.today() - timedelta(days=2)).strftime('%Y-%m-%d')}&z=9&v={lon},{lat},{lon+1},{lat+1}"
    
    st.image(f"https://worldview.earthdata.nasa.gov/snapshot?REQUEST=GetSnapshot&TIME={(date.today() - timedelta(days=2)).strftime('%Y-%m-%d')}&BBOX={lat-0.5},{lon-0.5},{lat+0.5},{lon+0.5}&CRS=EPSG:4326&LAYERS=VIIRS_SNPP_CorrectedReflectance_TrueColor,Coastlines&FORMAT=image/jpeg&WIDTH=800&HEIGHT=600",
             use_container_width=True)
    
    st.markdown(f"### 🛰️ Recent satellite imagery of {display_name}")
    st.markdown("*Courtesy of NASA Worldview*")
    
    st.markdown(f"[🔗 Explore this area interactively on NASA Worldview]({worldview_url})")
    st.markdown("---")
    
    # --- 2. HISTORICAL RISK ANALYSIS ---
    st.subheader("2. Historical Risk Analysis")
    if not res['hist_df'].empty:
        col1_res, col2_res, col3_res = st.columns(3)
        with col1_res:
            st.metric("Chance of a 'Hot' Day", f"{res['hot_prob']:.1f}%", help=f"Based on a threshold of >{res['hot_thresh']}°C")
        with col2_res:
            st.metric("Chance of a 'Rainy' Day", f"{res['rain_prob']:.1f}%", help=f"Based on a threshold of >{res['rain_thresh']} mm/day")
        with col3_res:
            st.metric("Chance of a 'Cold' Day", f"{res['cold_prob']:.1f}%", help=f"Based on a threshold of <{res['cold_thresh']}°C")
        st.caption(f"Analysis based on {res['total_days']} total days of data from the past 20 years from NASA's POWER Project.")

        # --- 3. FUTURE WEATHER OUTLOOK ---
        st.subheader("3. Future Weather Outlook")
        tab1, tab2 = st.tabs(["Simulated Forecast", "Immediate Forecast"])
        with tab1:
            st.markdown(f"##### Simulated Daily Forecast for {st.session_state.event_start.strftime('%B %Y')}")
            if not res['sim_df'].empty:
                st.dataframe(res['sim_df'])
                fig_sim = px.line(res['sim_df'], x="Date", y=res['sim_df'].columns[1:], markers=True, title="Simulated Day-by-Day Weather")
                
                # Increase legend font size AND capitalize Variable
                fig_sim.update_layout(
                    legend=dict(
                        font=dict(size=16),
                        title=dict(text="Variable", font=dict(size=18))
                    )
                )
                
                st.plotly_chart(fig_sim, use_container_width=True)
            else:
                st.warning("Could not generate a simulated forecast.")
        with tab2:
            st.markdown("##### Immediate 16-Day Forecast")
            if not res['imm_df'].empty:
                st.dataframe(res['imm_df'])
            else:
                st.warning("Could not retrieve the immediate forecast.")
        
        # --- 4. SMART REGIONAL SUGGESTIONS ---
        st.subheader("4. Smart Regional Suggestions")
        advice_points = []
        rain_prob = res.get('rain_prob', 0)
        hot_prob = res.get('hot_prob', 0)
        cold_prob = res.get('cold_prob', 0)
        is_high_risk = rain_prob > 50 or hot_prob > 50 or cold_prob > 50

        # Check for any moderate risk
        has_moderate_risk = (rain_prob > 20 or hot_prob > 20 or cold_prob > 20) and not is_high_risk

        # Better logic for extreme locations
        location_lower = res['location_input'].lower()
        address_lower = res['location'].address.lower()
        
        # Check for extreme locations
        avg_temp = res['hist_df']['temperature_2m_max'].mean() if not res['hist_df'].empty else None
        is_antarctica = (
            'antarct' in location_lower or 
            'antarct' in address_lower or 
            res['location'].latitude < -60 or
            (avg_temp is not None and avg_temp < -10)
        )
        
        if is_high_risk:
            # Determine which risk(s) are high
            risk_types = []
            if cold_prob > 50:
                risk_types.append(f"cold (❄️ {cold_prob:.0f}%)")
            if hot_prob > 50:
                risk_types.append(f"heat (🔥 {hot_prob:.0f}%)")
            if rain_prob > 50:
                risk_types.append(f"rain (🌧️ {rain_prob:.0f}%)")
            
            risk_description = ", ".join(risk_types)
            
            if cold_prob > 50:
                message = f"❄️ **High Cold Risk:** There's a {cold_prob:.0f}% chance of cold weather (below {res['cold_thresh']}°C). Be prepared with appropriate cold-weather gear and consider warmer alternatives."
                advice_points.append(message)
                st.warning(message)
            elif hot_prob > 50:
                message = f"🔥 **High Heat Risk:** There's a {hot_prob:.0f}% chance of hot weather (above {res['hot_thresh']}°C). Consider cooler destinations or times."
                advice_points.append(message)
                st.warning(message)
            elif rain_prob > 50:
                message = f"🌧️ **High Rain Risk:** With a {rain_prob:.0f}% chance of rainy conditions (>{res['rain_thresh']}mm/day), you might want to consider drier destinations."
                advice_points.append(message)
                st.warning(message)
        elif has_moderate_risk:
            risk_types = []
            if cold_prob > 20:
                risk_types.append(f"cold days ({cold_prob:.0f}%)")
            if hot_prob > 20:
                risk_types.append(f"hot days ({hot_prob:.0f}%)")
            if rain_prob > 20:
                risk_types.append(f"rainy days ({rain_prob:.0f}%)")
            
            risk_description = ", ".join(risk_types)
            message = f"⚠️ **Moderate Risk:** Be aware of potential {risk_description}. It is advisable to have a backup plan."
            advice_points.append(message)
            st.info(message)
        else:
            message = "✅ **Good Conditions Expected:** Your selected location and dates have a low historical risk of adverse weather."
            advice_points.append(message)
            st.success(message)

        # Search for better dates only for high risk (DISABLED for performance)
        # The find_best_dates function is too slow, so we skip it for now
        # if is_high_risk:
        #     try:
        #         event_duration = (st.session_state.event_end - st.session_state.event_start).days + 1
        #         search_start = st.session_state.event_start - timedelta(days=45)
        #         search_end = st.session_state.event_start + timedelta(days=45)
        #         best_start, best_end = find_best_dates(res['location'].latitude, res['location'].longitude, search_start, search_end, res['hot_thresh'], res['rain_thresh'], event_duration)
        #         
        #         if best_start and best_start.strftime('%Y-%m-%d') != st.session_state.event_start.strftime('%Y-%m-%d'):
        #             advice = f"Date Suggestion: The period from {best_start.strftime('%B %d')} to {best_end.strftime('%B %d')} has a historically lower weather risk."
        #             advice_points.append(advice)
        #             st.info(f"💡 {advice}")
        #     except Exception as e:
        #         print(f"Error finding better dates: {e}")

        # Show location suggestions for ALL high-risk locations
        if is_high_risk:
            suggested_locations = []
            address = res['location'].address
            country = address.split(',')[-1].strip()
            cooler_south_india = ["Munnar, Kerala", "Ooty, Tamil Nadu", "Kodaikanal, Tamil Nadu"]
            cooler_north_india = ["Shimla, Himachal Pradesh", "Manali, Himachal Pradesh", "Nainital, Uttarakhand"]
            drier_india = ["Jaisalmer, Rajasthan", "Leh, Ladakh", "Pune, Maharashtra"]
            cooler_international = ["Zurich, Switzerland", "Vancouver, Canada", "Oslo, Norway"]
            drier_international = ["Dubai, UAE", "Cairo, Egypt", "Lima, Peru"]
            warmer_india = ["Goa", "Chennai, Tamil Nadu", "Mumbai, Maharashtra"]
            warmer_international = ["Dubai, UAE", "Miami, USA", "Barcelona, Spain", "Singapore", "Bangkok, Thailand"]
            
            # Determine which suggestions to show
            if cold_prob > 50:
                # Special handling for Antarctica/extreme cold
                if is_antarctica or cold_prob >= 100 or (avg_temp is not None and avg_temp < -10):
                    warmer_international = ["Ushuaia, Argentina", "Punta Arenas, Chile", "Hobart, Australia", 
                                          "Christchurch, New Zealand", "Cape Town, South Africa"]
                
                source_list = warmer_india if country == "India" else warmer_international
                num_suggestions = min(3, len(source_list))
                suggested_locations = random.sample(source_list, num_suggestions)
                
            elif rain_prob > 50:
                source_list = drier_india if country == "India" else drier_international
                num_suggestions = min(3, len(source_list))
                suggested_locations = random.sample(source_list, num_suggestions)
                
            elif hot_prob > 50:
                if country == "India":
                    if any(state in address for state in ["Kerala", "Tamil Nadu", "Karnataka", "Andhra Pradesh", "Telangana"]):
                        source_list = cooler_south_india
                    else:
                        source_list = cooler_north_india
                else:
                    source_list = cooler_international
                num_suggestions = min(3, len(source_list))
                suggested_locations = random.sample(source_list, num_suggestions)
            
            # Display suggestion buttons - FIXED: Only one set of buttons now
            if suggested_locations:
                st.markdown("")
                st.markdown("##### Click a location to analyze it instead:")
                cols = st.columns(len(suggested_locations))
                # Use hash of current location + suggestions to create truly unique keys
                loc_hash = hash(res['location_input'] + str(suggested_locations))
                for i, loc in enumerate(suggested_locations):
                    with cols[i]:
                        button_key = f"btn_{abs(loc_hash)}_{i}"
                        st.button(loc, on_click=analyze_new_location_callback, args=[loc], key=button_key, use_container_width=True)

        res['advice_points'] = advice_points

        # --- 5. DOWNLOAD YOUR REPORT ---
        st.subheader("5. Download Your Report")
        original_results = st.session_state.original_results
        comparison_results = st.session_state.comparison_results
        
        original_results['advice_points'] = advice_points
        if comparison_results:
            comparison_results['advice_points'] = []

        # Try to generate PDF
        pdf_available = False
        pdf_data = None
        pdf_error_message = None
        
        try:
            pdf_data = generate_pdf_report(original_results, comparison_results)
            if isinstance(pdf_data, bytearray):
                pdf_data = bytes(pdf_data)
            pdf_available = True
        except Exception as e:
            pdf_error_message = str(e)
            st.warning(f"⚠️ PDF generation encountered an issue: {pdf_error_message}")
            st.info("CSV download is still available below.")
            print("PDF Generation Error Details:")
            traceback.print_exc()
        
        # Prepare CSV data
        orig_df = original_results['hist_df'].copy()
        orig_df['Location'] = original_results['location_input'].title()
        csv_parts = [orig_df]
        if comparison_results:
            comp_df = comparison_results['hist_df'].copy()
            comp_df['Location'] = comparison_results['location_input'].title()
            csv_parts.append(comp_df)
        
        csv_string = pd.concat(csv_parts).to_csv(index=False)
        if not original_results['sim_df'].empty:
            csv_string += "\n\n--- Simulated Forecast for Your Event ---\n"
            csv_string += original_results['sim_df'].to_csv(index=False)
        if advice_points:
            csv_string += "\n\n--- Smart Suggestions & Travel Advice ---\n"
            for point in advice_points:
                csv_string += f"- {point.replace('**', '')}\n"
        csv_data = csv_string.encode('utf-8')
        
        col1_dl, col2_dl = st.columns(2)
        with col1_dl:
            st.download_button("📄 Download Data (CSV)", csv_data, f"weather_data_{original_results['location_input'].replace(' ', '_').replace(',', '')}.csv", "text/csv", use_container_width=True)
        with col2_dl:
            if pdf_available and pdf_data:
                st.download_button("📑 Download Report (PDF)", pdf_data, f"weather_report_{original_results['location_input'].replace(' ', '_').replace(',', '')}.pdf", "application/pdf", use_container_width=True)
            else:
                st.button("📑 PDF Unavailable", disabled=True, use_container_width=True, help=pdf_error_message if pdf_error_message else "PDF generation failed")

    else:
        st.error("Could not retrieve any historical data for this location. The analysis cannot be completed.")