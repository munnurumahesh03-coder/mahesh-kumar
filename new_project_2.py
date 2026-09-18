import os
import json
import time
import re
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def ask_ai_where_to_go(all_urls_list):
    print("🧠 Running Hybrid AI + Deterministic Routing...")
    
    # 1. PYTHON SAFETY NET: Guarantee we NEVER miss the obvious links
    keywords = ['patient', 'record', 'address', 'visit', 'history', 'demographic', 'desk']
    junk_words = ['new', 'add', 'registration', 'privacy', 'logout', 'services', 'home', 'pharmacy', 'hrms']
    
    target_urls = []
    for link in all_urls_list:
        text_lower = link['text'].lower()
        url_lower = link['url'].lower()
        
        # If it has a good keyword AND doesn't have a junk keyword, keep it!
        if any(k in text_lower or k in url_lower for k in keywords):
            if not any(j in text_lower or j in url_lower for j in junk_words):
                if link['url'] not in target_urls:
                    target_urls.append(link['url'])

    # 2. AI FALLBACK: Ask the AI to check the remaining links just in case
    link_data = "\n".join([f"Text: '{l['text']}' | URL: {l['url']}" for l in all_urls_list])
    
    prompt = f"""I need to extract scattered patient data: [Patient ID, Name, Gender, Age/DOB, Address]. 
Look at these links. Which URLs might contain ANY of these fields?
(CRITICAL: Strictly AVOID 'New', 'Add', 'Registration', 'Privacy', 'Services', 'Logout', 'Pharmacy', 'HRMS'). 
CRITICAL INSTRUCTION: DO NOT BE LAZY. Return EVERY SINGLE valid URL. Do not truncate.
Return ONLY exact URL strings, separated by commas.

LINKS:
{link_data}"""
    
    try:
        response = groq_client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": "You are a strict URL routing API. Output only a comma-separated list."},
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )
        ai_urls = [u.strip('`"\' \n') for u in response.choices[0].message.content.strip().split(',') if 'http' in u or '#' in u]
        
        # Combine Python's guaranteed list with the AI's list
        for u in ai_urls:
            if u not in target_urls and not any(j in u.lower( ) for j in junk_words):
                target_urls.append(u)
                
    except Exception as e:
        print(f"⚠️ Minor LLM Error, relying on Python Safety Net: {e}")

    print(f"\n🤖 Hybrid Decision: Found {len(target_urls)} guaranteed URLs to crawl for scattered data!")
    print("📋 TARGET URLS SELECTED:")
    for i, url in enumerate(target_urls, 1):
        print(f"   {i}. {url}")
    print("-" * 50)
    
    return target_urls

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
    prompt = f"Extract patient records from this text. The data might be INCOMPLETE (e.g., only ID and Address). Extract whatever fields are available. You MUST map 'MR No' or 'Patient ID' to patient_id. Return ONLY valid JSON.\n\nSCHEMA:\n{json.dumps(schema)}\n\nDATA:\n{raw_text}"
    
    try:
        response = groq_client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"}
        )
        data = json.loads(response.choices[0].message.content.strip())
        # Only keep records that have at least a Patient ID so we can merge them later
        valid_patients = [p for p in data.get("patients", []) if p.get("patient_id")]
        return valid_patients
    except Exception as e:
        return []

