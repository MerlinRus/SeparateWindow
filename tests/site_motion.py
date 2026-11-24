"""Check FAQ interruption and reduced motion on the built website."""
from playwright.sync_api import expect, sync_playwright

from onboarding import HOST, serve_site


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='chromium', headless=True)
        try:
            for route, width in (('/', 390), ('/en/', 1280)):
                page = browser.new_page(viewport={'width': width, 'height': 800})
                page.route(HOST + '/**', serve_site)
                assert page.goto(HOST + route).ok
                details = page.locator('.answers details').first
                summary = details.locator('summary')
                heights = details.evaluate('''details => {
                    const summary = details.querySelector('summary');
                    const answer = details.querySelector('.faq-answer');
                    const height = () => answer.getBoundingClientRect().height;
                    summary.click();
                    let motion = answer.getAnimations()[0];
                    motion.pause();
                    motion.currentTime = 80;
                    const beforeClose = height();
                    summary.click();
                    motion = answer.getAnimations()[0];
                    motion.pause();
                    motion.currentTime = 0;
                    const startClose = height();
                    motion.currentTime = motion.effect.getTiming().duration / 3;
                    const beforeReopen = height();
                    summary.click();
                    motion = answer.getAnimations()[0];
                    motion.pause();
                    motion.currentTime = 0;
                    const startReopen = height();
                    const endOpen = parseFloat(motion.effect.getKeyframes().at(-1).height);
                    motion.finish();
                    return {beforeClose, startClose, beforeReopen, startReopen, endOpen};
                }''')
                assert 0 < heights['beforeReopen'] < heights['beforeClose'] < heights['endOpen']
                assert abs(heights['beforeClose'] - heights['startClose']) < 1
                assert abs(heights['beforeReopen'] - heights['startReopen']) < 1
                expect(details).to_have_attribute('open', '')
                summary.press('Enter')
                expect(details).not_to_have_attribute('open', '')

                page.emulate_media(reduced_motion='reduce')
                details.evaluate("details => details.querySelector('summary').click()")
                assert details.evaluate("details => details.open && !details.querySelector('.faq-answer').getAnimations().length")
                details.evaluate("details => details.querySelector('summary').click()")
                assert details.evaluate("details => !details.open && !details.querySelector('.faq-answer').getAnimations().length")
                assert page.locator('.hero-copy').evaluate("element => getComputedStyle(element).animationName === 'none'")

                footer = page.locator('.footer-support')
                footer.locator('summary').press('Enter')
                expect(footer.locator('.footer-support-panel')).to_be_in_viewport(ratio=1)
                expect(footer).to_have_attribute('open', '')
                page.close()
                print(f'PASS {route} at {width}px: smooth FAQ reversal, keyboard and reduced motion, footer disclosure')
        finally:
            browser.close()


if __name__ == '__main__':
    main()
