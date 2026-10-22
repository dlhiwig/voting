import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright, TimeoutError as PlaywrightTimeout

URL = "https://survey123.arcgis.com/share/caee07c36a9c47ab87409e52d2b42447"
OPTIONS = [("Spookiest", "1208 Perseus Hill Ct"), ("Most Festive", "8 S Main St"), ("Best Business", "42 N Main St")]
SUCCESS_PHRASE = "Your response was submitted successfully."
OUTPUT_DIR = Path(__file__).parent / "review-results"


def select_and_assert(page, group_name: str, option_text: str):
    radio = page.get_by_role("radio", name=option_text, exact=True)
    # Survey123 overlays native inputs with styled labels.
    page.get_by_text(option_text, exact=True).click()
    expect(radio).to_be_checked()
    print(f"  OK {group_name}: {option_text}")


def main() -> int:
    OUTPUT_DIR.mkdir(exist_ok=True)
    success_path = OUTPUT_DIR / "confirmation_success.png"
    failure_path = OUTPUT_DIR / "failure.png"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(20_000)
        try:
            page.goto(URL, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
            print("Selecting options:")
            for group, option in OPTIONS:
                select_and_assert(page, group, option)
            page.get_by_role("button", name="Submit", exact=True).click()
            success_area = page.locator("#screenContent")
            success_area.get_by_text(SUCCESS_PHRASE, exact=True).wait_for(state="visible")
            expect(success_area).to_contain_text("Thank you.")
            page.screenshot(path=str(success_path), full_page=True)
            print("Visible confirmation verified under #screenContent")
            print(f"Screenshot: {success_path}")
            return 0
        except PlaywrightTimeout as exc:
            page.screenshot(path=str(failure_path), full_page=True)
            print(f"Timeout: {exc}")
            print(f"Screenshot: {failure_path}")
            return 1
        except Exception as exc:
            page.screenshot(path=str(failure_path), full_page=True)
            print(f"Error: {exc}")
            print(f"Screenshot: {failure_path}")
            return 1
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    sys.exit(main())
