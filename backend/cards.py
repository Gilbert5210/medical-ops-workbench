import hashlib
import html
from pathlib import Path

from .db import DATA


def bundle_hash(draft):
    import json
    data = {key: getattr(draft, key) for key in ("id", "version", "title", "body", "tags", "cards", "platform")}
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def card_html(draft, index=0):
    cards = draft.cards or [{"heading": draft.title, "text": "医学科研学习笔记"}]
    card = cards[index]
    title = html.escape(str(card.get("heading", "")))
    body = html.escape(str(card.get("text", ""))).replace("\n", "<br>")
    footer = f"医学科研 · 学习与讨论　　{index + 1:02d} / {len(cards):02d}"
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><style>
    *{{box-sizing:border-box}}body{{margin:0;background:#f5f1e9;font-family:"PingFang SC","Microsoft YaHei",sans-serif;color:#183f39}}
    main{{width:1080px;height:1440px;padding:110px 88px;display:flex;flex-direction:column;overflow:hidden;background:radial-gradient(ellipse at 100% 0,#d4e4cd,transparent 55%),#f5f1e9}}
    header{{font-size:28px;letter-spacing:5px;border-bottom:2px solid #b8c9ba;padding-bottom:30px}}h1{{font-size:76px;line-height:1.32;margin:75px 0 42px;font-weight:650;overflow-wrap:anywhere}}
    article{{font-size:36px;line-height:1.85;white-space:normal;overflow-wrap:anywhere;flex:1}}footer{{font-size:25px;color:#647970;border-top:2px solid #b8c9ba;padding-top:28px}}
    </style><main><header>RESEARCH NOTES / 科研手记</header><h1>{title}</h1><article>{body}</article><footer>{footer}</footer></main></html>'''


async def render_cards(draft):
    from playwright.async_api import async_playwright
    target = DATA / "assets" / f"draft-{draft.id}-v{draft.version}"
    target.mkdir(parents=True, exist_ok=True)
    paths = []
    async with async_playwright() as p:
        chrome = Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
        browser = await p.chromium.launch(headless=True, executable_path=str(chrome) if chrome.exists() else None)
        page = await browser.new_page(viewport={"width": 1080, "height": 1440}, device_scale_factor=1)
        try:
            for i in range(len(draft.cards or [{}])):
                await page.set_content(card_html(draft, i))
                await page.evaluate("document.fonts.ready")
                overflow = await page.evaluate("document.querySelector('main').scrollHeight > 1440")
                if overflow:
                    raise ValueError("图卡内容超出版面，请缩短图卡文字后重新生成。")
                path = target / f"{i + 1:02d}.png"
                await page.screenshot(path=str(path))
                paths.append(str(path.resolve()))
        finally:
            await browser.close()
    return paths
