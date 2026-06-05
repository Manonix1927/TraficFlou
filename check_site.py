from playwright.sync_api import sync_playwright
import re, time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36")
    page = context.new_page()

    all_requests = []
    def on_req(req):
        all_requests.append(req.url)
    page.on("request", on_req)

    page.goto("https://stavka.com.ua/", wait_until="load", timeout=30000)
    time.sleep(5)

    print("=== Analytics requests ===")
    for u in all_requests:
        if any(k in u for k in ["analytics", "gtag", "gtm", "collect", "pixel", "metrika", "stat"]):
            print(u[:150])

    print("\n=== GA IDs in rendered HTML ===")
    html = page.content()
    print("GA4:", list(set(re.findall(r'G-[A-Z0-9]{6,}', html))))
    print("GTM:", list(set(re.findall(r'GTM-[A-Z0-9]{4,}', html))))

    context.close()
    browser.close()
