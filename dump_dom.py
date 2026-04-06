from playwright.sync_api import sync_playwright
try:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto('http://localhost:8501')
        page.wait_for_selector('text=Options', timeout=10000)
        html = page.content()
        with open('dom.html', 'w', encoding='utf-8') as f:
            f.write(html)
        browser.close()
except Exception as e:
    print(e)
