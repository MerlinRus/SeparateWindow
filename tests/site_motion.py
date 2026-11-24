"""Check disclosure interruption, support navigation, and reduced motion."""
from playwright.sync_api import expect, sync_playwright

from onboarding import HOST, serve_site


def check_reversal(details, content_selector):
    heights = details.evaluate('''(details, selector) => {
        const summary = details.querySelector('summary');
        const content = details.querySelector(selector);
        const height = () => content.getBoundingClientRect().height;
        summary.click();
        let motion = content.getAnimations()[0];
        motion.pause();
        motion.currentTime = 80;
        const beforeClose = height();
        summary.click();
        motion = content.getAnimations()[0];
        motion.pause();
        motion.currentTime = 0;
        const startClose = height();
        motion.currentTime = motion.effect.getTiming().duration / 3;
        const beforeReopen = height();
        summary.click();
        motion = content.getAnimations()[0];
        motion.pause();
        motion.currentTime = 0;
        const startReopen = height();
        const endOpen = parseFloat(motion.effect.getKeyframes().at(-1).height);
        motion.finish();
        return {beforeClose, startClose, beforeReopen, startReopen, endOpen};
    }''', content_selector)
    assert 0 < heights['beforeReopen'] < heights['beforeClose'] < heights['endOpen']
    assert abs(heights['beforeClose'] - heights['startClose']) < 1
    assert abs(heights['beforeReopen'] - heights['startReopen']) < 1
    expect(details).to_have_attribute('open', '')


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
                check_reversal(details, '.faq-answer')
                summary.press('Enter')
                expect(details).not_to_have_attribute('open', '')

                footer = page.locator('.footer-support')
                check_reversal(footer, '.footer-support-body')
                expect(footer.locator('.footer-support-panel')).to_be_in_viewport(ratio=1)
                footer.locator('summary').press('Enter')
                expect(footer).not_to_have_attribute('open', '')

                if width == 1280:
                    page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
                    scroll = page.locator('header a[href="#support"]').evaluate('''async link => {
                        const from = scrollY;
                        link.click();
                        const frames = [from, scrollY];
                        for (let frame = 0; frame < 8; frame++) {
                            await new Promise(requestAnimationFrame);
                            frames.push(scrollY);
                        }
                        return [...new Set(frames)];
                    }''')
                    assert len(scroll) > 3, scroll
                    expect(page.locator('#support')).to_be_focused()

                page.emulate_media(reduced_motion='reduce')
                details.evaluate("details => details.querySelector('summary').click()")
                assert details.evaluate("details => details.open && !details.querySelector('.faq-answer').getAnimations().length")
                details.evaluate("details => details.querySelector('summary').click()")
                assert details.evaluate("details => !details.open && !details.querySelector('.faq-answer').getAnimations().length")
                assert page.locator('.hero-copy').evaluate("element => getComputedStyle(element).animationName === 'none'")

                footer.locator('summary').press('Enter')
                assert footer.locator('.footer-support-body').evaluate('el => !el.getAnimations().length')
                expect(footer.locator('.footer-support-panel')).to_be_in_viewport(ratio=1)
                expect(footer).to_have_attribute('open', '')
                page.close()
                print(f'PASS {route} at {width}px: smooth FAQ and footer reversal, keyboard and reduced motion')
        finally:
            browser.close()


if __name__ == '__main__':
    main()