def run_scattered_data_agent(base_url, username, password, max_pages=3):
    print(f"🚀 Booting up Scattered Data Aggregation Agent...")
    
    # 🚨 SMART MERGE DICTIONARY: Keys are Patient IDs, Values are the combined data
    master_database = {}
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--start-maximized"]) 
        page = browser.new_page()
        
        try:
            print("🌐 Navigating to portal login...")
            page.goto(base_url, timeout=60000)
            
            print("🔑 Logging in...")
            page.locator('input[type="text"], input[type="email"], input[name*="user"], input[name*="email"]').first.fill(username)
            page.locator('input[type="password"], input[name*="pass"]').first.fill(password)
            page.keyboard.press("Enter")
            
            print("⏳ Waiting for dashboard and sidebar to fully load...")
            page.wait_for_load_state("networkidle", timeout=60000)
            time.sleep(8) 
            
            print("📂 Expanding ALL sidebar menus to reveal every hidden folder...")
            try:
                dropdowns = page.locator("a[data-toggle='collapse'], li.treeview > a, .menu-toggle, .sidebar a, .nav-link")
                for i in range(dropdowns.count()):
                    try:
                        dropdowns.nth(i).click(force=True, timeout=1000)
                        time.sleep(0.2)
                    except:
                        pass
            except Exception:
                pass
            
            print("🔍 Harvesting EVERY link on the portal...")
            raw_links = page.locator("a").evaluate_all("""elements => elements.map(el => {
                return { text: el.innerText.trim(), href: el.getAttribute('href') }
            })""")
            
            all_urls = []
            for link in raw_links:
                href = link.get('href')
                text = link.get('text', '')
                if href and not any(junk in href.lower() for junk in ['logout', 'javascript:']):
                    if href.startswith('#'):
                        full_url = page.url.split('#')[0] + href
                    else:
                        full_url = urljoin(page.url, href)
                    
                    if full_url not in [u['url'] for u in all_urls]:
                        all_urls.append({'text': text, 'url': full_url})
            
            print(f"✅ Found {len(all_urls)} unique folders/links.")
            
            # 🚨 PASSING THE FULL LIST TO THE HYBRID ROUTER
            target_urls = ask_ai_where_to_go(all_urls)
            
            if not target_urls:
                print("⚠️ AI couldn't find any valid URLs. Exiting.")
                return
            
            # 🚨 EXHAUSTIVE CRAWL LOOP 🚨
            for target_url in target_urls:
                print(f"\n🖱️ Crawling folder -> {target_url}")
                
                try:
                    page.goto(target_url, timeout=45000)
                except Exception:
                    print("⚠️ Page load timeout, forcing script to continue...")
                
                print("⏳ Waiting for data to render...")
                time.sleep(5) 
                
                for current_page in range(1, max_pages + 1):
                    print(f"\n📄 --- Scanning Page {current_page} ---")
                    time.sleep(2)
                    
                    raw_text = page.inner_text("body") 
                    
                    print("🧠 Asking AI to extract partial/full patient records...")
                    patients_found = extract_patient_data(raw_text)
                    
                    if len(patients_found) == 0:
                        if current_page == 1:
                            print("⏭️ AI confirmed no patient data here. Moving to next folder...")
                            break 
                        else:
                            print("⚠️ Reached the end of the data.")
                            break 
                    
                    print(f"   ✅ Found {len(patients_found)} profiles. Merging into Master Database...")
                    
                    # 🚨 SMART MERGE LOGIC: Combines scattered data using Patient ID 🚨
                    for p in patients_found:
                        pid = p.get("patient_id")
                        if not pid: continue
                        
                        if pid not in master_database:
                            master_database[pid] = p 
                        else:
                            for key, value in p.items():
                                if value: 
                                    master_database[pid][key] = value
                    
                    if current_page < max_pages:
                        next_page_num = str(current_page + 1)
                        print(f"➡️ Attempting to click page number '{next_page_num}'...")
                        try:
                            next_btn = page.locator(f"//a[normalize-space()='{next_page_num}'] | //span[normalize-space()='{next_page_num}'] | //li[normalize-space()='{next_page_num}']").last
                            next_btn.click(force=True, timeout=5000)
                            time.sleep(5) 
                        except Exception:
                            print(f"⚠️ Could not click page {next_page_num}. End of list.")
                            break
            
            print("\n==================================================")
            print(f"🎉 EXTRACTION COMPLETE! Total Unique Profiles Aggregated: {len(master_database)}")
            print("==================================================")
            
            final_list = list(master_database.values())
            print(json.dumps({"all_patients": final_list}, indent=4))
            
        except Exception as e:
            print(f"❌ Error: {e}")
        finally:
            input("🛑 Press ENTER to close browser...")
            browser.close()

if __name__ == "__main__":
    TARGET_URL = "https://saph.spartahms.com" 
    USER = ""
    PASS = ""
    
    run_scattered_data_agent(TARGET_URL, USER, PASS, max_pages=3 )
