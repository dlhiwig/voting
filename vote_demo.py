from playwright.sync_api import sync_playwright

SURVEY_URL = (
    "https://survey123.arcgis.com/share/"
    "caee07c36a9c47ab87409e52d2b42447"
)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.set_default_timeout(30_000)

        try:
            print(f"Navigating to {SURVEY_URL} ...")
            # Survey123 renders via client-side JavaScript; domcontentloaded gets the initial shell
            page.goto(SURVEY_URL, wait_until="domcontentloaded")

            # Selection 1: Spookiest
            print("Selecting '1208 Perseus Hill Ct' (Spookiest)...")
            page.get_by_label("1208 Perseus Hill Ct", exact=True).check()

            # Selection 2: Most Festive
            print("Selecting '8 S Main St' (Most Festive)...")
            page.get_by_label("8 S Main St", exact=True).check()

            # Selection 3: Best Business
            print("Selecting '42 N Main St' (Best Business)...")
            page.get_by_label("42 N Main St", exact=True).check()

            # Note: If the survey uses dropdowns instead of radio buttons, use:
            # page.get_by_label("Spookiest", exact=False).select_option(label="1208 Perseus Hill Ct")
            # page.get_by_label("Most Festive", exact=False).select_option(label="8 S Main St")
            # page.get_by_label("Best Business", exact=False).select_option(label="42 N Main St")

            # Pause so you can verify all three choices.
            approval = input(
                "\nVerify the three selections in the browser.\n"
                "Type SUBMIT to submit once: "
            ).strip()

            if approval != "SUBMIT":
                print("Canceled without submitting.")
                return

            page.get_by_role("button", name="Submit", exact=True).click()
            print(
                "\nClicked Submit once. Check the browser "
                "for confirmation that the survey was accepted."
            )
            input("Press Enter to close the browser...")

        finally:
            browser.close()


if __name__ == "__main__":
    main()
