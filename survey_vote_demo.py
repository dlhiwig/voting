import sys
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout, expect

URL = "https://survey123.arcgis.com/share/caee07c36a9c47ab87409e52d2b42447"

OPTIONS = [
    ("Spookiest", "1208 Perseus Hill Ct"),
    ("Most Festive", "8 S Main St"),
    ("Best Business", "42 N Main St"),
]

SUCCESS_PHRASE = "Your response was submitted successfully."


def select_and_assert(page, group_name: str, option_text: str):
    """Select a visible Survey123 option and confirm its radio is checked."""
    radio = page.get_by_role("radio", name=option_text, exact=True)
    # Survey123 overlays native radio inputs with styled labels.
    page.get_by_text(option_text, exact=True).click()
    expect(radio).to_be_checked()
    print(f"  OK {group_name}: {option_text}")


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # set True once stable
        context = browser.new_context()               # fresh context = no cookies / storage
        page = context.new_page()
        page.set_default_timeout(20_000)

        try:
            page.goto(URL, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)  # let Survey123 finish rendering radios

            print("Selecting options:")
            for group, option in OPTIONS:
                select_and_assert(page, group, option)

            page.get_by_role("button", name="Submit", exact=True).click()

            # Scoped confirmation — avoids the duplicate text under #formPage
            success = page.locator("#screenContent").get_by_text(SUCCESS_PHRASE)
            success.wait_for(state="visible")
            expect(page.locator("#screenContent")).to_contain_text("Thank you.")

            page.screenshot(path="confirmation_success.png", full_page=True)
            print("Visible confirmation verified under #screenContent")
            print("Screenshot: confirmation_success.png")
            return 0

        except PlaywrightTimeout as exc:
            page.screenshot(path="failure.png", full_page=True)
            print(f"Timeout: {exc}")
            print("Screenshot: failure.png")
            return 1
        except Exception as exc:
            page.screenshot(path="failure.png", full_page=True)
            print(f"Error: {exc}")
            print("Screenshot: failure.png")
            return 1
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    sys.exit(main())
