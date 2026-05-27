"""Inspect Olive Young .prd_info element structure"""
import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.browser import BrowserManager

url = "https://www.oliveyoung.co.kr/store/main/getBestList.do"

bm = BrowserManager()
page = bm.create()

print("[inspect] navigating...")
page.goto(url, wait_until="domcontentloaded")
page.wait_for_timeout(5000)

# Inspect .prd_info structure
result = page.evaluate("""() => {
    var items = document.querySelectorAll('.prd_info');
    var samples = [];
    for (var i = 0; i < Math.min(items.length, 3); i++) {
        var el = items[i];
        var info = {
            index: i,
            outerHTML: el.outerHTML.substring(0, 2000),
            childTags: [],
            allTexts: [],
            allLinks: [],
            allImgs: [],
        };

        // Collect child element info
        var children = el.querySelectorAll('*');
        for (var j = 0; j < Math.min(children.length, 30); j++) {
            var child = children[j];
            var cls = child.className || '';
            if (typeof cls !== 'string') cls = '';
            var tag = child.tagName.toLowerCase();
            var text = (child.textContent || '').trim().substring(0, 100);

            info.childTags.push({
                tag: tag,
                cls: cls.substring(0, 80),
                text: text.substring(0, 60),
            });
        }

        // Links
        var links = el.querySelectorAll('a[href]');
        for (var k = 0; k < links.length; k++) {
            info.allLinks.push({
                href: (links[k].getAttribute('href') || '').substring(0, 200),
                text: (links[k].textContent || '').trim().substring(0, 60),
            });
        }

        // Images
        var imgs = el.querySelectorAll('img');
        for (var m = 0; m < imgs.length; m++) {
            info.allImgs.push({
                src: (imgs[m].getAttribute('src') || '').substring(0, 200),
                alt: (imgs[m].getAttribute('alt') || '').substring(0, 60),
            });
        }

        samples.push(info);
    }
    return samples;
}""")

for sample in result:
    print(f"\n=== Item #{sample['index']} ===")
    print(f"Links ({len(sample['allLinks'])}):")
    for l in sample['allLinks']:
        print(f"  text='{l['text']}' href={l['href'][:80]}")
    print(f"Images ({len(sample['allImgs'])}):")
    for img in sample['allImgs']:
        print(f"  alt='{img['alt']}' src={img['src'][:80]}")
    print(f"Children ({len(sample['childTags'])}):")
    for c in sample['childTags'][:15]:
        print(f"  <{c['tag']} class='{c['cls']}'> {c['text'][:50]}")

bm.close()
print("\n[inspect] done")
