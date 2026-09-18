import os
import json
import time
import re
from playwright.sync_api import sync_playwright
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def ask_ai_where_to_go(link_data):
    print("🧠 Asking AI to blindly analyze routing URLs based on schema...")
    
    # 🚨 PROMPT FIX: Explicitly looking for "Patient" related links and removing the Top 3 limit!
    prompt = f"""I need to extract data matching this exact schema: [Patient ID, Name, Gender, Age/DOB, Address]. 
Look at the following list of website links. Which URLs are most likely to contain the master data table with these specific fields? 
HINT: Explicitly look for links or folders containing the word 'Patient' or related terms indicating a master list/directory.
(CRITICAL: Strictly AVOID links for creating *new* records (like 'New', 'Add', 'Registration'), 'Privacy', 'Services', 'Home', or 'Logout'). 
Return ALL likely exact URL strings, separated by commas, ordered from most likely to least likely. Do not include any conversational text.

LINKS:
{link_data}"""
    
    try:
        response = groq_client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": "You are a strict URL routing API. You output only a comma-separated list of URLs."},
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )
        best_urls = response.choices[0].message.content.strip()
        
        # Clean up and split into a list of URLs
        url_list = [u.strip('`"\' \n') for u in best_urls.split(',') if 'http' in u]
        print(f"🤖 AI Decision: URLs to try -> {url_list}" )
        return url_list
    except Exception as e:
        print(f"❌ LLM Error: {e}")
        return []


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

def run_fully_autonomous_agent(url, username, password, max_pages=3):
    print(f"🚀 Booting up 100% Blind Autonomous Agent (Limit: {max_pages} Pages)...")
    master_database = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--start-maximized"]) 
        page = browser.new_page()
        
        try:
            print("🌐 Navigating to portal login...")
            # 🚨 TIMEOUT FIX 1: Give the login page 60 seconds to load
            page.goto(url, timeout=60000)
            
            print("🔑 Logging in...")
            page.locator('input[type="text"], input[type="email"], input[name*="user"], input[name*="email"]').first.fill(username)
            page.locator('input[type="password"], input[name*="pass"]').first.fill(password)
            page.keyboard.press("Enter")
            
            print("⏳ Waiting for dashboard to load...")
            page.wait_for_load_state("networkidle", timeout=60000)
            time.sleep(4)
            
            print("📂 Expanding sidebar menus to reveal hidden links...")
            try:
                dropdowns = page.locator("a[data-toggle='collapse'], li.treeview > a, .menu-toggle, .sidebar a")
                for i in range(dropdowns.count()):
                    try:
                        dropdowns.nth(i).click(force=True, timeout=1000)
                        time.sleep(0.5)
                    except:
                        pass
            except Exception as e:
                print("⚠️ Minor issue expanding menus, continuing...")
            
            print("🔍 Scanning DOM for all internal routing URLs...")
            links = page.locator("a[href]").evaluate_all("""elements => {
                return elements.map(el => ({ text: el.innerText.trim(), href: el.href })).filter(l => l.text.length > 0 && !l.href.includes('javascript') && !l.href.toLowerCase().includes('logout'))
            }""")
            
            link_list_str = "\n".join([f"Text: '{l['text']}' | URL: {l['href']}" for l in links])
            
            target_urls = ask_ai_where_to_go(link_list_str)
            
            if not target_urls:
                print("⚠️ AI couldn't find any valid URLs. Exiting.")
                return
                
            found_correct_page = False
            
            for target_url in target_urls:
                print(f"\n🖱️ Navigating to AI-selected URL -> {target_url}")
                
                # 🚨 TIMEOUT FIX 2: Ignore crashes if the hospital server is slow!
                try:
                    page.goto(target_url, timeout=60000)
                except Exception as e:
                    print("⚠️ Page load took a long time, but forcing script to continue...")
                
                print("⏳ Waiting for hospital database to fetch records...")
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except:
                    pass
                time.sleep(6) # Hard pause to let the spinning loader finish
                
                for current_page in range(1, max_pages + 1):
                    print(f"\n📄 --- Scraping Page {current_page} of {max_pages} ---")
                    
                    print("⏳ Waiting for table rows to render...")
                    try:
                        page.wait_for_selector("table tr", timeout=20000)
                    except:
                        print("⚠️ No table rows found on this page.")
                    time.sleep(3) 
                    
                    print("📥 Extracting table text...")
                    raw_text = page.inner_text("body") 
                    
                    print("🧠 Sending to Groq AI for structuring...")
                    patients_found = extract_patient_data(raw_text)
                    print(f"   ✅ Found {len(patients_found)} profiles on this page.")
                    
                    if len(patients_found) == 0:
                        if current_page == 1:
                            print("⚠️ No records found here. Jumping to the next AI suggested URL...")
                            break 
                        else:
                            print("⚠️ Reached the end of the data. Stopping pagination.")
                            found_correct_page = True
                            break 
                    
                    found_correct_page = True
                    master_database.extend(patients_found)
                    
                    if current_page < max_pages:
                        next_page_num = str(current_page + 1)
                        print(f"➡️ Attempting to click page number '{next_page_num}'...")
                        try:
                            next_btn = page.locator(f"//a[normalize-space()='{next_page_num}'] | //span[normalize-space()='{next_page_num}'] | //li[normalize-space()='{next_page_num}']").last
                            next_btn.click(force=True, timeout=5000)
                            
                            print("⏳ Waiting for new data to load...")
                            time.sleep(5) 
                        except Exception as e:
                            print(f"⚠️ Could not click page {next_page_num}: {e}")
                            break
                
                if found_correct_page:
                    break 
            
            print("\n==================================================")
            print(f"🎉 EXTRACTION COMPLETE! Total Profiles Aggregated: {len(master_database)}")
            print("==================================================")
            print(json.dumps({"all_patients": master_database}, indent=4))
            
        except Exception as e:
            print(f"❌ Error: {e}")
        finally:
            input("🛑 Press ENTER to close browser...")
            browser.close()

if __name__ == "__main__":
    TARGET_URL = "https://saph.spartahms.com" 
    USER = ""
    PASS = ""
    
    run_fully_autonomous_agent(TARGET_URL, USER, PASS, max_pages=3 )
