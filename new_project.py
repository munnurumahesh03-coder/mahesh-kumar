import os
import json
import time
from playwright.sync_api import sync_playwright
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def extract_patient_data(raw_text):
    schema = {
        "patients": [
            {
                "patient_id": None, 
                "patient_name": None,
                "gender": None,
                "age_dob": None,
                "address": None
            }
        ]
    }
    prompt = f"Extract all patient records from this table text into the exact JSON schema provided. Map 'MR No' to patient_id. Return ONLY valid JSON.\n\nSCHEMA:\n{json.dumps(schema)}\n\nDATA:\n{raw_text}"
    
    try:
        response = groq_client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"}
        )
        data = json.loads(response.choices[0].message.content.strip())
        valid_patients = [p for p in data.get("patients", []) if p.get("patient_name")]
        return valid_patients
    except Exception as e:
        print(f"❌ LLM Error: {e}")
        return []

def run_pagination_agent(url, username, password, max_pages=3):
    print(f"🚀 Booting up Targeted Pagination Agent (Limit: {max_pages} Pages)...")
    master_database = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--start-maximized"]) 
        page = browser.new_page()
        
        try:
            print("🌐 Navigating to portal login...")
            page.goto(url)
            
            print("🔑 Logging in...")
            page.locator('input[type="text"], input[type="email"], input[name*="user"], input[name*="email"]').first.fill(username)
            page.locator('input[type="password"], input[name*="pass"]').first.fill(password)
            page.keyboard.press("Enter")
            
            print("⏳ Waiting for dashboard to load...")
            page.wait_for_load_state("networkidle")
            time.sleep(3)
            
            print("📂 Navigating directly to Patient Status table...")
            page.goto("https://saph.spartahms.com/Show/Index/659#/PatientStatus" )
            
            # 🚨 NUMERIC PAGINATION LOOP 🚨
            for current_page in range(1, max_pages + 1):
                print(f"\n📄 --- Scraping Page {current_page} of {max_pages} ---")
                
                print("⏳ Waiting for table data to render...")
                page.wait_for_selector("table", timeout=15000)
                time.sleep(2) # Extra buffer for dynamic rows
                
                print("📥 Extracting table text...")
                raw_text = page.inner_text("table") 
                
                print("🧠 Sending to Groq AI for structuring...")
                patients_found = extract_patient_data(raw_text)
                print(f"   ✅ Found {len(patients_found)} patients on this page.")
                
                master_database.extend(patients_found)
                
                # If we haven't reached the max pages, click the NEXT NUMBER
                if current_page < max_pages:
                    next_page_num = str(current_page + 1)
                    print(f"➡️ Attempting to click page number '{next_page_num}'...")
                    try:
                        # 🚨 BULLETPROOF XPATH LOCATOR WITH FORCE CLICK 🚨
                        # This looks for any link or span containing exactly the number, ignoring spaces
                        next_btn = page.locator(f"//a[normalize-space()='{next_page_num}'] | //span[normalize-space()='{next_page_num}'] | //li[normalize-space()='{next_page_num}']").last
                        
                        # force=True bypasses Playwright's strict visibility checks
                        next_btn.click(force=True, timeout=5000)
                        
                        print("⏳ Waiting for new data to load...")
                        time.sleep(3) # Wait for the table to refresh with new data
                    except Exception as e:
                        print(f"⚠️ Could not click page {next_page_num}: {e}")
                        break
            
            print("\n==================================================")
            print(f"🎉 EXTRACTION COMPLETE! Total Patients Aggregated: {len(master_database)}")
            print("==================================================")
            print(json.dumps({"all_patients": master_database}, indent=4))
            
        except Exception as e:
            print(f"❌ Error: {e}")
        finally:
            input("🛑 Press ENTER to close browser...")
            browser.close()

if __name__ == "__main__":
    TARGET_URL = "https://saph.spartahms.com" 
    USER = "PUT_THEIR_EMAIL_HERE"
    PASS = "PUT_THEIR_PASSWORD_HERE"
    
    run_pagination_agent(TARGET_URL, USER, PASS, max_pages=3 )
