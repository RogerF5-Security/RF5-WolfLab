"""Run against a demo server on port 8765. Playwright is a development dependency."""
import json,os
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];out=ROOT/'.qa';out.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,**({'executable_path':os.environ['WOLFLAB_CHROMIUM']} if os.environ.get('WOLFLAB_CHROMIUM') else {}))
    page=browser.new_page(viewport={'width':1440,'height':1100});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8765/',wait_until='networkidle');page.get_by_text('DEMO · SIN RADIO',exact=True).wait_for()
    page.locator('#ssid').fill('WolfLab_Presentacion');page.locator('#campaign').fill('Presentacion RF5');page.locator('#save').click();page.wait_for_timeout(3500)
    assert page.locator('#ssid-display').inner_text()=='WolfLab_Presentacion'
    page.locator('#pause').click();page.wait_for_timeout(800);assert page.locator('#active-label').inner_text()=='Radio pausada'
    page.locator('#start').click();page.wait_for_timeout(800);page.screenshot(path=str(out/'operator.png'),full_page=True)
    page.locator('#show-private').check();assert 'DEMO-' in page.locator('#records').inner_text()
    with page.expect_download() as download:page.locator('#export-csv').click()
    download.value.save_as(str(out/'demo.csv'));page.locator('#show-private').uncheck()
    wall=browser.new_page(viewport={'width':1600,'height':1000});wall.goto('http://127.0.0.1:8765/wall',wait_until='networkidle');wall.locator('.sheep').first.wait_for()
    text=wall.locator('body').inner_text();assert 'DEMO-' not in text and 'Demo 00' not in text;wall.screenshot(path=str(out/'wall.png'),full_page=True)
    mobile=browser.new_page(viewport={'width':390,'height':844},is_mobile=True);mobile.goto('http://127.0.0.1:8765/',wait_until='networkidle')
    assert mobile.evaluate('document.documentElement.scrollWidth<=innerWidth');mobile.screenshot(path=str(out/'mobile.png'),full_page=True)
    assert not errors,errors
    (out/'browser-result.json').write_text(json.dumps({'passed':True,'checks':['SSID change','pause/start','private toggle','CSV export','anonymous wall','mobile overflow','no JS exceptions']},indent=2))
    print('Browser checks passed');browser.close()
